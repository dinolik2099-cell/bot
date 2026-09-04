from __future__ import annotations

import pandas as pd


def available_at_or_before(df: pd.DataFrame, asof: pd.Timestamp,
                           columns: list[str] | None = None) -> pd.Series:
    """
    Return the latest fully timestamped observation at or before `asof`.

    This helper is deliberately conservative: callers should use the previous
    completed candle for signals when execution occurs at the next candle.
    """
    if not isinstance(df.index, pd.DatetimeIndex):
        raise TypeError("DataFrame index must be a DatetimeIndex")

    ts = pd.Timestamp(asof)
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    else:
        ts = ts.tz_convert("UTC")

    eligible = df.loc[df.index <= ts]
    if eligible.empty:
        raise KeyError(f"No observation available at or before {ts}")

    row = eligible.iloc[-1]
    if columns is not None:
        return row[columns]
    return row


def signal_from_completed_bar(df: pd.DataFrame, execution_ts: pd.Timestamp,
                              columns: list[str] | None = None) -> pd.Series:
    """
    For execution at a candle timestamp, use the immediately preceding
    candle as the last fully completed bar.
    """
    ts = pd.Timestamp(execution_ts)
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    else:
        ts = ts.tz_convert("UTC")

    eligible = df.loc[df.index < ts]
    if eligible.empty:
        raise KeyError(f"No completed candle before execution time {ts}")

    row = eligible.iloc[-1]
    if columns is not None:
        return row[columns]
    return row
