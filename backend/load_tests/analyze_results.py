"""Combine Locust CSV output and server-monitor JSONL into audit-friendly reports."""

from __future__ import annotations

import argparse
import csv
import io
import json
import locale
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any, Iterable


def number(value: Any, default: float = 0.0) -> float:
    try:
        parsed = float(str(value).strip())
        return parsed if math.isfinite(parsed) else default
    except (TypeError, ValueError):
        return default


def integer(value: Any, default: int = 0) -> int:
    return int(number(value, float(default)))


def first_present(row: dict[str, Any], *keys: str, default: Any = "") -> Any:
    for key in keys:
        if key in row and str(row[key]).strip() != "":
            return row[key]
    return default


def load_csv(path: Path) -> list[dict[str, str]]:
    raw = path.read_bytes()
    encodings = list(dict.fromkeys(("utf-8-sig", locale.getpreferredencoding(False), "gb18030")))
    last_error: UnicodeDecodeError | None = None
    for encoding in encodings:
        try:
            text = raw.decode(encoding)
        except UnicodeDecodeError as exc:
            last_error = exc
            continue
        return list(csv.DictReader(io.StringIO(text, newline="")))
    raise ValueError(
        f"Could not decode Locust CSV {path.name}; tried {', '.join(encodings)}"
    ) from last_error


REQUIRED_MONITOR_METRICS = (
    ("cpu", "percent"),
    ("memory", "percent"),
    ("disk", "usage_percent"),
    ("disk", "busy_percent"),
)

DEFAULT_REQUIRED_PROCESS_GROUPS = ("gunicorn", "nginx", "postgres")


def parse_utc_timestamp(value: Any, *, label: str) -> datetime:
    """Parse epoch or timezone-aware ISO timestamps and return UTC."""

    raw = str(value).strip()
    if not raw:
        raise ValueError(f"{label} is missing")
    try:
        numeric = float(raw)
    except ValueError:
        numeric = None
    if numeric is not None:
        if not math.isfinite(numeric) or numeric < 0:
            raise ValueError(f"{label} is invalid: {raw}")
        if numeric >= 100_000_000_000:
            numeric /= 1000
        try:
            return datetime.fromtimestamp(numeric, tz=timezone.utc)
        except (OverflowError, OSError, ValueError) as exc:
            raise ValueError(f"{label} is invalid: {raw}") from exc
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label} is invalid: {raw}") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{label} must include a timezone: {raw}")
    return parsed.astimezone(timezone.utc)


def iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def validate_monitor_sample(sample: dict[str, Any], line_number: int) -> None:
    parse_utc_timestamp(sample.get("timestamp"), label=f"Monitor line {line_number} timestamp")
    host = sample.get("host")
    if not isinstance(host, str) or not host.strip():
        raise ValueError(f"Monitor line {line_number} is missing host identity")
    for section, key in REQUIRED_MONITOR_METRICS:
        section_value = sample.get(section)
        metric_path = f"{section}.{key}"
        if not isinstance(section_value, dict) or key not in section_value:
            raise ValueError(f"Monitor line {line_number} is missing required metric: {metric_path}")
        raw_value = section_value[key]
        if isinstance(raw_value, bool):
            raise ValueError(f"Monitor line {line_number} has a non-numeric metric: {metric_path}")
        try:
            parsed = float(raw_value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Monitor line {line_number} has a non-numeric metric: {metric_path}") from exc
        if not math.isfinite(parsed):
            raise ValueError(f"Monitor line {line_number} has a non-finite metric: {metric_path}")
        if parsed < 0 or parsed > 100:
            raise ValueError(
                f"Monitor line {line_number} has an out-of-range percentage for {metric_path}: {parsed}"
            )

def required_locust_number(
    row: dict[str, str],
    *keys: str,
    row_number: int,
    integer_only: bool = False,
) -> float | int:
    raw_value = first_present(row, *keys, default=None)
    label = "/".join(keys)
    if raw_value is None:
        raise ValueError(f"Locust stats row {row_number} is missing required metric: {label}")
    try:
        parsed = float(str(raw_value).strip())
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"Locust stats row {row_number} has a non-numeric metric: {label}"
        ) from exc
    if not math.isfinite(parsed) or parsed < 0:
        raise ValueError(f"Locust stats row {row_number} has an invalid metric: {label}")
    if integer_only:
        if not parsed.is_integer():
            raise ValueError(f"Locust stats row {row_number} must be an integer: {label}")
        return int(parsed)
    return parsed


def locust_row(row: dict[str, str], row_number: int) -> dict[str, Any]:
    requests = required_locust_number(
        row, "Request Count", "Requests", row_number=row_number, integer_only=True
    )
    failures = required_locust_number(
        row, "Failure Count", "Failures", row_number=row_number, integer_only=True
    )
    p95_ms = required_locust_number(row, "95%", "95%ile", "P95", row_number=row_number)
    return {
        "method": first_present(row, "Type", "Method", default=""),
        "name": first_present(row, "Name", default=""),
        "requests": requests,
        "failures": failures,
        "error_rate_percent": round(100 * failures / max(requests, 1), 3),
        "median_ms": number(first_present(row, "Median Response Time", "50%")),
        "average_ms": number(first_present(row, "Average Response Time", "Average")),
        "p95_ms": p95_ms,
        "p99_ms": number(first_present(row, "99%", "99%ile", "P99")),
        "max_ms": number(first_present(row, "Max Response Time", "100%", "Max")),
        "requests_per_second": number(first_present(row, "Requests/s", "Current RPS")),
        "failures_per_second": number(first_present(row, "Failures/s")),
    }


def summarize_locust(path: Path) -> dict[str, Any]:
    parsed = [
        locust_row(row, row_number)
        for row_number, row in enumerate(load_csv(path), start=2)
    ]
    parsed = [row for row in parsed if row["name"] or row["requests"] or row["failures"]]
    if not parsed:
        raise ValueError(f"Locust CSV has no data rows: {path}")

    aggregate = next((row for row in parsed if row["name"].strip().lower() == "aggregated"), None)
    endpoints = [row for row in parsed if row is not aggregate]
    if aggregate is None:
        requests = sum(row["requests"] for row in endpoints)
        failures = sum(row["failures"] for row in endpoints)
        aggregate = {
            "method": "",
            "name": "Aggregated (calculated)",
            "requests": requests,
            "failures": failures,
            "error_rate_percent": round(100 * failures / max(requests, 1), 3),
            "median_ms": max((row["median_ms"] for row in endpoints), default=0.0),
            "average_ms": (
                sum(row["average_ms"] * row["requests"] for row in endpoints) / max(requests, 1)
            ),
            # Percentiles cannot be mathematically combined. Maximum endpoint values
            # are deliberately conservative when Locust's Aggregated row is absent.
            "p95_ms": max((row["p95_ms"] for row in endpoints), default=0.0),
            "p99_ms": max((row["p99_ms"] for row in endpoints), default=0.0),
            "max_ms": max((row["max_ms"] for row in endpoints), default=0.0),
            "requests_per_second": sum(row["requests_per_second"] for row in endpoints),
            "failures_per_second": sum(row["failures_per_second"] for row in endpoints),
        }

    return {
        "source": path.name,
        "aggregate": aggregate,
        "endpoints": sorted(endpoints, key=lambda row: (row["p95_ms"], row["failures"]), reverse=True),
    }


def load_monitor(path: Path) -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig") as source:
        for line_number, line in enumerate(source, start=1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid monitor JSON on line {line_number}: {exc}") from exc
            if not isinstance(value, dict):
                raise ValueError(f"Monitor line {line_number} is not a JSON object")
            validate_monitor_sample(value, line_number)
            samples.append(value)
    if not samples:
        raise ValueError(f"Monitor JSONL has no samples: {path}")
    return samples


def nested_number(sample: dict[str, Any], section: str, key: str) -> float:
    value = sample.get(section, {})
    return number(value.get(key) if isinstance(value, dict) else None)


def metric(values: Iterable[float]) -> dict[str, float]:
    materialized = list(values)
    return {
        "average": round(mean(materialized), 3) if materialized else 0.0,
        "peak": round(max(materialized), 3) if materialized else 0.0,
    }


def summarize_monitor(path: Path) -> dict[str, Any]:
    samples = load_monitor(path)
    process_groups: dict[str, dict[str, list[float]]] = {}
    for sample in samples:
        groups = sample.get("process_groups", {})
        if not isinstance(groups, dict):
            continue
        for name, values in groups.items():
            if not isinstance(values, dict):
                continue
            group = process_groups.setdefault(name, {"cpu": [], "rss": [], "count": []})
            group["cpu"].append(number(values.get("cpu_percent")))
            group["rss"].append(number(values.get("memory_rss_bytes")))
            group["count"].append(number(values.get("count")))

    parsed_timestamps = [
        parse_utc_timestamp(sample["timestamp"], label=f"Monitor line {index} timestamp")
        for index, sample in enumerate(samples, start=1)
    ]
    if any(current < previous for previous, current in zip(parsed_timestamps, parsed_timestamps[1:])):
        raise ValueError("Monitor timestamps are not in chronological order")
    first = parsed_timestamps[0]
    last = parsed_timestamps[-1]
    duration_seconds = max(0.0, (last - first).total_seconds())
    hosts = {str(sample["host"]).strip() for sample in samples}
    if len(hosts) != 1:
        raise ValueError("Monitor samples contain multiple host identities")

    return {
        "source": path.name,
        "sample_count": len(samples),
        "host": next(iter(hosts)),
        "started_at": iso_utc(first),
        "ended_at": iso_utc(last),
        "duration_seconds": round(duration_seconds, 3),
        "cpu_percent": metric(nested_number(sample, "cpu", "percent") for sample in samples),
        "memory_percent": metric(nested_number(sample, "memory", "percent") for sample in samples),
        "swap_percent": metric(nested_number(sample, "swap", "percent") for sample in samples),
        "disk_usage_percent": metric(nested_number(sample, "disk", "usage_percent") for sample in samples),
        "disk_busy_percent": metric(nested_number(sample, "disk", "busy_percent") for sample in samples),
        "disk_read_bytes_per_second": metric(
            nested_number(sample, "disk", "read_bytes_per_second") for sample in samples
        ),
        "disk_write_bytes_per_second": metric(
            nested_number(sample, "disk", "write_bytes_per_second") for sample in samples
        ),
        "network_received_bytes_per_second": metric(
            nested_number(sample, "network", "received_bytes_per_second") for sample in samples
        ),
        "network_sent_bytes_per_second": metric(
            nested_number(sample, "network", "sent_bytes_per_second") for sample in samples
        ),
        "process_groups": {
            name: {
                "cpu_percent": metric(values["cpu"]),
                "memory_rss_bytes": metric(values["rss"]),
                "process_count": metric(values["count"]),
            }
            for name, values in sorted(process_groups.items())
        },
    }


def infer_related_file(stats_path: Path, suffix: str) -> Path | None:
    marker = "_stats.csv"
    if stats_path.name.endswith(marker):
        candidate = stats_path.with_name(stats_path.name[: -len(marker)] + suffix)
        if candidate.exists():
            return candidate
    return None


def load_failures(path: Path | None, limit: int = 20) -> list[dict[str, str]]:
    if path is None or not path.exists():
        return []
    rows = load_csv(path)
    safe_keys = ("Method", "Name", "Error", "Occurrences")
    return [{key: row.get(key, "") for key in safe_keys} for row in rows[:limit]]


def load_peak_users(path: Path | None) -> int | None:
    history = summarize_history(path)
    return history["peak_users"] if history else None


def summarize_history(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None
    rows = load_csv(path)
    if not rows:
        raise ValueError(f"Locust history CSV has no data rows: {path}")
    timestamps = [
        parse_utc_timestamp(
            first_present(row, "Timestamp", default=""),
            label=f"Locust history row {row_number} timestamp",
        )
        for row_number, row in enumerate(rows, start=2)
    ]
    started = min(timestamps)
    ended = max(timestamps)
    return {
        "source": path.name,
        "started_at": iso_utc(started),
        "ended_at": iso_utc(ended),
        "duration_seconds": round(max(0.0, (ended - started).total_seconds()), 3),
        "peak_users": max(
            integer(first_present(row, "User Count", "Users", default=0)) for row in rows
        ),
    }


def calculate_overlap_seconds(
    history: dict[str, Any] | None,
    monitor: dict[str, Any],
) -> float:
    if history is None:
        return 0.0
    locust_start = parse_utc_timestamp(history["started_at"], label="Locust start time")
    locust_end = parse_utc_timestamp(history["ended_at"], label="Locust end time")
    monitor_start = parse_utc_timestamp(monitor["started_at"], label="Monitor start time")
    monitor_end = parse_utc_timestamp(monitor["ended_at"], label="Monitor end time")
    return max(
        0.0,
        (min(locust_end, monitor_end) - max(locust_start, monitor_start)).total_seconds(),
    )


def process_group_peak(monitor: dict[str, Any], required_name: str) -> float:
    required = required_name.casefold()
    return max(
        (
            values["process_count"]["peak"]
            for name, values in monitor["process_groups"].items()
            if required in name.casefold()
        ),
        default=0.0,
    )


def threshold_result(label: str, actual: float, maximum: float, unit: str) -> dict[str, Any]:
    passed = actual <= maximum
    return {
        "metric": label,
        "actual": round(actual, 3),
        "maximum": maximum,
        "unit": unit,
        "passed": passed,
        "message": f"{label} {actual:.2f}{unit} {'≤' if passed else '>'} {maximum:.2f}{unit}",
    }


def minimum_threshold_result(
    label: str,
    actual: float | int | None,
    minimum: float | int,
    unit: str,
) -> dict[str, Any]:
    passed = actual is not None and actual >= minimum
    actual_value = round(float(actual), 3) if actual is not None else None
    actual_text = "缺失" if actual is None else f"{float(actual):.2f}{unit}"
    return {
        "metric": label,
        "actual": actual_value,
        "minimum": minimum,
        "unit": unit,
        "passed": passed,
        "message": f"{label} {actual_text} {'≥' if passed else '<'} {float(minimum):.2f}{unit}",
    }


def evaluate(
    locust: dict[str, Any],
    monitor: dict[str, Any],
    peak_users: int | None,
    overlap_seconds: float,
    args: argparse.Namespace,
) -> list[dict[str, Any]]:
    aggregate = locust["aggregate"]
    monitor_coverage_percent = 100 * overlap_seconds / args.expected_duration_seconds
    checks = [
        minimum_threshold_result("请求总数", aggregate["requests"], args.min_requests, ""),
        minimum_threshold_result("最高虚拟用户数", peak_users, args.expected_users, ""),
        minimum_threshold_result(
            "服务器监控有效重叠覆盖率",
            monitor_coverage_percent,
            args.min_monitor_coverage * 100,
            "%",
        ),
        threshold_result("请求错误率", aggregate["error_rate_percent"], args.max_error_rate, "%"),
        threshold_result("总体 P95", aggregate["p95_ms"], args.max_p95_ms, "ms"),
        threshold_result("CPU 峰值", monitor["cpu_percent"]["peak"], args.max_cpu, "%"),
        threshold_result("内存峰值", monitor["memory_percent"]["peak"], args.max_memory, "%"),
        threshold_result("磁盘使用率", monitor["disk_usage_percent"]["peak"], args.max_disk_usage, "%"),
        threshold_result("磁盘忙碌率", monitor["disk_busy_percent"]["peak"], args.max_disk_busy, "%"),
    ]
    checks.extend(
        minimum_threshold_result(
            f"关键进程 {required_name}",
            process_group_peak(monitor, required_name),
            1,
            "",
        )
        for required_name in args.required_processes
    )
    if args.expected_monitor_host:
        host_matches = monitor["host"].casefold() == args.expected_monitor_host.casefold()
        host_check = minimum_threshold_result(
            "监控服务器身份匹配",
            1 if host_matches else 0,
            1,
            "",
        )
        host_check["message"] = (
            f"监控服务器 {monitor['host']} "
            f"{'=' if host_matches else '!='} {args.expected_monitor_host}"
        )
        checks.append(host_check)
    return checks


def human_bytes(value: float) -> str:
    units = ("B", "KiB", "MiB", "GiB", "TiB")
    amount = float(value)
    for unit in units:
        if abs(amount) < 1024 or unit == units[-1]:
            return f"{amount:.2f} {unit}"
        amount /= 1024
    return f"{amount:.2f} TiB"


def markdown_report(report: dict[str, Any]) -> str:
    locust = report["locust"]
    aggregate = locust["aggregate"]
    monitor = report["monitor"]
    verdict = report["verdict"]
    lines = [
        "# 系统并发压力测试报告",
        "",
        f"**结论：{verdict}**",
        "",
        f"- 请求总数：{aggregate['requests']}",
        f"- 失败请求：{aggregate['failures']}",
        f"- 错误率：{aggregate['error_rate_percent']:.3f}%",
        f"- 总体 P95：{aggregate['p95_ms']:.2f} ms",
        f"- 平均吞吐：{aggregate['requests_per_second']:.2f} 请求/秒",
        f"- 最高虚拟用户数：{report['peak_users'] if report['peak_users'] is not None else '未提供历史 CSV'}",
        f"- 目标虚拟用户数：{report['expectations']['expected_users']}",
        f"- 目标测试时长：{report['expectations']['expected_duration_seconds']:.1f} 秒",
        f"- 服务器监控主机：{monitor['host']}",
        f"- 服务器监控样本：{monitor['sample_count']} 个（原始跨度 {monitor['duration_seconds']:.1f} 秒）",
        f"- 与 Locust 实际重叠：{report['monitor_overlap_seconds']:.1f} 秒（有效覆盖率 {report['monitor_coverage_percent']:.1f}%）",
        "",
        "## 验收阈值",
        "",
        "| 指标 | 实测 | 标准 | 结果 |",
        "|---|---:|---:|:---:|",
    ]
    for check in report["checks"]:
        actual = "缺失" if check["actual"] is None else f"{check['actual']:.2f}{check['unit']}"
        if "maximum" in check:
            standard = f"≤ {check['maximum']:.2f}{check['unit']}"
        else:
            standard = f"≥ {check['minimum']:.2f}{check['unit']}"
        lines.append(
            f"| {check['metric']} | {actual} | {standard} | {'通过' if check['passed'] else '不通过'} |"
        )

    lines.extend(
        [
            "",
            "## 服务器资源",
            "",
            "| 指标 | 平均 | 峰值 |",
            "|---|---:|---:|",
            f"| CPU | {monitor['cpu_percent']['average']:.2f}% | {monitor['cpu_percent']['peak']:.2f}% |",
            f"| 内存 | {monitor['memory_percent']['average']:.2f}% | {monitor['memory_percent']['peak']:.2f}% |",
            f"| Swap | {monitor['swap_percent']['average']:.2f}% | {monitor['swap_percent']['peak']:.2f}% |",
            f"| 磁盘使用率 | {monitor['disk_usage_percent']['average']:.2f}% | {monitor['disk_usage_percent']['peak']:.2f}% |",
            f"| 磁盘忙碌率 | {monitor['disk_busy_percent']['average']:.2f}% | {monitor['disk_busy_percent']['peak']:.2f}% |",
            f"| 磁盘读取速度 | {human_bytes(monitor['disk_read_bytes_per_second']['average'])}/s | {human_bytes(monitor['disk_read_bytes_per_second']['peak'])}/s |",
            f"| 磁盘写入速度 | {human_bytes(monitor['disk_write_bytes_per_second']['average'])}/s | {human_bytes(monitor['disk_write_bytes_per_second']['peak'])}/s |",
            f"| 网络接收速度 | {human_bytes(monitor['network_received_bytes_per_second']['average'])}/s | {human_bytes(monitor['network_received_bytes_per_second']['peak'])}/s |",
            f"| 网络发送速度 | {human_bytes(monitor['network_sent_bytes_per_second']['average'])}/s | {human_bytes(monitor['network_sent_bytes_per_second']['peak'])}/s |",
            "",
            "## 最慢接口（按 P95）",
            "",
            "| 方法 | 接口 | 请求数 | 失败数 | P95 |",
            "|---|---|---:|---:|---:|",
        ]
    )
    for endpoint in locust["endpoints"][:15]:
        lines.append(
            f"| {endpoint['method']} | `{endpoint['name']}` | {endpoint['requests']} | "
            f"{endpoint['failures']} | {endpoint['p95_ms']:.2f} ms |"
        )

    if monitor["process_groups"]:
        lines.extend(
            [
                "",
                "## 关键进程资源峰值",
                "",
                "| 进程 | 进程数峰值 | CPU 峰值 | 内存峰值 |",
                "|---|---:|---:|---:|",
            ]
        )
        for name, values in monitor["process_groups"].items():
            lines.append(
                f"| `{name}` | {values['process_count']['peak']:.0f} | "
                f"{values['cpu_percent']['peak']:.2f}% | {human_bytes(values['memory_rss_bytes']['peak'])} |"
            )

    if report["failures"]:
        lines.extend(["", "## Locust 错误样本", ""])
        for failure in report["failures"]:
            lines.append(
                f"- `{failure.get('Method', '')} {failure.get('Name', '')}`："
                f"{failure.get('Error', '')}（{failure.get('Occurrences', '')} 次）"
            )

    failed_checks = [check["message"] for check in report["checks"] if not check["passed"]]
    lines.extend(["", "## 大白话结论", ""])
    if failed_checks:
        lines.append("本轮测试没有达到设定的稳定标准，以下指标超限：")
        lines.extend(f"- {message}" for message in failed_checks)
    else:
        lines.append("本轮测试在设定并发和测试时长内全部达标，没有发现明显的容量风险。")
    lines.extend(
        [
            "",
            "> 此结论只代表本轮场景、虚拟用户数、测试数据量和服务器配置，不能直接外推到更高并发。",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze Locust CSV and server monitor JSONL results.")
    parser.add_argument("--locust-stats", type=Path, required=True, help="Locust *_stats.csv file.")
    parser.add_argument("--monitor", type=Path, required=True, help="server_monitor.py JSONL output.")
    parser.add_argument("--locust-failures", type=Path, help="Optional Locust *_failures.csv file.")
    parser.add_argument("--locust-history", type=Path, help="Optional Locust *_stats_history.csv file.")
    parser.add_argument(
        "--required-process",
        action="append",
        dest="required_processes",
        help=(
            "Required server process-name fragment; repeat to replace the defaults "
            "(gunicorn, nginx, postgres)."
        ),
    )
    parser.add_argument(
        "--expected-monitor-host",
        help=(
            "Expected server-monitor hostname. Required together with --fail-on-threshold "
            "so a report cannot accidentally use another machine."
        ),
    )
    parser.add_argument("--output-md", type=Path, required=True, help="Markdown report destination.")
    parser.add_argument("--output-json", type=Path, required=True, help="Machine-readable JSON destination.")
    parser.add_argument("--expected-users", type=int, required=True, help="Virtual users the test was required to reach.")
    parser.add_argument(
        "--expected-duration-seconds",
        type=float,
        required=True,
        help="Planned load-test duration in seconds.",
    )
    parser.add_argument("--min-requests", type=int, default=1, help="Minimum acceptable request count (default: 1).")
    parser.add_argument(
        "--min-monitor-coverage",
        type=float,
        default=0.9,
        help="Minimum monitored fraction of expected duration (default: 0.9).",
    )
    parser.add_argument("--max-error-rate", type=float, default=0.5, help="Maximum error percentage.")
    parser.add_argument("--max-p95-ms", type=float, default=1500.0, help="Maximum aggregate P95 in milliseconds.")
    parser.add_argument("--max-cpu", type=float, default=85.0, help="Maximum system CPU percentage.")
    parser.add_argument("--max-memory", type=float, default=80.0, help="Maximum memory percentage.")
    parser.add_argument("--max-disk-usage", type=float, default=80.0, help="Maximum disk usage percentage.")
    parser.add_argument("--max-disk-busy", type=float, default=95.0, help="Maximum disk busy percentage.")
    parser.add_argument(
        "--fail-on-threshold",
        action="store_true",
        help="Exit with status 2 when any threshold is exceeded (reports are still written).",
    )
    args = parser.parse_args(argv)
    if args.expected_users <= 0:
        parser.error("--expected-users must be positive")
    if args.expected_duration_seconds <= 0:
        parser.error("--expected-duration-seconds must be positive")
    if args.min_requests < 1:
        parser.error("--min-requests must be at least 1")
    if not 0 < args.min_monitor_coverage <= 1:
        parser.error("--min-monitor-coverage must be greater than 0 and no greater than 1")
    args.required_processes = list(
        dict.fromkeys(
            name.strip().casefold()
            for name in (args.required_processes or DEFAULT_REQUIRED_PROCESS_GROUPS)
            if name.strip()
        )
    )
    if not args.required_processes:
        parser.error("at least one --required-process must be specified")
    if args.fail_on_threshold and not args.expected_monitor_host:
        parser.error("--expected-monitor-host is required with --fail-on-threshold")
    for name in (
        "max_error_rate",
        "max_p95_ms",
        "max_cpu",
        "max_memory",
        "max_disk_usage",
        "max_disk_busy",
    ):
        if getattr(args, name) < 0:
            parser.error(f"--{name.replace('_', '-')} cannot be negative")
    return args


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        locust = summarize_locust(args.locust_stats)
        monitor = summarize_monitor(args.monitor)
        failures_path = args.locust_failures or infer_related_file(args.locust_stats, "_failures.csv")
        history_path = args.locust_history or infer_related_file(args.locust_stats, "_stats_history.csv")
        history = summarize_history(history_path)
        peak_users = history["peak_users"] if history else None
        overlap_seconds = calculate_overlap_seconds(history, monitor)
        monitor_coverage_percent = 100 * overlap_seconds / args.expected_duration_seconds
        checks = evaluate(locust, monitor, peak_users, overlap_seconds, args)
        report = {
            "schema_version": 2,
            "verdict": "PASS" if all(check["passed"] for check in checks) else "FAIL",
            "locust": locust,
            "monitor": monitor,
            "locust_history": history,
            "peak_users": peak_users,
            "locust_history_source": history["source"] if history else None,
            "monitor_overlap_seconds": round(overlap_seconds, 3),
            "monitor_coverage_percent": round(monitor_coverage_percent, 3),
            "failures": load_failures(failures_path),
            "checks": checks,
            "expectations": {
                "expected_users": args.expected_users,
                "expected_duration_seconds": args.expected_duration_seconds,
                "minimum_requests": args.min_requests,
                "minimum_monitor_coverage": args.min_monitor_coverage,
                "required_processes": args.required_processes,
                "expected_monitor_host": args.expected_monitor_host,
            },
            "thresholds": {
                "max_error_rate_percent": args.max_error_rate,
                "max_p95_ms": args.max_p95_ms,
                "max_cpu_percent": args.max_cpu,
                "max_memory_percent": args.max_memory,
                "max_disk_usage_percent": args.max_disk_usage,
                "max_disk_busy_percent": args.max_disk_busy,
            },
        }
        markdown = markdown_report(report)
        write_text(args.output_md, markdown)
        write_text(args.output_json, json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        print(f"{report['verdict']}: {args.output_md} | {args.output_json}")
        return 2 if args.fail_on_threshold and report["verdict"] == "FAIL" else 0
    except (OSError, ValueError, csv.Error) as exc:
        print(f"analysis failed: {exc}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
