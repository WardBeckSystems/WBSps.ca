# WBSps.ca Smoke Test Report

- **Execution Time:** `2026-11-22 05:16:02 UTC`
- **Overall Verdict:** `HEALTHY`
- **Passed Endpoints:** `15 / 15`
- **Total Duration:** `2.18s`

## DNS Resolution

| Host | Status | Resolved IP(s) |
| :--- | :---: | :--- |
| `wbsps.ca` | **PASS** | `69.27.124.160` |
| `xtm.wbsps.ca` | **PASS** | `69.27.124.160` |
| `wardbecksystems.github.io` | **PASS** | `185.199.108.153`, `185.199.109.153`, `185.199.111.153`, `185.199.110.153` |

## Endpoint Health Checks

| Name | Category | Status | Latency | Size | Result |
| :--- | :--- | :---: | :---: | :---: | :---: |
| [WBSps.ca Root (HTTPS)](https://wbsps.ca/) | Main Archive | `200` | 330.2 ms | 1362.4 KB | **PASS** |
| [WBSps.ca HTTP Redirect / Port 80](http://wbsps.ca/) | Main Archive | `200` | 312.4 ms | 1362.4 KB | **PASS** |
| [WBSps.ca Search Page](https://wbsps.ca/search.html) | Main Archive Tools | `200` | 283.2 ms | 11.1 KB | **PASS** |
| [WBSps.ca Drawing Viewer](https://wbsps.ca/viewer.html) | Main Archive Tools | `200` | 247.8 ms | 36.9 KB | **PASS** |
| [WBSps.ca Rotation Audit](https://wbsps.ca/rotation_audit.html) | Main Archive Tools | `200` | 216.7 ms | 713.9 KB | **PASS** |
| [WBSps.ca Parts Database](https://wbsps.ca/PARTS/index.html) | Main Archive Tools | `200` | 221.6 ms | 2.6 KB | **PASS** |
| [WBSps.ca Logo SVG](https://wbsps.ca/WBS_Logo.svg) | Archive Assets | `200` | 343.6 ms | 14.7 KB | **PASS** |
| [WBS Panel Bundle JS](https://wbsps.ca/_catalog/wbs_panel.js) | Archive Assets | `200` | 213.4 ms | 11.0 KB | **PASS** |
| [WBS Scan Bundle JS](https://wbsps.ca/_catalog/wbs_scan.js?v=7792b3a7) | Archive Assets | `200` | 236.4 ms | 6.5 KB | **PASS** |
| [XTM-4 Standalone App](https://xtm.wbsps.ca/) | XTM Meter | `200` | 155.0 ms | 72.9 KB | **PASS** |
| [XTM Version Telemetry JSON](https://xtm.wbsps.ca/version.json) | XTM Meter | `200` | 172.2 ms | 0.1 KB | **PASS** |
| [GitHub Pages Mirror Root](https://wardbecksystems.github.io/WBSps.ca/) | GitHub Pages | `200` | 84.3 ms | 1362.4 KB | **PASS** |
| [McCurdy ATS Dual Meters Simulator](https://wardbecksystems.github.io/WBSps.ca/mccurdy_ats_dual_meters.html) | GitHub Pages | `200` | 48.0 ms | 61.7 KB | **PASS** |
| [McCurdy Meter Logo Styleguide](https://wardbecksystems.github.io/WBSps.ca/styleguide-mccurdy-meter-logo.html) | GitHub Pages | `200` | 54.7 ms | 38.6 KB | **PASS** |
| [GitHub Pages Search Engine](https://wardbecksystems.github.io/WBSps.ca/search.html) | GitHub Pages | `200` | 76.4 ms | 11.1 KB | **PASS** |
