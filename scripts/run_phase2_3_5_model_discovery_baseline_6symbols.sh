#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="${PYTHON:-$ROOT/venv/bin/python}"
if [[ ! -x "$PYTHON" ]]; then PYTHON="python3"; fi

OUTDIR="$ROOT/data/reports/phase2_3_5_model_discovery_6symbols_parts"
mkdir -p "$OUTDIR"

symbols=(BTCUSDT ETHUSDT BNBUSDT SOLUSDT XRPUSDT DOGEUSDT)
reports=()
for symbol in "${symbols[@]}"; do
  echo "===== 开始 ${symbol} 模型基线 ====="
  out="$OUTDIR/${symbol}.json"
  "$PYTHON" "$ROOT/scripts/run_phase2_3_5_model_discovery_baseline.py" \
    --symbols "$symbol" \
    --shortlist 12 \
    --output "$out"
  reports+=("$out")
done

echo "===== 开始六币种合并 ====="
"$PYTHON" "$ROOT/scripts/merge_phase2_3_5_model_discovery_6symbols.py" \
  --reports "${reports[@]}" \
  --output "$ROOT/data/reports/phase2_3_5_model_discovery_baseline.json"
