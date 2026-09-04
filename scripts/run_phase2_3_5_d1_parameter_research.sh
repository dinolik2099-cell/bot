#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
source venv/bin/activate
python scripts/test_phase2_3_5_d1_parameter_research.py
python scripts/run_phase2_3_5_d1_parameter_research.py --workers 6
