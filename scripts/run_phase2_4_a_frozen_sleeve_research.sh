#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
source venv/bin/activate
python scripts/run_phase2_4_a_frozen_sleeve_research.py --workers "${1:-6}"
