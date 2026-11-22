#!/usr/bin/env python3
"""
WBSps.ca & Ecosystem Production Smoke Test
=========================================
Runs comprehensive endpoint, asset, and DNS health checks across:
- https://wbsps.ca (Primary production archive)
- https://xtm.wbsps.ca (XTM standalone meter app)
- https://wardbecksystems.github.io/WBSps.ca/ (GitHub Pages production mirror)

Features:
- Live console check-in log with status badges and latencies
- Persistent append-only file log (logs/smoke_test.log)
- Latest run snapshot in JSON (logs/smoke_test_latest.json)
- Latest run report in Markdown (logs/smoke_test_latest.md)
- Exit code 0 on success, 1 on critical failures (CI / cron friendly)
"""

import sys
import os
import time
import socket
import ssl
import json
import argparse
from datetime import datetime, timezone
from pathlib import Path
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_LOG_DIR = ROOT_DIR / "logs"

# Test targets configuration
HOSTS_TO_RESOLVE = [
    "wbsps.ca",
    "xtm.wbsps.ca",
    "wardbecksystems.github.io",
]

TARGETS = [
    # Primary Archive Site
    {
        "name": "WBSps.ca Root (HTTPS)",
        "url": "https://wbsps.ca/",
        "expected_status": [200],
        "category": "Main Archive",
        "critical": True,
    },
    {
        "name": "WBSps.ca HTTP Redirect / Port 80",
        "url": "http://wbsps.ca/",
        "expected_status": [200, 301, 302],
        "category": "Main Archive",
        "critical": False,
    },
    {
        "name": "WBSps.ca Search Page",
        "url": "https://wbsps.ca/search.html",
        "expected_status": [200],
        "category": "Main Archive Tools",
        "critical": True,
    },
    {
        "name": "WBSps.ca Drawing Viewer",
        "url": "https://wbsps.ca/viewer.html",
        "expected_status": [200],
        "category": "Main Archive Tools",
        "critical": True,
    },
    {
        "name": "WBSps.ca Rotation Audit",
        "url": "https://wbsps.ca/rotation_audit.html",
        "expected_status": [200],
        "category": "Main Archive Tools",
        "critical": False,
    },
    {
        "name": "WBSps.ca Parts Database",
        "url": "https://wbsps.ca/PARTS/index.html",
        "expected_status": [200],
        "category": "Main Archive Tools",
        "critical": False,
    },
    # Core Assets
    {
        "name": "WBSps.ca Logo SVG",
        "url": "https://wbsps.ca/WBS_Logo.svg",
        "expected_status": [200],
        "category": "Archive Assets",
        "critical": True,
    },
    {
        "name": "WBS Panel Bundle JS",
        "url": "https://wbsps.ca/_catalog/wbs_panel.js",
        "expected_status": [200],
        "category": "Archive Assets",
        "critical": True,
    },
    {
        "name": "WBS Scan Bundle JS",
        "url": "https://wbsps.ca/_catalog/wbs_scan.js?v=7792b3a7",
        "expected_status": [200],
        "category": "Archive Assets",
        "critical": True,
    },
    # XTM Standalone Meter
    {
        "name": "XTM-4 Standalone App",
        "url": "https://xtm.wbsps.ca/",
        "expected_status": [200],
        "category": "XTM Meter",
        "critical": True,
    },
    {
        "name": "XTM Version Telemetry JSON",
        "url": "https://xtm.wbsps.ca/version.json",
        "expected_status": [200],
        "category": "XTM Meter",
        "critical": True,
    },
    # GitHub Pages Production Mirror & Simulators
    {
        "name": "GitHub Pages Mirror Root",
        "url": "https://wardbecksystems.github.io/WBSps.ca/",
        "expected_status": [200],
        "category": "GitHub Pages",
        "critical": True,
    },
    {
        "name": "McCurdy ATS Dual Meters Simulator",
        "url": "https://wardbecksystems.github.io/WBSps.ca/mccurdy_ats_dual_meters.html",
        "expected_status": [200],
        "category": "GitHub Pages",
        "critical": True,
    },
    {
        "name": "McCurdy Meter Logo Styleguide",
        "url": "https://wardbecksystems.github.io/WBSps.ca/styleguide-mccurdy-meter-logo.html",
        "expected_status": [200],
        "category": "GitHub Pages",
        "critical": True,
    },
    {
        "name": "GitHub Pages Search Engine",
        "url": "https://wardbecksystems.github.io/WBSps.ca/search.html",
        "expected_status": [200],
        "category": "GitHub Pages",
        "critical": True,
    },
]


class SmokeTester:
    def __init__(self, log_dir: Path, timeout: float = 8.0, workers: int = 6):
        self.log_dir = log_dir
        self.timeout = timeout
        self.workers = workers
        self.ctx = ssl.create_default_context()
        self.dns_results = {}
        self.test_results = []
        self.start_time = None
        self.duration_sec = 0.0

    def check_dns(self):
        for host in HOSTS_TO_RESOLVE:
            try:
                ips = socket.gethostbyname_ex(host)[2]
                self.dns_results[host] = {"ok": True, "ips": ips, "error": None}
            except Exception as e:
                self.dns_results[host] = {"ok": False, "ips": [], "error": str(e)}

    def check_url(self, target: dict) -> dict:
        url = target["url"]
        expected = target["expected_status"]
        result = {
            "name": target["name"],
            "url": url,
            "category": target["category"],
            "critical": target["critical"],
            "status": None,
            "latency_ms": 0.0,
            "content_length": 0,
            "content_type": "",
            "passed": False,
            "error": None,
        }

        t0 = time.perf_counter()
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "WBSps-SmokeTest/1.0 (+https://wbsps.ca)",
                    "Accept": "*/*",
                },
            )
            with urllib.request.urlopen(req, context=self.ctx, timeout=self.timeout) as resp:
                elapsed = (time.perf_counter() - t0) * 1000.0
                body = resp.read()
                result["status"] = resp.status
                result["latency_ms"] = round(elapsed, 1)
                result["content_type"] = resp.headers.get("Content-Type", "")
                result["content_length"] = len(body)
                result["passed"] = resp.status in expected
        except urllib.error.HTTPError as e:
            elapsed = (time.perf_counter() - t0) * 1000.0
            result["status"] = e.code
            result["latency_ms"] = round(elapsed, 1)
            result["passed"] = e.code in expected
            result["error"] = f"HTTP {e.code}: {e.reason}"
        except urllib.error.URLError as e:
            elapsed = (time.perf_counter() - t0) * 1000.0
            result["latency_ms"] = round(elapsed, 1)
            result["passed"] = False
            result["error"] = f"URLError: {e.reason}"
        except Exception as e:
            elapsed = (time.perf_counter() - t0) * 1000.0
            result["latency_ms"] = round(elapsed, 1)
            result["passed"] = False
            result["error"] = str(e)

        return result

    def run(self):
        self.start_time = datetime.now(timezone.utc)
        t_begin = time.perf_counter()

        self.check_dns()

        # Test URLs concurrently
        results_by_url = {}
        with ThreadPoolExecutor(max_workers=self.workers) as executor:
            future_to_target = {
                executor.submit(self.check_url, target): target for target in TARGETS
            }
            for future in as_completed(future_to_target):
                res = future.result()
                results_by_url[res["url"]] = res

        # Preserve original configured order
        self.test_results = [results_by_url[t["url"]] for t in TARGETS]
        self.duration_sec = time.perf_counter() - t_begin

    def print_checkin_log(self):
        ts_str = self.start_time.strftime("%Y-%m-%d %H:%M:%S UTC")
        print("\n" + "=" * 76)
        print(f" WBSps.ca & Ecosystem Smoke Test Check-in — {ts_str}")
        print("=" * 76)

        # DNS Check section
        print("\n[DNS Resolution]")
        for host, data in self.dns_results.items():
            if data["ok"]:
                ips_str = ", ".join(data["ips"])
                print(f"  ✓ {host:28} -> {ips_str}")
            else:
                print(f"  ✗ {host:28} -> ERROR: {data['error']}")

        # Endpoint results grouped by category
        categories = []
        for r in self.test_results:
            if r["category"] not in categories:
                categories.append(r["category"])

        passed_count = sum(1 for r in self.test_results if r["passed"])
        failed_count = len(self.test_results) - passed_count
        crit_fails = sum(1 for r in self.test_results if not r["passed"] and r["critical"])

        for cat in categories:
            print(f"\n[{cat}]")
            cat_results = [r for r in self.test_results if r["category"] == cat]
            for r in cat_results:
                badge = "PASS" if r["passed"] else ("FAIL" if r["critical"] else "WARN")
                icon = "✓" if r["passed"] else ("✗" if r["critical"] else "!")
                status_str = f"HTTP {r['status']}" if r["status"] else "ERR"
                size_kb = f"{r['content_length'] / 1024:.1f} KB" if r["content_length"] else "0 KB"
                line = (
                    f"  {icon} [{badge:4}] {r['name']:36} | {status_str:8} | "
                    f"{r['latency_ms']:6.1f} ms | {size_kb:>8}"
                )
                print(line)
                if not r["passed"] and r["error"]:
                    print(f"         └─ Error: {r['error']}")

        print("\n" + "-" * 76)
        avg_latency = (
            sum(r["latency_ms"] for r in self.test_results) / len(self.test_results)
            if self.test_results
            else 0
        )
        status_banner = "ALL CHECKS PASSED" if crit_fails == 0 else f"{crit_fails} CRITICAL FAILURES"
        print(
            f" Summary: {status_banner} | {passed_count}/{len(self.test_results)} passed | "
            f"Avg Latency: {avg_latency:.1f} ms | Total Time: {self.duration_sec:.2f}s"
        )
        print("=" * 76 + "\n")

    def write_file_logs(self):
        self.log_dir.mkdir(parents=True, exist_ok=True)
        iso_ts = self.start_time.isoformat()
        date_str = self.start_time.strftime("%Y-%m-%d %H:%M:%S UTC")

        passed_count = sum(1 for r in self.test_results if r["passed"])
        total_count = len(self.test_results)
        crit_fails = sum(1 for r in self.test_results if not r["passed"] and r["critical"])
        verdict = "HEALTHY" if crit_fails == 0 else "FAILED"

        # 1. Append-only persistent text log
        log_file = self.log_dir / "smoke_test.log"
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"\n--- Smoke Test Run: {date_str} [{verdict}] ---\n")
            f.write(f"Total: {total_count} | Passed: {passed_count} | Critical Fails: {crit_fails} | Duration: {self.duration_sec:.2f}s\n")
            for host, d in self.dns_results.items():
                ips = ", ".join(d["ips"]) if d["ok"] else f"ERR: {d['error']}"
                f.write(f"  DNS {host}: {ips}\n")
            for r in self.test_results:
                tag = "PASS" if r["passed"] else ("FAIL" if r["critical"] else "WARN")
                status = f"HTTP_{r['status']}" if r["status"] else "ERR"
                err_msg = f" ({r['error']})" if r["error"] else ""
                f.write(f"  [{tag}] {r['name']} - {r['url']} -> {status} in {r['latency_ms']}ms [{r['content_length']}B]{err_msg}\n")

        # 2. Latest JSON snapshot
        json_file = self.log_dir / "smoke_test_latest.json"
        payload = {
            "timestamp": iso_ts,
            "verdict": verdict,
            "duration_sec": round(self.duration_sec, 2),
            "summary": {
                "total": total_count,
                "passed": passed_count,
                "failed": total_count - passed_count,
                "critical_failures": crit_fails,
                "avg_latency_ms": round(
                    sum(r["latency_ms"] for r in self.test_results) / total_count, 1
                )
                if total_count
                else 0,
            },
            "dns": self.dns_results,
            "endpoints": self.test_results,
        }
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)

        # 3. Latest Markdown summary table
        md_file = self.log_dir / "smoke_test_latest.md"
        with open(md_file, "w", encoding="utf-8") as f:
            f.write(f"# WBSps.ca Smoke Test Report\n\n")
            f.write(f"- **Execution Time:** `{date_str}`\n")
            f.write(f"- **Overall Verdict:** `{verdict}`\n")
            f.write(f"- **Passed Endpoints:** `{passed_count} / {total_count}`\n")
            f.write(f"- **Total Duration:** `{self.duration_sec:.2f}s`\n\n")

            f.write(f"## DNS Resolution\n\n")
            f.write(f"| Host | Status | Resolved IP(s) |\n| :--- | :---: | :--- |\n")
            for host, d in self.dns_results.items():
                st = "PASS" if d["ok"] else "FAIL"
                ip_str = ", ".join(f"`{ip}`" for ip in d["ips"]) if d["ok"] else f"Error: {d['error']}"
                f.write(f"| `{host}` | **{st}** | {ip_str} |\n")

            f.write(f"\n## Endpoint Health Checks\n\n")
            f.write(f"| Name | Category | Status | Latency | Size | Result |\n")
            f.write(f"| :--- | :--- | :---: | :---: | :---: | :---: |\n")
            for r in self.test_results:
                badge = "PASS" if r["passed"] else ("FAIL" if r["critical"] else "WARN")
                st = f"`{r['status']}`" if r["status"] else "`ERR`"
                size_str = f"{r['content_length'] / 1024:.1f} KB" if r["content_length"] else "0 KB"
                f.write(
                    f"| [{r['name']}]({r['url']}) | {r['category']} | {st} | "
                    f"{r['latency_ms']} ms | {size_str} | **{badge}** |\n"
                )

        print(f"Log files updated in: {self.log_dir}/")
        print(f"  • Append log:     {log_file}")
        print(f"  • JSON snapshot:  {json_file}")
        print(f"  • Markdown table: {md_file}")


def main():
    parser = argparse.ArgumentParser(description="Smoke test WBSps.ca and linked sites.")
    parser.add_argument(
        "--log-dir",
        type=Path,
        default=DEFAULT_LOG_DIR,
        help=f"Directory for smoke test logs (default: {DEFAULT_LOG_DIR})",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=8.0,
        help="Timeout in seconds per HTTP request (default: 8.0)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=6,
        help="Number of concurrent request workers (default: 6)",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Do not print check-in log to stdout",
    )
    args = parser.parse_args()

    tester = SmokeTester(
        log_dir=args.log_dir,
        timeout=args.timeout,
        workers=args.workers,
    )
    tester.run()

    if not args.quiet:
        tester.print_checkin_log()

    tester.write_file_logs()

    # Exit with code 1 if any critical test failed
    crit_fails = sum(1 for r in tester.test_results if not r["passed"] and r["critical"])
    if crit_fails > 0:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
