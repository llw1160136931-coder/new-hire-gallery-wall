from __future__ import annotations

import csv
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path


LOAD_TESTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(LOAD_TESTS_DIR))

import analyze_results


class AnalyzeResultsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory(prefix="analyze-results-")
        self.root = Path(self.temporary_directory.name)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def write_stats(self, name: str, requests: int = 100, failures: int = 0) -> Path:
        path = self.root / f"{name}_stats.csv"
        fieldnames = [
            "Type",
            "Name",
            "Request Count",
            "Failure Count",
            "Median Response Time",
            "Average Response Time",
            "Min Response Time",
            "Max Response Time",
            "Requests/s",
            "Failures/s",
            "95%",
            "99%",
        ]
        with path.open("w", encoding="utf-8", newline="") as target:
            writer = csv.DictWriter(target, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerow(
                {
                    "Type": "",
                    "Name": "Aggregated",
                    "Request Count": requests,
                    "Failure Count": failures,
                    "Median Response Time": 120 if requests else 0,
                    "Average Response Time": 150 if requests else 0,
                    "Min Response Time": 80 if requests else 0,
                    "Max Response Time": 700 if requests else 0,
                    "Requests/s": 20 if requests else 0,
                    "Failures/s": 0,
                    "95%": 450 if requests else 0,
                    "99%": 650 if requests else 0,
                }
            )
        return path

    def test_locust_csv_accepts_windows_chinese_encoding(self) -> None:
        path = self.root / "failures.csv"
        path.write_text(
            "Method,Name,Error,Occurrences\nGET,/api/works,请求已被限流,1\n",
            encoding="gb18030",
        )
        rows = analyze_results.load_csv(path)
        self.assertEqual(rows[0]["Error"], "请求已被限流")

    def write_history(
        self,
        name: str,
        peak_users: int,
        *,
        started: datetime | None = None,
        duration_seconds: int = 100,
    ) -> Path:
        path = self.root / f"{name}_stats_history.csv"
        started = started or datetime(2026, 7, 17, tzinfo=timezone.utc)
        with path.open("w", encoding="utf-8", newline="") as target:
            writer = csv.DictWriter(target, fieldnames=["Timestamp", "User Count", "Name"])
            writer.writeheader()
            writer.writerow(
                {
                    "Timestamp": int(started.timestamp()),
                    "User Count": max(1, peak_users // 2),
                    "Name": "Aggregated",
                }
            )
            writer.writerow(
                {
                    "Timestamp": int((started + timedelta(seconds=duration_seconds)).timestamp()),
                    "User Count": peak_users,
                    "Name": "Aggregated",
                }
            )
        return path
    def write_monitor(
        self,
        name: str,
        duration_seconds: int = 91,
        missing: str | None = None,
        *,
        started: datetime | None = None,
        host: str = "loadtest-server",
        second_host: str | None = None,
        process_groups: dict | None = None,
    ) -> Path:
        path = self.root / f"{name}.jsonl"
        started = started or datetime(2026, 7, 17, tzinfo=timezone.utc)
        if process_groups is None:
            process_groups = {
                "gunicorn": {"count": 4, "cpu_percent": 5, "memory_rss_bytes": 1000},
                "nginx": {"count": 2, "cpu_percent": 2, "memory_rss_bytes": 500},
                "postgres": {"count": 3, "cpu_percent": 3, "memory_rss_bytes": 800},
            }
        samples = []
        for index, timestamp in enumerate((started, started + timedelta(seconds=duration_seconds))):
            sample = {
                "timestamp": timestamp.isoformat().replace("+00:00", "Z"),
                "host": second_host if index and second_host else host,
                "interval_seconds": duration_seconds if index else 0,
                "cpu": {"percent": 20 + index},
                "memory": {"percent": 30 + index},
                "swap": {"percent": 0},
                "disk": {
                    "usage_percent": 40,
                    "busy_percent": 5 + index,
                    "read_bytes_per_second": 0,
                    "write_bytes_per_second": 0,
                },
                "network": {
                    "received_bytes_per_second": 0,
                    "sent_bytes_per_second": 0,
                },
                "process_groups": process_groups,
            }
            if missing:
                section, key = missing.split(".", 1)
                sample[section].pop(key)
            samples.append(sample)
        path.write_text(
            "".join(json.dumps(sample) + "\n" for sample in samples),
            encoding="utf-8",
        )
        return path
    def analyze(
        self,
        name: str,
        *,
        requests: int = 100,
        write_history: bool = True,
        peak_users: int = 100,
        monitor_duration: int = 91,
        monitor_started: datetime | None = None,
        monitor_host: str = "loadtest-server",
        process_groups: dict | None = None,
        extra_arguments: list[str] | None = None,
    ) -> tuple[int, dict]:
        stats = self.write_stats(name, requests=requests)
        if write_history:
            self.write_history(name, peak_users=peak_users)
        monitor = self.write_monitor(
            name,
            duration_seconds=monitor_duration,
            started=monitor_started,
            host=monitor_host,
            process_groups=process_groups,
        )
        markdown = self.root / f"{name}.md"
        machine_readable = self.root / f"{name}.json"
        arguments = [
            "--locust-stats",
            str(stats),
            "--monitor",
            str(monitor),
            "--output-md",
            str(markdown),
            "--output-json",
            str(machine_readable),
            "--expected-users",
            "100",
            "--expected-duration-seconds",
            "100",
            "--expected-monitor-host",
            "loadtest-server",
            "--fail-on-threshold",
            *(extra_arguments or []),
        ]
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            exit_code = analyze_results.main(arguments)
        report = json.loads(machine_readable.read_text(encoding="utf-8"))
        self.assertTrue(markdown.exists())
        return exit_code, report
    @staticmethod
    def checks_by_name(report: dict) -> dict[str, dict]:
        return {check["metric"]: check for check in report["checks"]}

    def test_complete_valid_data_passes(self) -> None:
        exit_code, report = self.analyze("pass")

        self.assertEqual(exit_code, 0)
        self.assertEqual(report["verdict"], "PASS")
        self.assertEqual(report["peak_users"], 100)
        self.assertEqual(report["monitor_coverage_percent"], 91)
        self.assertTrue(all(check["passed"] for check in report["checks"]))

    def test_zero_requests_fails(self) -> None:
        exit_code, report = self.analyze("zero", requests=0)

        self.assertEqual(exit_code, 2)
        self.assertEqual(report["verdict"], "FAIL")
        request_check = self.checks_by_name(report)["请求总数"]
        self.assertEqual(request_check["actual"], 0)
        self.assertFalse(request_check["passed"])

    def test_missing_p95_is_rejected_instead_of_becoming_zero(self) -> None:
        stats = self.write_stats("missing-p95")
        with stats.open("r", encoding="utf-8", newline="") as source:
            rows = list(csv.DictReader(source))
        rows[-1]["95%"] = ""
        with stats.open("w", encoding="utf-8", newline="") as target:
            writer = csv.DictWriter(target, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        with self.assertRaisesRegex(ValueError, "missing required metric.*95%"):
            analyze_results.summarize_locust(stats)

    def test_missing_stats_history_fails(self) -> None:
        exit_code, report = self.analyze("missing-history", write_history=False)

        self.assertEqual(exit_code, 2)
        self.assertEqual(report["verdict"], "FAIL")
        self.assertIsNone(report["peak_users"])
        self.assertFalse(self.checks_by_name(report)["最高虚拟用户数"]["passed"])

    def test_peak_users_below_expected_fails(self) -> None:
        exit_code, report = self.analyze("low-users", peak_users=99)

        self.assertEqual(exit_code, 2)
        self.assertEqual(report["verdict"], "FAIL")
        users_check = self.checks_by_name(report)["最高虚拟用户数"]
        self.assertEqual(users_check["actual"], 99)
        self.assertFalse(users_check["passed"])

    def test_monitor_coverage_below_minimum_fails(self) -> None:
        exit_code, report = self.analyze("short-monitor", monitor_duration=89)

        self.assertEqual(exit_code, 2)
        self.assertEqual(report["verdict"], "FAIL")
        coverage_check = self.checks_by_name(report)["服务器监控有效重叠覆盖率"]
        self.assertEqual(coverage_check["actual"], 89)
        self.assertFalse(coverage_check["passed"])

    def test_full_length_monitor_from_wrong_time_window_fails(self) -> None:
        exit_code, report = self.analyze(
            "wrong-window",
            monitor_duration=100,
            monitor_started=datetime(2026, 7, 17, tzinfo=timezone.utc) + timedelta(hours=1),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(report["monitor_overlap_seconds"], 0)
        coverage = self.checks_by_name(report)["服务器监控有效重叠覆盖率"]
        self.assertEqual(coverage["actual"], 0)
        self.assertFalse(coverage["passed"])

    def test_missing_default_critical_process_fails(self) -> None:
        process_groups = {
            "gunicorn": {"count": 4, "cpu_percent": 5, "memory_rss_bytes": 1000},
            "nginx": {"count": 2, "cpu_percent": 2, "memory_rss_bytes": 500},
        }
        exit_code, report = self.analyze("missing-postgres", process_groups=process_groups)

        self.assertEqual(exit_code, 2)
        process_check = self.checks_by_name(report)["关键进程 postgres"]
        self.assertEqual(process_check["actual"], 0)
        self.assertFalse(process_check["passed"])

    def test_explicit_required_process_replaces_defaults(self) -> None:
        process_groups = {
            "uvicorn-worker": {"count": 2, "cpu_percent": 5, "memory_rss_bytes": 1000},
        }
        exit_code, report = self.analyze(
            "custom-process",
            process_groups=process_groups,
            extra_arguments=["--required-process", "uvicorn"],
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(report["expectations"]["required_processes"], ["uvicorn"])
        self.assertTrue(self.checks_by_name(report)["关键进程 uvicorn"]["passed"])

    def test_expected_monitor_host_mismatch_fails(self) -> None:
        exit_code, report = self.analyze("wrong-host", monitor_host="another-server")

        self.assertEqual(exit_code, 2)
        host_check = self.checks_by_name(report)["监控服务器身份匹配"]
        self.assertEqual(host_check["actual"], 0)
        self.assertFalse(host_check["passed"])

    def test_monitor_samples_from_multiple_hosts_are_rejected(self) -> None:
        monitor = self.write_monitor("mixed-hosts", second_host="another-server")

        with self.assertRaisesRegex(ValueError, "multiple host identities"):
            analyze_results.summarize_monitor(monitor)

    def test_fail_on_threshold_requires_expected_monitor_host(self) -> None:
        arguments = [
            "--locust-stats", "stats.csv",
            "--monitor", "monitor.jsonl",
            "--output-md", "report.md",
            "--output-json", "report.json",
            "--expected-users", "100",
            "--expected-duration-seconds", "100",
            "--fail-on-threshold",
        ]
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            analyze_results.parse_args(arguments)
    def test_missing_required_monitor_field_raises_clear_error(self) -> None:
        monitor = self.write_monitor("bad-monitor", missing="disk.busy_percent")

        with self.assertRaisesRegex(ValueError, r"line 1.*disk\.busy_percent"):
            analyze_results.summarize_monitor(monitor)


if __name__ == "__main__":
    unittest.main()
