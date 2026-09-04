from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from quantbot.backtest.engine_v2 import BacktestEngine, Signal
from quantbot.research.evaluation import (
    evaluate_strategy,
    evaluate_windows,
    evaluation_to_dict,
)


def make_frame():
    idx = pd.date_range(
        "2025-01-01 00:00:00+00:00",
        periods=6,
        freq="1h",
    )
    return pd.DataFrame(
        {
            "open": [100, 101, 102, 103, 104, 105],
            "high": [101, 102, 103, 104, 105, 106],
            "low": [99, 100, 101, 102, 103, 104],
            "close": [100, 101, 102, 103, 104, 105],
            "volume": [10] * 6,
        },
        index=idx,
    )


def strategy(df, i):
    # The engine supplies pre-T history and expects execution timestamp T.
    ts = df.index[-1] + pd.Timedelta(hours=1)

    if i == 1:
        return Signal(
            timestamp=ts,
            side="buy",
            stop_price=99.0,
            risk_fraction=0.01,
            position_fraction=1.0,
            tag="test_entry",
        )
    if i == 4:
        return None
    return None


def engine_factory():
    return BacktestEngine(
        initial_equity=10000.0,
        max_position_fraction=1.0,
        max_risk_fraction=0.01,
        max_positions=1,
    )


def test_single_evaluation():
    frame = make_frame()

    result = evaluate_strategy(
        symbol="BTCUSDT",
        window="TRAIN",
        frame=frame,
        strategy=strategy,
        engine=engine_factory(),
    )

    assert result.symbol == "BTCUSDT"
    assert result.window == "TRAIN"
    assert result.rows == 6
    assert result.first_timestamp == frame.index[0].isoformat()
    assert result.last_timestamp == frame.index[-1].isoformat()
    assert len(result.backtest.trades) == 1

    payload = evaluation_to_dict(result)
    assert payload["symbol"] == "BTCUSDT"
    assert payload["window"] == "TRAIN"
    assert payload["initial_equity"] == 10000.0
    assert len(payload["trades"]) == 1


def test_windows_are_independent():
    frame = make_frame()

    evaluations = evaluate_windows(
        symbol="ETHUSDT",
        frames_by_window={
            "TRAIN": frame.iloc[:3],
            "VALIDATION": frame.iloc[3:5],
        },
        strategy=strategy,
        engine_factory=engine_factory,
    )

    assert [x.window for x in evaluations] == ["TRAIN", "VALIDATION"]
    assert evaluations[0].rows == 3
    assert evaluations[1].rows == 2


def test_bad_frame_is_rejected():
    frame = make_frame()
    duplicated = pd.concat([frame, frame.iloc[[0]]])

    try:
        evaluate_strategy(
            symbol="BTCUSDT",
            window="TRAIN",
            frame=duplicated,
            strategy=strategy,
            engine=engine_factory(),
        )
    except ValueError as exc:
        assert (
            "duplicate timestamps" in str(exc)
            or "timestamps are not monotonic" in str(exc)
        )
    else:
        raise AssertionError("duplicate timestamps were not rejected")


def main():
    test_single_evaluation()
    test_windows_are_independent()
    test_bad_frame_is_rejected()
    print("PHASE2_2_2_V1_0_1_STRATEGY_EVALUATION_CORE_TEST_OK")


if __name__ == "__main__":
    main()
