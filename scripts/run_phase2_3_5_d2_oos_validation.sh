#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
source venv/bin/activate
python scripts/test_phase2_3_5_d2_oos_validation.py
python scripts/run_phase2_3_5_d2_oos_validation.py --workers "${1:-6}"
