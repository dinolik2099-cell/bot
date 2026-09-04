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
class IntegrationDataset:
    dataset_id: str
    market: str
    interval: str
    symbols: tuple[str, ...]
    windows: tuple[BoundaryWindow, ...]
    actual_start: pd.Timestamp
    actual_end: pd.Timestamp
    requested_end: pd.Timestamp


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

    dataset_id = obj.get("dataset_id")
    if not dataset_id:
        raise ValueError("Missing dataset_id")

    symbols = tuple(obj.get("symbols", []))
    if not symbols:
        raise ValueError("Missing symbols")

    windows = []
    for item in obj.get("windows", []):
        windows.append(
            BoundaryWindow(
                name=item["name"],
                start=_utc(item["start"]),
                end=_utc(item["end"]),
            )
        )

    # Backward-compatible with the current lock format, whose windows are
    # represented as top-level TRAIN/VALIDATION/OOS objects.
    if not windows:
        for name in ("TRAIN", "VALIDATION", "OOS"):
            item = obj.get(name)
            if item:
                windows.append(
                    BoundaryWindow(
                        name=name,
                        start=_utc(item["start"]),
                        end=_utc(item["end"]),
                    )
                )

    if not windows:
        raise ValueError("No boundary windows found")

    return IntegrationDataset(
        dataset_id=dataset_id,
        market=obj["market"],
        interval=obj["interval"],
        symbols=symbols,
        windows=tuple(windows),
        actual_start=_utc(obj["actual_start"]),
        actual_end=_utc(obj["actual_end"]),
        requested_end=_utc(obj["requested_end"]),
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


def validate_boundary(
    dataset: IntegrationDataset,
    frames: dict[str, pd.DataFrame],
) -> dict:
    errors = []

    if set(frames) != set(dataset.symbols):
        errors.append(
            f"symbols mismatch: expected={sorted(dataset.symbols)} "
            f"actual={sorted(frames)}"
        )

    for symbol, df in frames.items():
        if df.empty:
            errors.append(f"{symbol}: empty dataset")
            continue

        if _utc(df.index[0]) < dataset.actual_start:
            errors.append(f"{symbol}: starts before actual_start")

        if _utc(df.index[-1]) > dataset.actual_end:
            errors.append(f"{symbol}: extends beyond actual_end")

        for window in dataset.windows:
            part = slice_window(
                df, window, dataset.actual_start, dataset.actual_end
            )
            if part.empty:
                errors.append(f"{symbol}: empty {window.name} window")

    return {
        "ok": not errors,
        "errors": errors,
        "dataset_id": dataset.dataset_id,
        "actual_start": dataset.actual_start.isoformat(),
        "actual_end": dataset.actual_end.isoformat(),
        "requested_end": dataset.requested_end.isoformat(),
    }
