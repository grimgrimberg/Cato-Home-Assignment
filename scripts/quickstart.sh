#!/usr/bin/env bash
# Cross-platform quickstart script for Daily Movers Assistant
# Works on macOS, Linux, and Windows (via Git Bash or WSL)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${WORKSPACE_ROOT}"

echo "=== Daily Movers Assistant - Quick Demo ==="
echo ""

# Check for venv
if [[ ! -d ".venv" ]]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv || python -m venv .venv
fi

# Activate venv (cross-platform)
if [[ -f ".venv/bin/activate" ]]; then
    source .venv/bin/activate
elif [[ -f ".venv/Scripts/activate" ]]; then
    source .venv/Scripts/activate
else
    echo "ERROR: Could not find venv activation script"
    exit 1
fi

echo "Installing dependencies..."
pip install -q -r requirements.txt

echo ""
echo "Running demo (US top 5 movers)..."
python -m daily_movers run \
    --mode movers \
    --region us \
    --top 5 \
    --out runs/demo-$(date +%Y-%m-%d-%H%M%S)

echo ""
echo "Demo complete. Check the digest.html file that just opened."
