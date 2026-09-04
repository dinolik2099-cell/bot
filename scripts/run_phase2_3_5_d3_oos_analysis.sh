#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
source venv/bin/activate
python scripts/test_phase2_3_5_d3_oos_analysis.py
python scripts/run_phase2_3_5_d3_oos_analysis.py
