from __future__ import annotations

import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd

from quantbot.research.integration import (
    BoundaryWindow,
    GapRange,
    build_split_summary,
    expected_end,
    load_boundary_lock,
    load_parquet,
    slice_window,
    timestamp_in_non_tradable_gap,
    validate_boundary,
)


def make_lock(path: Path):
    path.write_text(
        json.dumps({
            "dataset_id": "UM_1H_TEST",
            "market": "um",
            "interval": "1h",
            "requested_end": "2026-08-31T23:00:00+00:00",
            "actual_start": "2021-01-01T00:00:00+00:00",
            "actual_end": "2026-07-31T23:00:00+00:00",
            "splits": [
                {
                    "name": "TRAIN",
                    "start": "2021-01-01T00:00:00+00:00",
                    "end": "2024-12-31T23:59:59.999999+00:00",
                    "rows": 0, "available": True,
                },
                {
                    "name": "VALIDATION",
                    "start": "2025-01-01T00:00:00+00:00",
                    "end": "2025-12-31T23:59:59.999999+00:00",
                    "rows": 0, "available": True,
                },
                {
                    "name": "OOS",
                    "start": "2026-01-01T00:00:00+00:00",
                    "end": "2026-07-31T23:00:00+00:00",
                    "rows": 0, "available": True,
                },
            ],
            "gaps": [
                {
                    "symbol": "SOLUSDT",
                    "previous": "2022-02-25T23:00:00+00:00",
                    "next": "2022-03-01T00:00:00+00:00",
                    "missing_bars": 72,
                }
            ],
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
        }, indent=2),
        encoding="utf-8",
    )


def make_frame():
    idx = pd.to_datetime([
        "2022-02-25 23:00:00+00:00",
        "2022-03-01 00:00:00+00:00",
        "2025-01-01 00:00:00+00:00",
        "2025-12-31 23:00:00+00:00",
        "2026-01-01 00:00:00+00:00",
        "2026-07-31 23:00:00+00:00",
    ])
    return pd.DataFrame({
        "open": [100, 101, 102, 103, 104, 105],
        "high": [101, 102, 103, 104, 105, 106],
        "low": [99, 100, 101, 102, 103, 104],
        "close": [100, 101, 102, 103, 104, 105],
    }, index=idx)


def test_real_boundary_lock_shape(tmp: Path):
    path = tmp / "lock.json"
    make_lock(path)
    ds = load_boundary_lock(path)

    assert ds.dataset_id == "UM_1H_TEST"
    assert [w.name for w in ds.windows] == [
        "TRAIN", "VALIDATION", "OOS"
    ]
    assert len(ds.gaps) == 1
    assert ds.gaps[0].symbol == "SOLUSDT"
    assert ds.gaps[0].missing_bars == 72
    assert expected_end(ds) == ds.actual_end
    assert ds.synthetic_candles is False
    assert ds.gap_policy == "non_tradable"


def test_gap_range_semantics(tmp: Path):
    path = tmp / "lock.json"
    make_lock(path)
    ds = load_boundary_lock(path)

    missing = pd.Timestamp("2022-02-26 12:00:00+00:00")
    assert timestamp_in_non_tradable_gap(ds, "SOLUSDT", missing)

    assert not timestamp_in_non_tradable_gap(
        ds, "SOLUSDT",
        pd.Timestamp("2022-02-25 23:00:00+00:00"),
    )
    assert not timestamp_in_non_tradable_gap(
        ds, "SOLUSDT",
        pd.Timestamp("2022-03-01 00:00:00+00:00"),
    )


def test_actual_end_caps_requested_end(tmp: Path):
    path = tmp / "lock.json"
    make_lock(path)
    ds = load_boundary_lock(path)
    df = make_frame()

    oos = slice_window(
        df, ds.windows[2], ds.actual_start, ds.actual_end
    )
    assert oos.index[-1] == ds.actual_end
    assert expected_end(ds) < ds.requested_end


def test_boundary_validation_and_split_rows(tmp: Path):
    path = tmp / "lock.json"
    make_lock(path)
    ds = load_boundary_lock(path)
    df = make_frame()

    result = validate_boundary(ds, {"SOLUSDT": df})
    assert result["ok"] is True
    assert result["gap_count"] == 1

    summary = build_split_summary(ds, {"SOLUSDT": df})
    assert [x["name"] for x in summary] == [
        "TRAIN", "VALIDATION", "OOS"
    ]
    assert summary[1]["rows"] == 2
    assert summary[2]["rows"] == 2


def test_parquet_roundtrip(tmp: Path):
    df = make_frame()
    path = tmp / "SOLUSDT.parquet"
    df.to_parquet(path)

    loaded = load_parquet(path)
    assert loaded.index.equals(df.index)
    assert loaded.index.tz is not None
    assert list(loaded.columns) == list(df.columns)


def main():
    with TemporaryDirectory() as d:
        tmp = Path(d)
        test_real_boundary_lock_shape(tmp)
        test_gap_range_semantics(tmp)
        test_actual_end_caps_requested_end(tmp)
        test_boundary_validation_and_split_rows(tmp)
        test_parquet_roundtrip(tmp)

    print("PHASE2_1_V1_0_1_INTEGRATION_TEST_OK")


if __name__ == "__main__":
    main()
