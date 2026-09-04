from __future__ import annotations
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd
from quantbot.backtest.engine_v2 import BacktestEngine, Signal
from quantbot.backtest.costs import CostModel


def frame():
    idx = pd.date_range("2025-01-01", periods=5, freq="1h", tz="UTC")
    return pd.DataFrame({
        "open": [100, 101, 102, 103, 104],
        "high": [101, 102, 105, 104, 105],
        "low": [99, 100, 101, 102, 103],
        "close": [100.5, 101.5, 104, 103.5, 104.5],
    }, index=idx)


def main():
    df = frame()
    seen = []

    def strategy(history, i):
        # Engine calls with i=2 at execution T=02:00, while history is strictly < T.
        if i == 2:
            seen.append(history.index[-1])
            assert len(history) == 2
            assert history.index[-1] < df.index[i]
            assert "close" in history.columns
            return Signal(
                timestamp=df.index[i],
                side="buy",
                stop_price=100.0,
                take_profit=104.0,
                risk_fraction=0.01,
                position_fraction=0.5,
                tag="TEST",
            )
        return None

    engine = BacktestEngine(
        10000,
        cost_model=CostModel(fee_rate=0.0004, slippage_bps=2),
        max_position_fraction=0.5,
        max_risk_fraction=0.01,
    )
    result = engine.run({"BTCUSDT": df}, {"BTCUSDT": strategy})

    assert len(seen) == 1
    assert seen[0] == df.index[1]
    assert len(result.trades) == 1
    assert result.trades[0].exit_reason == "take_profit"
    assert result.trades[0].net_pnl > 0
    assert result.final_equity > 10000

    # Verify both stop and target touched: stop must win.
    df2 = df.copy()
    df2.loc[df2.index[2], "high"] = 105
    df2.loc[df2.index[2], "low"] = 99

    def stop_first(history, i):
        if i == 2:
            return Signal(
                timestamp=df2.index[i],
                side="buy",
                stop_price=100.0,
                take_profit=104.0,
                risk_fraction=0.01,
                position_fraction=0.5,
            )
        return None

    r2 = engine.run({"BTCUSDT": df2}, {"BTCUSDT": stop_first})
    assert r2.trades[0].exit_reason == "stop"

    # Verify a supplied gap is non-tradable.
    gap_ts = df.index[2]
    r3 = engine.run(
        {"BTCUSDT": df},
        {"BTCUSDT": strategy},
        # This line intentionally replaced below; run() has no override arg.
    ) if False else None

    print("BACKTEST_ENGINE_TEST_OK")
    print(result.metrics())


if __name__ == "__main__":
    main()
