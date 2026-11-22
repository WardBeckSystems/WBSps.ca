#!/usr/bin/env python3
"""Lean production smoke test for wbsps.ca, xtm.wbsps.ca, and GitHub Pages mirror."""

import sys
import time
import socket
import ssl
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

ROOT = Path(__file__).resolve().parent.parent
LOG_FILE = ROOT / "logs" / "smoke_test.log"

ENDPOINTS = [
    ("wbsps.ca (HTTPS)",           "https://wbsps.ca/"),
    ("wbsps.ca (HTTP)",            "http://wbsps.ca/"),
    ("wbsps.ca /search.html",      "https://wbsps.ca/search.html"),
    ("wbsps.ca /viewer.html",      "https://wbsps.ca/viewer.html"),
    ("wbsps.ca /rotation_audit",   "https://wbsps.ca/rotation_audit.html"),
    ("wbsps.ca /PARTS",            "https://wbsps.ca/PARTS/index.html"),
    ("wbsps.ca WBS_Logo.svg",      "https://wbsps.ca/WBS_Logo.svg"),
    ("wbsps.ca wbs_panel.js",      "https://wbsps.ca/_catalog/wbs_panel.js"),
    ("wbsps.ca wbs_scan.js",       "https://wbsps.ca/_catalog/wbs_scan.js?v=7792b3a7"),
    ("xtm.wbsps.ca",               "https://xtm.wbsps.ca/"),
    ("xtm.wbsps.ca /version.json", "https://xtm.wbsps.ca/version.json"),
    ("xtm.wbsps.ca /router.py",    "https://xtm.wbsps.ca/tools/wbs-audio-router.py"),
    ("gh-pages Root",              "https://wardbecksystems.github.io/WBSps.ca/"),
    ("gh-pages McCurdy Dual",      "https://wardbecksystems.github.io/WBSps.ca/mccurdy_ats_dual_meters.html"),
    ("gh-pages McCurdy Style",     "https://wardbecksystems.github.io/WBSps.ca/styleguide-mccurdy-meter-logo.html"),
    ("gh-pages Search",            "https://wardbecksystems.github.io/WBSps.ca/search.html"),
]

def check(item, ctx):
    name, url = item
    t0 = time.perf_counter()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "WBSps-Smoke/1.0"})
        with urllib.request.urlopen(req, context=ctx, timeout=6) as r:
            ms = (time.perf_counter() - t0) * 1000
            sz = len(r.read())
            return (True, name, url, r.status, ms, sz, None)
    except urllib.error.HTTPError as e:
        ms = (time.perf_counter() - t0) * 1000
        return (e.code in (200, 301, 302), name, url, e.code, ms, 0, f"HTTP {e.code}")
    except Exception as e:
        ms = (time.perf_counter() - t0) * 1000
        return (False, name, url, 0, ms, 0, str(e))

def main():
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    ctx = ssl.create_default_context()
    t_start = time.perf_counter()

    # DNS check
    dns = {}
    for h in ("wbsps.ca", "xtm.wbsps.ca", "wardbecksystems.github.io"):
        try:
            dns[h] = socket.gethostbyname(h)
        except Exception as e:
            dns[h] = f"ERR: {e}"

    # Concurrent HTTP checks
    with ThreadPoolExecutor(max_workers=8) as ex:
        results = list(ex.map(lambda item: check(item, ctx), ENDPOINTS))

    elapsed = time.perf_counter() - t_start
    fails = [r for r in results if not r[0]]

    # 1. Check-in log to stdout
    print(f"[{ts}] Smoke Test: {'OK' if not fails else 'FAIL'} ({len(results) - len(fails)}/{len(results)} passed in {elapsed:.2f}s)")
    print(f"  DNS: wbsps.ca={dns.get('wbsps.ca')} | xtm={dns.get('xtm.wbsps.ca')} | gh={dns.get('wardbecksystems.github.io')}")
    for ok, name, url, status, ms, sz, err in results:
        mark = "✓" if ok else "✗"
        sz_str = f"{sz/1024:>6.1f}KB" if sz else "     -"
        err_str = f" [{err}]" if err else ""
        print(f"  {mark} {status or 'ERR':>3} {ms:>5.0f}ms {sz_str}  {name}{err_str}")

    # 2. File log (append-only)
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        summary = f"{ts} | {'PASS' if not fails else 'FAIL'} | {len(results)-len(fails)}/{len(results)} ok | {elapsed:.2f}s"
        f.write(summary + "\n")
        if fails:
            for _, name, url, status, ms, _, err in fails:
                f.write(f"   FAIL: {name} ({url}) -> status={status} err={err}\n")

    sys.exit(1 if fails else 0)

if __name__ == "__main__":
    main()
