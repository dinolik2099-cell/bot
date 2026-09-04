from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from quantbot.research.evaluation import make_strategy_adapter


def make_frame():
    idx = pd.date_range(
        "2025-01-01 00:00:00+00:00",
        periods=8,
        freq="1h",
    )
    return pd.DataFrame(
        {
            "open": [100, 101, 102, 103, 104, 105, 106, 107],
            "high": [101, 102, 103, 104, 105, 106, 107, 108],
            "low": [99, 100, 101, 102, 103, 104, 105, 106],
            "close": [100, 101, 102, 103, 104, 105, 106, 107],
            "volume": [10] * 8,
        },
        index=idx,
    )


def test_strategy(df):
    x = df.copy()
    x["signal"] = 0
    x["stop"] = float("nan")
    x["target"] = float("nan")

    # Signal is generated on T-1 (row 2), then executed at T (row 3).
    x.iloc[2, x.columns.get_loc("signal")] = 1
    x.iloc[2, x.columns.get_loc("stop")] = x.iloc[2]["close"] - 1
    x.iloc[2, x.columns.get_loc("target")] = x.iloc[2]["close"] + 3

    return x


def test_adapter_uses_t_minus_1_information():
    frame = make_frame()
    adapter = make_strategy_adapter(
        test_strategy,
        full_frame=frame,
        risk_fraction=0.01,
        position_fraction=1.0,
        tag="v1.0.4_t_minus_1",
    )

    signal = adapter(frame.iloc[:3].copy(), 3)

    assert signal is not None
    assert signal.timestamp == frame.index[3]
    assert signal.side == "buy"
    assert signal.stop_price == frame.iloc[2]["close"] - 1
    assert signal.take_profit == frame.iloc[2]["close"] + 3


def test_strategy_is_precomputed_once():
    frame = make_frame()
    calls = {"count": 0}

    def counted_strategy(df):
        calls["count"] += 1
        x = df.copy()
        x["signal"] = 0
        x["stop"] = float("nan")
        x["target"] = float("nan")
        x.iloc[2, x.columns.get_loc("signal")] = 1
        x.iloc[2, x.columns.get_loc("stop")] = x.iloc[2]["close"] - 1
        x.iloc[2, x.columns.get_loc("target")] = x.iloc[2]["close"] + 3
        return x

    adapter = make_strategy_adapter(
        counted_strategy,
        full_frame=frame,
        risk_fraction=0.01,
        position_fraction=1.0,
        tag="v1.0.4_precompute",
    )

    for i in range(1, len(frame)):
        adapter(frame.iloc[:i].copy(), i)

    assert calls["count"] == 1


def test_empty_history_returns_no_signal():
    frame = make_frame()
    adapter = make_strategy_adapter(
        test_strategy,
        full_frame=frame,
        risk_fraction=0.01,
        position_fraction=1.0,
        tag="v1.0.4_empty",
    )
    assert adapter(frame.iloc[:0].copy(), 0) is None


def test_zero_signal_returns_no_signal():
    frame = make_frame()

    def no_signal(df):
        x = df.copy()
        x["signal"] = 0
        x["stop"] = float("nan")
        x["target"] = float("nan")
        return x

    adapter = make_strategy_adapter(
        no_signal,
        full_frame=frame,
        risk_fraction=0.01,
        position_fraction=1.0,
        tag="v1.0.4_zero",
    )
    assert adapter(frame.iloc[:4].copy(), 4) is None


def test_true_lookahead_is_rejected():
    frame = make_frame()
    adapter = make_strategy_adapter(
        test_strategy,
        full_frame=frame,
        risk_fraction=0.01,
        position_fraction=1.0,
        tag="v1.0.4_lookahead",
    )

    # Keep len(history) == i, but make the final historical timestamp equal T.
    history = frame.iloc[:3].copy()
    history.index = history.index[:-1].append(
        pd.DatetimeIndex([frame.index[3]])
    )

    try:
        adapter(history, 3)
    except ValueError as exc:
        assert "lookahead violation" in str(exc)
    else:
        raise AssertionError("true lookahead history was not rejected")


def test_history_length_contract_is_rejected():
    frame = make_frame()
    adapter = make_strategy_adapter(
        test_strategy,
        full_frame=frame,
        risk_fraction=0.01,
        position_fraction=1.0,
        tag="v1.0.4_contract",
    )

    try:
        adapter(frame.iloc[:2].copy(), 3)
    except ValueError as exc:
        assert "history length mismatch" in str(exc)
    else:
        raise AssertionError("invalid engine history length was not rejected")


def main():
    test_adapter_uses_t_minus_1_information()
    test_strategy_is_precomputed_once()
    test_empty_history_returns_no_signal()
    test_zero_signal_returns_no_signal()
    test_true_lookahead_is_rejected()
    test_history_length_contract_is_rejected()
    print("PHASE2_2_2_V1_0_4_STRATEGY_ADAPTER_TEST_OK")


if __name__ == "__main__":
    main()
