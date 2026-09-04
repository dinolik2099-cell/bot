from __future__ import annotations

import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from quantbot.research.runner import (
    assert_gap_policy,
    assert_no_future_window_leakage,
    build_research_dataset,
    split_frame,
    split_frames,
    summarize_dataset,
)


def make_lock(path: Path):
    obj = {
        "dataset_id": "UM_1H_RUNNER_TEST",
        "market": "um",
        "interval": "1h",
        "requested_end": "2026-08-31T23:00:00+00:00",
        "actual_start": "2021-01-01T00:00:00+00:00",
        "actual_end": "2026-07-31T23:00:00+00:00",
        "splits": [
            {"name": "TRAIN", "start": "2021-01-01T00:00:00+00:00",
             "end": "2024-12-31T23:00:00+00:00",
             "rows": 0, "available": True},
            {"name": "VALIDATION", "start": "2025-01-01T00:00:00+00:00",
             "end": "2025-12-31T23:00:00+00:00",
             "rows": 0, "available": True},
            {"name": "OOS", "start": "2026-01-01T00:00:00+00:00",
             "end": "2026-07-31T23:00:00+00:00",
             "rows": 0, "available": True},
        ],
        "gaps": [{
            "symbol": "SOLUSDT",
            "previous": "2022-02-25T23:00:00+00:00",
            "next": "2022-03-01T00:00:00+00:00",
            "missing_bars": 72,
        }],
        "policies": {
            "timezone": "UTC",
            "boundary_unit": "completed_candle_timestamp",
            "synthetic_candles": False,
            "gap_policy": "non_tradable",
            "oos_end_policy": "min(requested_end, actual_dataset_end)",
            "lookahead_policy":
                "execution_at_T_uses_information_strictly_before_T",
        },
        "status": "LOCKED",
    }
    path.write_text(json.dumps(obj), encoding="utf-8")


def make_frame():
    idx = pd.to_datetime([
        "2024-12-31 23:00:00+00:00",
        "2025-01-01 00:00:00+00:00",
        "2025-12-31 23:00:00+00:00",
        "2026-01-01 00:00:00+00:00",
        "2026-07-31 23:00:00+00:00",
    ])
    return pd.DataFrame({
        "open": [1, 2, 3, 4, 5],
        "high": [2, 3, 4, 5, 6],
        "low": [0, 1, 2, 3, 4],
        "close": [1, 2, 3, 4, 5],
    }, index=idx)


def test_dataset_and_splits(tmp):
    lock = tmp / "lock.json"
    make_lock(lock)
    ds = build_research_dataset(lock)
    frame = make_frame()

    train = split_frame(ds, frame, "TRAIN")
    validation = split_frame(ds, frame, "VALIDATION")
    oos = split_frame(ds, frame, "OOS")

    assert len(train) == 1
    assert len(validation) == 2
    assert len(oos) == 2

    split = split_frames(
        ds,
        {"BTCUSDT": frame, "ETHUSDT": frame},
        "VALIDATION",
    )
    assert set(split) == {"BTCUSDT", "ETHUSDT"}
    assert all(len(x) == 2 for x in split.values())


def test_boundaries_and_summary(tmp):
    lock = tmp / "lock.json"
    make_lock(lock)
    ds = build_research_dataset(lock)
    frame = make_frame()

    assert_no_future_window_leakage(ds, frame.loc[: "2024-12-31 23:00:00+00:00"], "TRAIN")
    assert_no_future_window_leakage(ds, frame.loc["2025-01-01 00:00:00+00:00":"2025-12-31 23:00:00+00:00"], "VALIDATION")
    assert_no_future_window_leakage(ds, frame.loc["2026-01-01 00:00:00+00:00":], "OOS")

    summary = summarize_dataset(
        ds,
        {"BTCUSDT": frame},
        {"BTCUSDT": "canonical_raw"},
    )
    assert summary["dataset_id"] == "UM_1H_RUNNER_TEST"
    assert summary["data_sources"]["BTCUSDT"] == "canonical_raw"


def test_gap_policy(tmp):
    lock = tmp / "lock.json"
    make_lock(lock)
    ds = build_research_dataset(lock)

    frame = pd.DataFrame({
        "open": [1], "high": [1], "low": [1], "close": [1]
    }, index=pd.to_datetime([
        "2022-02-25 23:00:00+00:00"
    ]))

    assert_gap_policy(ds, "SOLUSDT", frame)


def main():
    with TemporaryDirectory() as d:
        tmp = Path(d)
        test_dataset_and_splits(tmp)
        test_boundaries_and_summary(tmp)
        test_gap_policy(tmp)

    print("PHASE2_2_1_RESEARCH_RUNNER_TEST_OK")


if __name__ == "__main__":
    main()
