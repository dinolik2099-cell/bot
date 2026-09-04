from __future__ import annotations

import io
import zipfile
import tempfile
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import pandas as pd

from quantbot.data.load import normalize_kline_frame
from quantbot.data.validator import validate_frame, expected_timestamp_unit
from quantbot.data.binance_public import monthly_url


def main():
    assert monthly_url("spot", "BTCUSDT", "1h", 2024, 1).endswith(
        "/data/spot/monthly/klines/BTCUSDT/1h/BTCUSDT-1h-2024-01.zip"
    )
    assert monthly_url("um", "BTCUSDT", "1h", 2024, 1).endswith(
        "/data/futures/um/monthly/klines/BTCUSDT/1h/BTCUSDT-1h-2024-01.zip"
    )

    ms = pd.Series([1609459200000, 1609462800000])
    us = pd.Series([1735689600000000, 1735693200000000])
    assert expected_timestamp_unit(ms) == "ms"
    assert expected_timestamp_unit(us) == "us"

    raw = pd.DataFrame([
        [1609459200000, "1", "2", "0.5", "1.5", "10", 1609462799999, "15", 10, "5", "7.5", 0],
        [1609462800000, "1.5", "2.2", "1.4", "2", "11", 1609466399999, "20", 12, "6", "10", 0],
    ])
    df = normalize_kline_frame(raw)
    report = validate_frame(df, "1h")
    assert report.ok, report.to_dict()
    assert len(df) == 2

    bad = df.copy()
    bad.iloc[0, bad.columns.get_loc("high")] = 0.1
    report = validate_frame(bad, "1h")
    assert not report.ok
    assert report.invalid_ohlc >= 1

    print("DATA_ENGINE_TEST_OK")


if __name__ == "__main__":
    main()
