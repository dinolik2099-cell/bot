from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd

from quantbot.backtest.costs import CostModel
from quantbot.backtest.engine_v2 import BacktestEngine, Signal


def make_frame(rows):
    idx = pd.date_range(
        "2025-01-01 00:00:00", periods=len(rows), freq="1h", tz="UTC"
    )
    return pd.DataFrame(rows, index=idx)


def test_strict_history_and_next_bar_exit():
    df = make_frame([
        {"open": 100, "high": 101, "low": 99, "close": 100},
        {"open": 101, "high": 102, "low": 100, "close": 101.5},
        # Entry happens here. Even though this bar later touches 99/105,
        # it must NOT trigger the newly opened position.
        {"open": 102, "high": 105, "low": 99, "close": 103},
        # Next bar is eligible and reaches TP.
        {"open": 103, "high": 105, "low": 102, "close": 104},
    ])

    observations = []

    def strategy(history, i):
        if i == 2:
            assert len(history) == 2
            assert history.index[-1] == df.index[1]
            assert history.index[-1] < df.index[i]
            assert df.index[i] not in history.index
            observations.append(i)
            return Signal(
                timestamp=df.index[i],
                side="buy",
                stop_price=100,
                take_profit=104,
                risk_fraction=0.01,
                position_fraction=0.5,
                tag="NEXT_BAR",
            )
        return None

    engine = BacktestEngine(
        10000,
        CostModel(fee_rate=0.0004, slippage_bps=0),
        max_position_fraction=0.5,
        max_risk_fraction=0.01,
    )
    result = engine.run({"BTCUSDT": df}, {"BTCUSDT": strategy})

    assert observations == [2]
    assert len(result.trades) == 1
    assert result.trades[0].exit_reason == "take_profit"
    assert result.trades[0].exit_time == df.index[3].isoformat()


def test_same_bar_stop_wins_after_entry_bar():
    df = make_frame([
        {"open": 100, "high": 101, "low": 99, "close": 100},
        {"open": 101, "high": 102, "low": 100, "close": 101},
        {"open": 102, "high": 103, "low": 101, "close": 102},
        # Both levels are touched on this later candle.
        {"open": 103, "high": 105, "low": 99, "close": 104},
    ])

    def strategy(history, i):
        if i == 2:
            return Signal(
                timestamp=df.index[i],
                side="buy",
                stop_price=100,
                take_profit=104,
                risk_fraction=0.01,
                position_fraction=0.5,
            )
        return None

    engine = BacktestEngine(
        10000,
        CostModel(fee_rate=0.0004, slippage_bps=0),
        max_position_fraction=0.5,
        max_risk_fraction=0.01,
    )
    result = engine.run({"BTCUSDT": df}, {"BTCUSDT": strategy})

    assert len(result.trades) == 1
    assert result.trades[0].exit_reason == "stop"


def test_gap_is_not_an_entry_timestamp():
    df = make_frame([
        {"open": 100, "high": 101, "low": 99, "close": 100},
        {"open": 101, "high": 102, "low": 100, "close": 101},
        {"open": 102, "high": 103, "low": 101, "close": 102},
        {"open": 103, "high": 104, "low": 102, "close": 103},
    ])
    gap_ts = df.index[2]
    calls = []

    def strategy(history, i):
        calls.append(df.index[i])
        return Signal(
            timestamp=df.index[i],
            side="buy",
            stop_price=99,
            take_profit=105,
            risk_fraction=0.01,
            position_fraction=0.2,
        )

    engine = BacktestEngine(
        10000,
        CostModel(fee_rate=0, slippage_bps=0),
        max_position_fraction=0.2,
        max_risk_fraction=0.01,
        gap_indices={"BTCUSDT": {gap_ts}},
    )
    result = engine.run({"BTCUSDT": df}, {"BTCUSDT": strategy})

    assert gap_ts not in calls
    assert result.skipped_gap_bars == 1
    assert result.trades == []


def main():
    test_strict_history_and_next_bar_exit()
    test_same_bar_stop_wins_after_entry_bar()
    test_gap_is_not_an_entry_timestamp()
    print("BACKTEST_ENGINE_V1_1_TEST_OK")


if __name__ == "__main__":
    main()
