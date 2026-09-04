from __future__ import annotations

from dataclasses import dataclass
import pandas as pd


@dataclass(frozen=True)
class TimeSplit:
    name: str
    start: pd.Timestamp
    end: pd.Timestamp

    def mask(self, index: pd.DatetimeIndex) -> pd.Series:
        return (index >= self.start) & (index <= self.end)

    def describe(self) -> dict:
        return {
            "name": self.name,
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
        }


def parse_utc(value: str) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    else:
        ts = ts.tz_convert("UTC")
    return ts


def build_splits(train_end: str, validation_end: str, oos_end: str,
                 dataset_start: str | None = None,
                 dataset_end: str | None = None) -> list[TimeSplit]:
    train_end_ts = parse_utc(train_end)
    validation_end_ts = parse_utc(validation_end)
    oos_end_ts = parse_utc(oos_end)

    if not (train_end_ts < validation_end_ts < oos_end_ts):
        raise ValueError("Split boundaries must satisfy train_end < validation_end < oos_end")

    start = parse_utc(dataset_start) if dataset_start else pd.Timestamp("1970-01-01", tz="UTC")

    splits = [
        TimeSplit("TRAIN", start, train_end_ts),
        TimeSplit("VALIDATION", train_end_ts + pd.Timedelta(microseconds=1), validation_end_ts),
        TimeSplit("OOS", validation_end_ts + pd.Timedelta(microseconds=1), oos_end_ts),
    ]

    if dataset_end:
        end = parse_utc(dataset_end)
        if end < splits[-1].start:
            raise ValueError("dataset_end is before OOS start")
    return splits


def slice_split(df: pd.DataFrame, split: TimeSplit) -> pd.DataFrame:
    if not isinstance(df.index, pd.DatetimeIndex):
        raise TypeError("DataFrame index must be a DatetimeIndex")
    idx = df.index
    return df.loc[(idx >= split.start) & (idx <= split.end)].copy()
