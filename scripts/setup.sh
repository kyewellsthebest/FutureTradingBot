#!/usr/bin/env bash
# One-shot environment setup: creates a venv and installs requirements.
set -euo pipefail
cd "$(dirname "$0")/.."

PY=${PYTHON:-python3}
"$PY" -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
echo
echo "Done. Activate with:  source .venv/bin/activate"
echo "Then:"
echo "  python -m bot.main          # run the trading loop"
echo "  python -m dashboard.server  # run the dashboard on :5000"
