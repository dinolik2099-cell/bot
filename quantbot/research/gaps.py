from __future__ import annotations

from dataclasses import dataclass
import pandas as pd

from quantbot.data.validator import INTERVAL_MS


@dataclass(frozen=True)
class GapRange:
    start_exclusive: pd.Timestamp
    end_exclusive: pd.Timestamp
    missing_bars: int

    def contains(self, ts: pd.Timestamp) -> bool:
        return self.start_exclusive < ts < self.end_exclusive


def detect_gaps(index: pd.DatetimeIndex, interval: str) -> list[GapRange]:
    if interval not in INTERVAL_MS or len(index) < 2:
        return []

    idx = pd.DatetimeIndex(index).sort_values()
    step = pd.Timedelta(milliseconds=INTERVAL_MS[interval])
    diffs = idx.to_series().diff()

    gaps = []
    for ts, delta in diffs[diffs > step * 1.01].items():
        missing = max(0, int(round(delta / step)) - 1)
        gaps.append(GapRange(ts - delta, ts, missing))
    return gaps


def is_timestamp_available(ts: pd.Timestamp, gaps: list[GapRange]) -> bool:
    ts = pd.Timestamp(ts)
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    return not any(g.contains(ts) for g in gaps)


def availability_mask(index: pd.DatetimeIndex, gaps: list[GapRange]) -> pd.Series:
    return pd.Series(
        [is_timestamp_available(ts, gaps) for ts in index],
        index=index,
        dtype=bool,
    )
