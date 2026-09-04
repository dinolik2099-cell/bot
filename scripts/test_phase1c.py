from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd

from quantbot.research.splits import build_splits, slice_split
from quantbot.research.gaps import detect_gaps, is_timestamp_available
from quantbot.research.lookahead import signal_from_completed_bar
from quantbot.backtest.costs import CostModel


def main():
    splits = build_splits("2024-12-31T23:59:59Z", "2025-12-31T23:59:59Z", "2026-08-31T23:59:59Z",
                          "2021-01-01T00:00:00Z")
    assert [s.name for s in splits] == ["TRAIN", "VALIDATION", "OOS"]

    idx = pd.date_range("2025-01-01", periods=4, freq="1h", tz="UTC")
    df = pd.DataFrame({"close": [100, 101, 102, 103]}, index=idx)
    part = slice_split(df, splits[1])
    assert len(part) == 4

    gap_idx = idx.delete(2)
    gaps = detect_gaps(gap_idx, "1h")
    assert len(gaps) == 1
    assert gaps[0].missing_bars == 1
    assert not is_timestamp_available(pd.Timestamp("2025-01-01 02:00", tz="UTC"), gaps)

    signal = signal_from_completed_bar(df, pd.Timestamp("2025-01-01 03:00", tz="UTC"))
    assert signal["close"] == 102

    cm = CostModel(fee_rate=0.0004, slippage_bps=2)
    assert cm.execution_price(100, "buy") > 100
    assert cm.execution_price(100, "sell") < 100
    assert abs(cm.trading_cost(10000) - 4) < 1e-12

    print("PHASE1C_TEST_OK")


if __name__ == "__main__":
    main()
