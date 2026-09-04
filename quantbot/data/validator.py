from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import pandas as pd
import numpy as np


INTERVAL_MS = {
    "1m": 60_000, "3m": 180_000, "5m": 300_000, "15m": 900_000,
    "30m": 1_800_000, "1h": 3_600_000, "2h": 7_200_000,
    "4h": 14_400_000, "6h": 21_600_000, "8h": 28_800_000,
    "12h": 43_200_000, "1d": 86_400_000,
}


@dataclass
class QualityReport:
    rows: int
    start: str | None
    end: str | None
    duplicate_timestamps: int
    non_monotonic: int
    gaps: int
    invalid_ohlc: int
    non_positive_prices: int
    negative_volume: int
    nan_core: int

    @property
    def ok(self) -> bool:
        return all([
            self.duplicate_timestamps == 0,
            self.non_monotonic == 0,
            self.gaps == 0,
            self.invalid_ohlc == 0,
            self.non_positive_prices == 0,
            self.negative_volume == 0,
            self.nan_core == 0,
        ])

    def to_dict(self):
        return self.__dict__ | {"ok": self.ok}


def validate_frame(df: pd.DataFrame, interval: str) -> QualityReport:
    if df.empty:
        return QualityReport(0, None, None, 0, 0, 0, 0, 0, 0, 0)

    x = df.copy()
    idx = pd.DatetimeIndex(x.index)
    duplicate = int(idx.duplicated().sum())
    non_monotonic = int((idx[1:] < idx[:-1]).sum()) if len(idx) > 1 else 0

    gaps = 0
    if interval in INTERVAL_MS and len(idx) > 1:
        diffs = idx.to_series().diff().dropna().dt.total_seconds() * 1000
        expected = INTERVAL_MS[interval]
        # A gap means more than one expected interval. Duplicate/negative cases are counted separately.
        gaps = int((diffs > expected * 1.01).sum())

    core = ["open", "high", "low", "close"]
    nan_core = int(x[core].isna().any(axis=1).sum())
    invalid_ohlc = int(((x.high < x.low) | (x.open > x.high) | (x.open < x.low) |
                        (x.close > x.high) | (x.close < x.low)).sum())
    non_positive_prices = int((x[["open", "high", "low", "close"]] <= 0).any(axis=1).sum())
    negative_volume = int((x["volume"] < 0).sum()) if "volume" in x else 0

    return QualityReport(
        rows=len(x),
        start=idx.min().isoformat(),
        end=idx.max().isoformat(),
        duplicate_timestamps=duplicate,
        non_monotonic=non_monotonic,
        gaps=gaps,
        invalid_ohlc=invalid_ohlc,
        non_positive_prices=non_positive_prices,
        negative_volume=negative_volume,
        nan_core=nan_core,
    )


def expected_timestamp_unit(values: pd.Series) -> str:
    """Infer ms vs us for Binance public data without assuming a fixed year."""
    s = pd.to_numeric(values, errors="coerce").dropna()
    if s.empty:
        raise ValueError("no timestamps")
    median = float(s.abs().median())
    return "us" if median >= 10**14 else "ms"


def load_csv_file(path: str | Path) -> pd.DataFrame:
    from .load import normalize_kline_frame
    return normalize_kline_frame(pd.read_csv(path, header=None))
