#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${ROOT}/venv/bin/python"
[[ -x "$PYTHON" ]] || PYTHON="python3"

WINDOW="TRAIN"
ROWS="1500"
GAP_PROBE_ROWS="120"
BOUNDARY="data/reports/research_boundary_lock.json"
RAW_ROOT="data/raw"
PARQUET_ROOT="data/parquet"
REPORT_DIR="data/reports"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --window) WINDOW="$2"; shift 2 ;;
    --rows) ROWS="$2"; shift 2 ;;
    --gap-probe-rows) GAP_PROBE_ROWS="$2"; shift 2 ;;
    *) echo "未知参数：$1" >&2; exit 2 ;;
  esac
done

cd "$ROOT"
mkdir -p "$REPORT_DIR"

symbols=(BTCUSDT ETHUSDT BNBUSDT SOLUSDT XRPUSDT DOGEUSDT)
for symbol in "${symbols[@]}"; do
  echo "===== 开始 ${symbol} ====="
  "$PYTHON" scripts/test_phase2_3_5_real_data_preflight_6symbols.py \
    --symbol "$symbol" \
    --window "$WINDOW" \
    --boundary "$BOUNDARY" \
    --raw-root "$RAW_ROOT" \
    --parquet-root "$PARQUET_ROOT" \
    --rows "$ROWS" \
    --gap-probe-rows "$GAP_PROBE_ROWS" \
    --output "${REPORT_DIR}/phase2_3_5_real_data_preflight_${symbol}.json"
done

"$PYTHON" scripts/merge_phase2_3_5_real_data_preflight_6symbols.py \
  --input-dir "$REPORT_DIR" \
  --output "${REPORT_DIR}/phase2_3_5_real_data_preflight_6symbols.json"

