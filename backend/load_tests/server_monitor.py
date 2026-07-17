"""Write lightweight server resource samples as JSON Lines.

Run this on the server being tested while Locust runs from another machine.
The output intentionally excludes process command lines and environment variables so
credentials cannot accidentally end up in a load-test report.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, TextIO

import psutil


DEFAULT_PROCESS_NAMES = ("gunicorn", "nginx", "postgres")
SCHEMA_VERSION = 1


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def safe_process_value(getter, default: Any = None) -> Any:
    try:
        return getter()
    except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess, OSError):
        return default


def matching_processes(names: set[str], pids: set[int]) -> list[psutil.Process]:
    matches: list[psutil.Process] = []
    for process in psutil.process_iter(attrs=("pid", "name")):
        try:
            pid = process.info["pid"]
            name = (process.info.get("name") or "").lower()
            if pid in pids or any(candidate in name for candidate in names):
                matches.append(process)
        except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess):
            continue
    return matches


def prime_process_cpu(processes: Iterable[psutil.Process]) -> None:
    for process in processes:
        safe_process_value(lambda process=process: process.cpu_percent(interval=None), 0.0)


def process_sample(process: psutil.Process) -> dict[str, Any] | None:
    try:
        with process.oneshot():
            name = process.name()
            memory = process.memory_info()
            io = safe_process_value(process.io_counters)
            return {
                "pid": process.pid,
                "name": name,
                "status": safe_process_value(process.status),
                "cpu_percent": round(process.cpu_percent(interval=None), 2),
                "memory_rss_bytes": memory.rss,
                "memory_percent": round(process.memory_percent(), 3),
                "threads": safe_process_value(process.num_threads, 0),
                "io_read_bytes": getattr(io, "read_bytes", 0),
                "io_write_bytes": getattr(io, "write_bytes", 0),
            }
    except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess, OSError):
        return None


def aggregate_processes(processes: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "count": 0,
            "cpu_percent": 0.0,
            "memory_rss_bytes": 0,
            "memory_percent": 0.0,
            "threads": 0,
        }
    )
    for process in processes:
        row = grouped[process["name"]]
        row["count"] += 1
        row["cpu_percent"] += process["cpu_percent"]
        row["memory_rss_bytes"] += process["memory_rss_bytes"]
        row["memory_percent"] += process["memory_percent"]
        row["threads"] += process["threads"]

    return {
        name: {
            **values,
            "cpu_percent": round(values["cpu_percent"], 2),
            "memory_percent": round(values["memory_percent"], 3),
        }
        for name, values in sorted(grouped.items())
    }


def counter_rate(current: int, previous: int | None, elapsed: float) -> float:
    if previous is None or elapsed <= 0 or current < previous:
        return 0.0
    return round((current - previous) / elapsed, 2)


def collect_sample(
    *,
    index: int,
    disk_path: Path,
    process_names: set[str],
    pids: set[int],
    previous: dict[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    sampled_at = time.monotonic()
    memory = psutil.virtual_memory()
    swap = psutil.swap_memory()
    disk_usage = psutil.disk_usage(str(disk_path))
    disk_io = psutil.disk_io_counters()
    network = psutil.net_io_counters()
    load_average = safe_process_value(getattr(os, "getloadavg", lambda: None))

    processes = matching_processes(process_names, pids)
    if previous is None:
        prime_process_cpu(processes)
    process_rows = [row for process in processes if (row := process_sample(process)) is not None]

    elapsed = sampled_at - previous["sampled_at"] if previous else 0.0
    disk_read_bytes = getattr(disk_io, "read_bytes", 0)
    disk_write_bytes = getattr(disk_io, "write_bytes", 0)
    disk_busy_ms = getattr(disk_io, "busy_time", 0)
    net_recv_bytes = getattr(network, "bytes_recv", 0)
    net_sent_bytes = getattr(network, "bytes_sent", 0)

    previous_disk_read = previous.get("disk_read_bytes") if previous else None
    previous_disk_write = previous.get("disk_write_bytes") if previous else None
    previous_disk_busy = previous.get("disk_busy_ms") if previous else None
    previous_net_recv = previous.get("net_recv_bytes") if previous else None
    previous_net_sent = previous.get("net_sent_bytes") if previous else None

    busy_delta = (
        max(0, disk_busy_ms - previous_disk_busy)
        if previous_disk_busy is not None and disk_busy_ms >= previous_disk_busy
        else 0
    )
    disk_busy_percent = min(100.0, busy_delta / (elapsed * 10.0)) if elapsed > 0 else 0.0

    sample = {
        "schema_version": SCHEMA_VERSION,
        "timestamp": utc_now(),
        "sample_index": index,
        "host": socket.gethostname(),
        "monitor_config": {
            "process_names": sorted(process_names),
            "pids": sorted(pids),
        },
        "interval_seconds": round(elapsed, 3),
        "cpu": {
            "percent": round(psutil.cpu_percent(interval=None), 2),
            "count_logical": psutil.cpu_count(logical=True),
            "load_average": [round(value, 3) for value in load_average] if load_average else None,
        },
        "memory": {
            "total_bytes": memory.total,
            "available_bytes": memory.available,
            "used_bytes": memory.used,
            "percent": round(memory.percent, 2),
        },
        "swap": {
            "total_bytes": swap.total,
            "used_bytes": swap.used,
            "percent": round(swap.percent, 2),
        },
        "disk": {
            "path": str(disk_path),
            "total_bytes": disk_usage.total,
            "free_bytes": disk_usage.free,
            "used_bytes": disk_usage.used,
            "usage_percent": round(disk_usage.percent, 2),
            "read_bytes_per_second": counter_rate(disk_read_bytes, previous_disk_read, elapsed),
            "write_bytes_per_second": counter_rate(disk_write_bytes, previous_disk_write, elapsed),
            "busy_percent": round(disk_busy_percent, 2),
        },
        "network": {
            "received_bytes_per_second": counter_rate(net_recv_bytes, previous_net_recv, elapsed),
            "sent_bytes_per_second": counter_rate(net_sent_bytes, previous_net_sent, elapsed),
            "received_bytes_total": net_recv_bytes,
            "sent_bytes_total": net_sent_bytes,
        },
        "processes": process_rows,
        "process_groups": aggregate_processes(process_rows),
    }
    state = {
        "sampled_at": sampled_at,
        "disk_read_bytes": disk_read_bytes,
        "disk_write_bytes": disk_write_bytes,
        "disk_busy_ms": disk_busy_ms,
        "net_recv_bytes": net_recv_bytes,
        "net_sent_bytes": net_sent_bytes,
    }
    return sample, state


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Monitor CPU, memory, disk, network and selected server processes as JSONL."
    )
    parser.add_argument("--output", default="-", help="JSONL output path; '-' writes to stdout.")
    parser.add_argument("--interval", type=float, default=1.0, help="Sampling interval in seconds (default: 1).")
    parser.add_argument("--duration", type=float, default=0.0, help="Stop after N seconds; 0 runs until interrupted.")
    parser.add_argument("--disk-path", default="/", help="Filesystem path whose usage should be monitored.")
    parser.add_argument(
        "--process-name",
        action="append",
        dest="process_names",
        help="Case-insensitive process-name fragment; repeatable. Defaults to gunicorn, nginx and postgres.",
    )
    parser.add_argument("--pid", action="append", type=int, default=[], help="Additional PID to monitor; repeatable.")
    args = parser.parse_args(argv)
    if args.interval < 0.1:
        parser.error("--interval must be at least 0.1 seconds")
    if args.duration < 0:
        parser.error("--duration cannot be negative")
    disk_path = Path(args.disk_path)
    if not disk_path.exists():
        parser.error(f"--disk-path does not exist: {disk_path}")
    return args


def open_output(path: str) -> tuple[TextIO, bool]:
    if path == "-":
        return sys.stdout, False
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    return output_path.open("w", encoding="utf-8", newline="\n"), True


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    process_names = {name.lower() for name in (args.process_names or DEFAULT_PROCESS_NAMES)}
    pids = set(args.pid)
    output, should_close = open_output(args.output)
    stopped = False

    def stop_monitoring(_signum, _frame) -> None:
        nonlocal stopped
        stopped = True

    signal.signal(signal.SIGINT, stop_monitoring)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, stop_monitoring)

    started = time.monotonic()
    previous: dict[str, Any] | None = None
    index = 0
    try:
        while not stopped:
            if index:
                remaining = args.interval
                while remaining > 0 and not stopped:
                    sleep_for = min(remaining, 0.2)
                    time.sleep(sleep_for)
                    remaining -= sleep_for
            if stopped:
                break
            if args.duration and index and time.monotonic() - started >= args.duration:
                break
            sample, previous = collect_sample(
                index=index,
                disk_path=Path(args.disk_path),
                process_names=process_names,
                pids=pids,
                previous=previous,
            )
            output.write(json.dumps(sample, ensure_ascii=False, separators=(",", ":")) + "\n")
            output.flush()
            index += 1
            if args.duration and time.monotonic() - started >= args.duration:
                break
    finally:
        if should_close:
            output.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
