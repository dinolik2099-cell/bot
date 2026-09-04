from __future__ import annotations

import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd

from quantbot.research.integration import (
    build_split_summary,
    effective_end,
    load_boundary_lock,
    load_canonical_symbol,
    load_symbol_with_parquet_fallback,
    timestamp_in_non_tradable_gap,
    validate_boundary,
)


def make_lock(path: Path):
    path.write_text(json.dumps({
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
                "end": "2024-12-31T23:59:59+00:00",
                "rows": 0,
                "available": True,
            },
            {
                "name": "VALIDATION",
                "start": "2025-01-01T00:00:00+00:00",
                "end": "2025-12-31T23:59:59+00:00",
                "rows": 0,
                "available": True,
            },
            {
                "name": "OOS",
                "start": "2026-01-01T00:00:00+00:00",
                "end": "2026-07-31T23:00:00+00:00",
                "rows": 0,
                "available": True,
            },
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
    }, indent=2), encoding="utf-8")


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


def test_lock_contract(tmp: Path):
    p = tmp / "lock.json"
    make_lock(p)
    ds = load_boundary_lock(p)

    assert ds.dataset_id == "UM_1H_TEST"
    assert [w.name for w in ds.windows] == ["TRAIN", "VALIDATION", "OOS"]
    assert len(ds.gaps) == 1
    assert ds.synthetic_candles is False
    assert ds.gap_policy == "non_tradable"


def test_split_membership(tmp: Path):
    p = tmp / "lock.json"
    make_lock(p)
    ds = load_boundary_lock(p)
    summary = build_split_summary(ds, {"SOLUSDT": make_frame()})

    assert [x["rows"] for x in summary] == [2, 2, 2]

    train = summary[0]["per_symbol"]["SOLUSDT"]
    validation = summary[1]["per_symbol"]["SOLUSDT"]
    oos = summary[2]["per_symbol"]["SOLUSDT"]

    assert train["first"] == "2022-02-25T23:00:00+00:00"
    assert train["last"] == "2022-03-01T00:00:00+00:00"
    assert validation["first"] == "2025-01-01T00:00:00+00:00"
    assert validation["last"] == "2025-12-31T23:00:00+00:00"
    assert oos["first"] == "2026-01-01T00:00:00+00:00"
    assert oos["last"] == "2026-07-31T23:00:00+00:00"


def test_gap_and_effective_end(tmp: Path):
    p = tmp / "lock.json"
    make_lock(p)
    ds = load_boundary_lock(p)

    assert timestamp_in_non_tradable_gap(
        ds, "SOLUSDT", "2022-02-26T12:00:00+00:00"
    )
    assert not timestamp_in_non_tradable_gap(
        ds, "SOLUSDT", "2022-02-25T23:00:00+00:00"
    )
    assert effective_end(ds) == pd.Timestamp(
        "2026-07-31T23:00:00+00:00"
    )


def test_validation(tmp: Path):
    p = tmp / "lock.json"
    make_lock(p)
    ds = load_boundary_lock(p)

    result = validate_boundary(ds, {"SOLUSDT": make_frame()})
    assert result["ok"] is True
    assert result["gap_count"] == 1


def test_canonical_loader_delegates():
    frame = make_frame()
    with patch(
        "quantbot.research.integration.load_symbol",
        return_value=frame,
    ) as mocked:
        result = load_canonical_symbol(
            "/raw",
            "SOLUSDT",
            "1h",
            market="um",
            validate=True,
        )

    mocked.assert_called_once_with(
        "/raw",
        "SOLUSDT",
        "1h",
        market="um",
        validate=True,
    )
    assert result is frame


def test_parquet_fallback(tmp: Path):
    frame = make_frame()
    path = tmp / "parquet" / "um" / "1h" / "SOLUSDT.parquet"
    path.parent.mkdir(parents=True)
    frame.to_parquet(path)

    def missing_loader(*args, **kwargs):
        raise FileNotFoundError("no raw data")

    with patch(
        "quantbot.research.integration.load_symbol",
        side_effect=missing_loader,
    ):
        loaded, source = load_symbol_with_parquet_fallback(
            tmp / "raw",
            tmp / "parquet",
            "SOLUSDT",
            "1h",
            market="um",
        )

    assert source == "parquet_fallback"
    assert loaded.index.equals(frame.index)


def main():
    with TemporaryDirectory() as d:
        tmp = Path(d)
        test_lock_contract(tmp)
        test_split_membership(tmp)
        test_gap_and_effective_end(tmp)
        test_validation(tmp)
        test_parquet_fallback(tmp)

    test_canonical_loader_delegates()
    print("PHASE2_1_V1_1_CANONICAL_LOADER_TEST_OK")


if __name__ == "__main__":
    main()
