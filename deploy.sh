#!/usr/bin/env bash
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
XTM_DIR="$HERE/XTM.WBSps.ca"

echo "===================================================================="
echo " WBSps.ca Ecosystem Coordinated Deployment"
echo "===================================================================="

# 1. Deploy XTM standalone application
if [ -d "$XTM_DIR" ] && [ -f "$XTM_DIR/deploy.py" ]; then
    echo ">> Deploying XTM application..."
    python3 "$XTM_DIR/deploy.py" "$@"
else
    echo ">> Skipping XTM deploy: XTM.WBSps.ca directory or deploy.py not found."
fi

# 2. Run ecosystem smoke test check-in
if [ -f "$HERE/smoke_test.sh" ]; then
    echo ""
    echo ">> Running post-deploy smoke test check-in..."
    "$HERE/smoke_test.sh"
fi

echo "===================================================================="
echo " Ecosystem Deployment & Health Check Complete"
echo "===================================================================="
