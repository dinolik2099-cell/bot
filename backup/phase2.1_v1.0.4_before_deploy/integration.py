from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd


@dataclass(frozen=True)
class BoundaryWindow:
    name: str
    start: pd.Timestamp
    end: pd.Timestamp


@dataclass(frozen=True)
class GapRange:
    symbol: str
    previous: pd.Timestamp
    next: pd.Timestamp
    missing_bars: int

    @property
    def start_exclusive(self) -> pd.Timestamp:
        return self.previous

    @property
    def end_exclusive(self) -> pd.Timestamp:
        return self.next

    def contains_missing_timestamp(self, timestamp: pd.Timestamp) -> bool:
        ts = _utc(timestamp)
        return self.start_exclusive < ts < self.end_exclusive


@dataclass(frozen=True)
class IntegrationDataset:
    dataset_id: str
    market: str
    interval: str
    windows: tuple[BoundaryWindow, ...]
    gaps: tuple[GapRange, ...]
    actual_start: pd.Timestamp
    actual_end: pd.Timestamp
    requested_end: pd.Timestamp
    synthetic_candles: bool
    gap_policy: str
    lookahead_policy: str


def _utc(value) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        return ts.tz_localize("UTC")
    return ts.tz_convert("UTC")


def load_boundary_lock(path: str | Path) -> IntegrationDataset:
    p = Path(path)
    obj = json.loads(p.read_text(encoding="utf-8"))

    if obj.get("status") != "LOCKED":
        raise ValueError("Boundary lock is not LOCKED")

    required = [
        "dataset_id", "market", "interval", "requested_end",
        "actual_start", "actual_end", "splits", "gaps", "policies",
    ]
    missing = [key for key in required if key not in obj]
    if missing:
        raise ValueError(f"Boundary lock missing fields: {missing}")

    policies = obj["policies"]
    if policies.get("timezone") != "UTC":
        raise ValueError("Boundary timezone must be UTC")
    if policies.get("synthetic_candles") is not False:
        raise ValueError("Boundary policy synthetic_candles must be false")
    if policies.get("gap_policy") != "non_tradable":
        raise ValueError("Boundary policy gap_policy must be non_tradable")
    if policies.get("lookahead_policy") != (
        "execution_at_T_uses_information_strictly_before_T"
    ):
        raise ValueError("Unexpected lookahead policy")

    windows = tuple(
        BoundaryWindow(
            name=item["name"],
            start=_utc(item["start"]),
            end=_utc(item["end"]),
        )
        for item in obj["splits"]
    )

    expected_names = ("TRAIN", "VALIDATION", "OOS")
    if tuple(w.name for w in windows) != expected_names:
        raise ValueError(
            f"Unexpected split order/names: {[w.name for w in windows]}"
        )

    for i, window in enumerate(windows):
        if window.start > window.end:
            raise ValueError(f"Invalid split: {window.name}")
        if i and window.start != windows[i - 1].end + pd.Timedelta(microseconds=1):
            raise ValueError(f"Non-contiguous split boundary: {window.name}")

    gaps = tuple(
        GapRange(
            symbol=item["symbol"],
            previous=_utc(item["previous"]),
            next=_utc(item["next"]),
            missing_bars=int(item["missing_bars"]),
        )
        for item in obj["gaps"]
    )

    for gap in gaps:
        if gap.previous >= gap.next:
            raise ValueError(f"Invalid gap range: {gap}")
        if gap.missing_bars <= 0:
            raise ValueError(f"Invalid missing_bars: {gap}")

    actual_start = _utc(obj["actual_start"])
    actual_end = _utc(obj["actual_end"])
    requested_end = _utc(obj["requested_end"])

    if actual_start > actual_end:
        raise ValueError("actual_start > actual_end")

    if obj["market"] not in {"um", "spot"}:
        raise ValueError(f"Unsupported market: {obj['market']}")

    return IntegrationDataset(
        dataset_id=obj["dataset_id"],
        market=obj["market"],
        interval=obj["interval"],
        windows=windows,
        gaps=gaps,
        actual_start=actual_start,
        actual_end=actual_end,
        requested_end=requested_end,
        synthetic_candles=bool(policies["synthetic_candles"]),
        gap_policy=policies["gap_policy"],
        lookahead_policy=policies["lookahead_policy"],
    )


def load_parquet(path: str | Path) -> pd.DataFrame:
    df = pd.read_parquet(path)

    if not isinstance(df.index, pd.DatetimeIndex):
        if "open_time" in df.columns:
            df["open_time"] = pd.to_datetime(df["open_time"], utc=True)
            df = df.set_index("open_time")
        else:
            raise ValueError(f"No DatetimeIndex/open_time in {path}")

    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    else:
        df.index = df.index.tz_convert("UTC")

    if not df.index.is_monotonic_increasing:
        raise ValueError(f"Parquet index not sorted: {path}")
    if df.index.has_duplicates:
        raise ValueError(f"Duplicate timestamps: {path}")

    required = {"open", "high", "low", "close"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"{path}: missing columns {sorted(missing)}")

    return df


def slice_window(
    df: pd.DataFrame,
    window: BoundaryWindow,
    actual_start: pd.Timestamp,
    actual_end: pd.Timestamp,
) -> pd.DataFrame:
    start = max(window.start, actual_start)
    end = min(window.end, actual_end)

    if start > end:
        return df.iloc[0:0].copy()

    return df.loc[(df.index >= start) & (df.index <= end)].copy()


def expected_end(dataset: IntegrationDataset) -> pd.Timestamp:
    return min(dataset.requested_end, dataset.actual_end)


def find_gap_ranges(
    dataset: IntegrationDataset,
    symbol: str,
) -> tuple[GapRange, ...]:
    return tuple(g for g in dataset.gaps if g.symbol == symbol)


def timestamp_in_non_tradable_gap(
    dataset: IntegrationDataset,
    symbol: str,
    timestamp: pd.Timestamp,
) -> bool:
    ts = _utc(timestamp)
    return any(
        gap.contains_missing_timestamp(ts)
        for gap in find_gap_ranges(dataset, symbol)
    )


def validate_boundary(
    dataset: IntegrationDataset,
    frames: dict[str, pd.DataFrame],
) -> dict:
    errors = []

    symbols = tuple(sorted(frames))
    expected_symbols = tuple(
        sorted({gap.symbol for gap in dataset.gaps})
    )

    # The current Boundary Lock does not store a top-level symbol list.
    # Symbol membership is therefore validated by the caller against the
    # requested universe, while this function validates every supplied frame.

    for symbol, df in frames.items():
        if df.empty:
            errors.append(f"{symbol}: empty dataset")
            continue

        first = _utc(df.index[0])
        last = _utc(df.index[-1])

        if first < dataset.actual_start:
            errors.append(f"{symbol}: starts before actual_start")
        if last > expected_end(dataset):
            errors.append(f"{symbol}: extends beyond expected_end")

        for window in dataset.windows:
            part = slice_window(
                df, window, dataset.actual_start, dataset.actual_end
            )
            if part.empty:
                errors.append(f"{symbol}: empty {window.name} window")

        for gap in find_gap_ranges(dataset, symbol):
            if gap.previous < first or gap.next > last:
                # A gap can legitimately be outside a particular dataset
                # window, but if both endpoints are inside the dataset span,
                # the gap must remain a gap.
                continue

            between = df.loc[
                (df.index > gap.previous) & (df.index < gap.next)
            ]
            if not between.empty:
                errors.append(
                    f"{symbol}: gap unexpectedly filled between "
                    f"{gap.previous.isoformat()} and {gap.next.isoformat()}"
                )

    return {
        "ok": not errors,
        "errors": errors,
        "dataset_id": dataset.dataset_id,
        "symbols": list(symbols),
        "actual_start": dataset.actual_start.isoformat(),
        "actual_end": dataset.actual_end.isoformat(),
        "requested_end": dataset.requested_end.isoformat(),
        "effective_end": expected_end(dataset).isoformat(),
        "gap_count": len(dataset.gaps),
    }


def build_split_summary(
    dataset: IntegrationDataset,
    frames: dict[str, pd.DataFrame],
) -> list[dict]:
    result = []
    for window in dataset.windows:
        per_symbol = {}
        total_rows = 0
        for symbol, df in sorted(frames.items()):
            part = slice_window(
                df, window, dataset.actual_start, dataset.actual_end
            )
            rows = len(part)
            total_rows += rows
            per_symbol[symbol] = {
                "rows": rows,
                "first": part.index[0].isoformat() if rows else None,
                "last": part.index[-1].isoformat() if rows else None,
            }

        result.append({
            "name": window.name,
            "start": window.start.isoformat(),
            "end": window.end.isoformat(),
            "rows": total_rows,
            "per_symbol": per_symbol,
        })
    return result
