#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-python}"
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  PYTHON_BIN="python3"
fi

"$PYTHON_BIN" -m pip install -r requirements.txt -r requirements-dev.txt
"$PYTHON_BIN" -m daily_movers run --date 2026-02-08 --mode movers --top 20 --out runs/2026-02-08
"$PYTHON_BIN" -m daily_movers run --mode watchlist --watchlist watchlist.yaml --out runs/watchlist-demo
"$PYTHON_BIN" -m pytest -q -s
