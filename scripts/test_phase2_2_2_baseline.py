from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from quantbot.backtest.engine_v2 import BacktestEngine
from quantbot.research.evaluation import evaluate_strategy
from quantbot.strategies.models import trend_pullback
from scripts.run_phase2_2_2_baseline import (
    STRATEGIES,
    _gap_indices,
)


def make_frame(rows: int = 240) -> pd.DataFrame:
    idx = pd.date_range(
        "2021-01-01 00:00:00+00:00",
        periods=rows,
        freq="1h",
    )
    close = pd.Series(range(100, 100 + rows), index=idx, dtype=float)
    return pd.DataFrame(
        {
            "open": close,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
            "volume": 100.0,
        },
        index=idx,
    )


def test_strategy_registry():
    assert tuple(STRATEGIES) == (
        "trend_breakout",
        "trend_pullback",
        "volatility_breakout",
        "mean_reversion",
    )
    assert len(STRATEGIES) == 4


def test_engine_gap_index_builder():
    class Gap:
        previous = pd.Timestamp("2021-01-01 01:00:00+00:00")
        next = pd.Timestamp("2021-01-01 04:00:00+00:00")
        missing_bars = 2
        symbol = "BTCUSDT"

    class Boundary:
        gaps = (Gap(),)

    class Dataset:
        boundary = Boundary()

    points = _gap_indices(Dataset(), "BTCUSDT")
    assert len(points) == 2
    assert pd.Timestamp("2021-01-01 02:00:00+00:00") in points
    assert pd.Timestamp("2021-01-01 03:00:00+00:00") in points


def test_real_evaluation_shape():
    frame = make_frame()
    result = evaluate_strategy(
        symbol="BTCUSDT",
        window="TRAIN",
        frame=frame,
        strategy=trend_pullback,
        engine=BacktestEngine(initial_equity=10_000.0),
        risk_fraction=0.01,
        position_fraction=1.0,
        tag="baseline:test",
    )

    assert result.symbol == "BTCUSDT"
    assert result.window == "TRAIN"
    assert result.rows == len(frame)
    assert result.backtest.initial_equity == 10_000.0
    assert isinstance(result.backtest.trades, list)
    assert result.backtest.rejected_signals == 0


def main():
    test_strategy_registry()
    test_engine_gap_index_builder()
    test_real_evaluation_shape()
    print("PHASE2_2_2_BASELINE_RUNNER_TEST_OK")


if __name__ == "__main__":
    main()
