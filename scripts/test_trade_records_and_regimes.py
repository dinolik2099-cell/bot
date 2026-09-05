"""Synthetic-only coverage for audit records and causal regime labels."""
from pathlib import Path
import sys
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from quantbot.analytics import TradeRecord, summarize_failures
from quantbot.research.regimes import RegimeConfig, classify_regimes


def main() -> None:
    index = pd.date_range("2025-01-01", periods=120, freq="h", tz="UTC")
    close = pd.Series(100.0 + np.arange(120) * 0.2, index=index)
    frame = pd.DataFrame({"high": close + 0.5, "low": close - 0.5, "close": close})
    regimes = classify_regimes(frame, RegimeConfig(fast_span=5, slow_span=15, volatility_window=5))
    assert regimes.index.equals(frame.index)
    assert regimes.iloc[-1]["regime"] == "low_volatility_uptrend"
    records = (
        TradeRecord("BTCUSDT", "m1", "trend", "2025-01-01T00:00:00+00:00", "2025-01-01T01:00:00+00:00", "buy", 100, 98, 104, 98, "stop", -2, -2.1, .1, .02, 1, 3600, -1, regime="low_volatility_uptrend"),
        TradeRecord("ETHUSDT", "m2", "trend", "2025-01-01T00:00:00+00:00", "2025-01-01T01:00:00+00:00", "sell", 100, 102, 96, 96, "take_profit", 4, 3.9, .1, .02, 1, 3600, 2, regime="low_volatility_downtrend"),
    )
    summary = summarize_failures(records)
    assert summary["loss_count"] == 1 and summary["losses_by_exit_reason"] == {"stop": 1}
    assert records[0].to_dict()["model"] == "m1"
    print("TRADE_RECORDS_AND_REGIMES_SYNTHETIC_TEST_OK")


if __name__ == "__main__":
    main()
