from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd

from quantbot.backtest.engine_v2 import BacktestEngine, Signal
from quantbot.backtest.costs import CostModel


def make_df():
    idx = pd.date_range("2025-01-01", periods=5, freq="1h", tz="UTC")
    return pd.DataFrame(
        {
            "open": [100, 101, 102, 103, 104],
            "high": [101, 102, 105, 104, 105],
            "low": [99, 100, 101, 102, 103],
            "close": [100.5, 101.5, 104, 103.5, 104.5],
            "volume": [1000]*5,
        },
        index=idx,
    )


def main():
    df = make_df()
    calls = []

    def strategy(data, i):
        # i=2 executes at 02:00; strategy must only inspect rows before i.
        assert i == 2
        calls.append(i)
        assert len(data.iloc[:i]) == 2
        assert data.iloc[i-1]["close"] == 101.5
        return Signal(
            timestamp=data.index[i],
            side="buy",
            stop_price=100.0,
            take_profit=104.0,
            risk_fraction=0.01,
            position_fraction=0.5,
            tag="TEST",
        )

    engine = BacktestEngine(
        10000,
        cost_model=CostModel(fee_rate=0.0004, slippage_bps=2),
        max_position_fraction=0.5,
        max_risk_fraction=0.01,
        max_positions=1,
    )
    result = engine.run({"BTCUSDT": df}, {"BTCUSDT": strategy})

    assert calls == [2]
    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.exit_reason == "take_profit"
    assert trade.net_pnl > 0
    assert result.final_equity > 10000
    assert result.metrics()["max_drawdown"] >= 0

    print("BACKTEST_ENGINE_TEST_OK")
    print(result.metrics())


if __name__ == "__main__":
    main()
