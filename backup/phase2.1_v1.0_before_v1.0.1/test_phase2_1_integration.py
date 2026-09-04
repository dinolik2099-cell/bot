from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd

from quantbot.research.integration import (
    BoundaryWindow,
    load_boundary_lock,
    load_parquet,
    slice_window,
    validate_boundary,
)


def write_lock(path: Path):
    path.write_text(
        json.dumps(
            {
                "status": "LOCKED",
                "dataset_id": "UM_1H_TEST",
                "market": "um",
                "interval": "1h",
                "symbols": ["BTCUSDT"],
                "actual_start": "2021-01-01T00:00:00+00:00",
                "actual_end": "2026-07-31T23:00:00+00:00",
                "requested_end": "2026-08-31T23:00:00+00:00",
                "windows": [
                    {
                        "name": "TRAIN",
                        "start": "2021-01-01T00:00:00+00:00",
                        "end": "2024-12-31T23:00:00+00:00",
                    },
                    {
                        "name": "VALIDATION",
                        "start": "2025-01-01T00:00:00+00:00",
                        "end": "2025-12-31T23:00:00+00:00",
                    },
                    {
                        "name": "OOS",
                        "start": "2026-01-01T00:00:00+00:00",
                        "end": "2026-07-31T23:00:00+00:00",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )


def make_df():
    idx = pd.to_datetime(
        [
            "2024-12-31 23:00:00+00:00",
            "2025-01-01 00:00:00+00:00",
            "2025-12-31 23:00:00+00:00",
            "2026-01-01 00:00:00+00:00",
            "2026-07-31 23:00:00+00:00",
        ]
    )
    return pd.DataFrame(
        {
            "open": [100, 101, 102, 103, 104],
            "high": [101, 102, 103, 104, 105],
            "low": [99, 100, 101, 102, 103],
            "close": [100.5, 101.5, 102.5, 103.5, 104.5],
        },
        index=idx,
    )


def test_lock_and_windows(tmp: Path):
    lock = tmp / "lock.json"
    write_lock(lock)
    ds = load_boundary_lock(lock)

    assert ds.dataset_id == "UM_1H_TEST"
    assert ds.actual_end == pd.Timestamp(
        "2026-07-31 23:00:00+00:00"
    )
    assert ds.requested_end == pd.Timestamp(
        "2026-08-31 23:00:00+00:00"
    )

    df = make_df()
    train = slice_window(
        df, ds.windows[0], ds.actual_start, ds.actual_end
    )
    validation = slice_window(
        df, ds.windows[1], ds.actual_start, ds.actual_end
    )
    oos = slice_window(
        df, ds.windows[2], ds.actual_start, ds.actual_end
    )

    assert list(train.index) == [
        pd.Timestamp("2024-12-31 23:00:00+00:00")
    ]
    assert list(validation.index) == [
        pd.Timestamp("2025-01-01 00:00:00+00:00"),
        pd.Timestamp("2025-12-31 23:00:00+00:00"),
    ]
    assert list(oos.index) == [
        pd.Timestamp("2026-01-01 00:00:00+00:00"),
        pd.Timestamp("2026-07-31 23:00:00+00:00"),
    ]


def test_requested_end_is_never_extended(tmp: Path):
    lock = tmp / "lock.json"
    write_lock(lock)
    ds = load_boundary_lock(lock)
    df = make_df()

    # Even though requested_end is later, OOS is hard-capped by actual_end.
    oos = slice_window(
        df,
        ds.windows[2],
        ds.actual_start,
        ds.actual_end,
    )
    assert oos.index[-1] == ds.actual_end
    assert pd.Timestamp("2026-08-01 00:00:00+00:00") not in oos.index


def test_boundary_validation(tmp: Path):
    lock = tmp / "lock.json"
    write_lock(lock)
    ds = load_boundary_lock(lock)
    result = validate_boundary(ds, {"BTCUSDT": make_df()})
    assert result["ok"] is True
    assert result["errors"] == []


def test_parquet_roundtrip(tmp: Path):
    source = make_df()
    path = tmp / "BTCUSDT.parquet"
    source.to_parquet(path)

    loaded = load_parquet(path)
    assert loaded.index.equals(source.index)
    assert list(loaded.columns) == list(source.columns)


def main():
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        test_lock_and_windows(tmp)
        test_requested_end_is_never_extended(tmp)
        test_boundary_validation(tmp)
        test_parquet_roundtrip(tmp)

    print("PHASE2_1_INTEGRATION_TEST_OK")


if __name__ == "__main__":
    main()
