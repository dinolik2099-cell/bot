from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .integration import (
    IntegrationDataset,
    effective_end,
    load_boundary_aware_symbol_with_parquet_fallback,
    load_boundary_lock,
    timestamp_in_non_tradable_gap,
)


@dataclass(frozen=True)
class ResearchWindow:
    name: str
    start: pd.Timestamp
    end: pd.Timestamp


@dataclass(frozen=True)
class ResearchDataset:
    boundary: IntegrationDataset
    windows: tuple[ResearchWindow, ...]
    effective_end: pd.Timestamp


def _utc(value) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        return ts.tz_localize("UTC")
    return ts.tz_convert("UTC")


def build_research_dataset(lock_path: str | Path) -> ResearchDataset:
    boundary = load_boundary_lock(lock_path)
    end = effective_end(boundary)

    windows = tuple(
        ResearchWindow(
            name=w.name,
            start=max(w.start, boundary.actual_start),
            end=min(w.end, end),
        )
        for w in boundary.windows
    )

    return ResearchDataset(
        boundary=boundary,
        windows=windows,
        effective_end=end,
    )


def load_research_frames(
    dataset: ResearchDataset,
    raw_root: str | Path,
    parquet_root: str | Path,
    symbols: list[str] | tuple[str, ...],
) -> tuple[dict[str, pd.DataFrame], dict[str, str]]:
    frames: dict[str, pd.DataFrame] = {}
    sources: dict[str, str] = {}

    for symbol in symbols:
        df, source = load_boundary_aware_symbol_with_parquet_fallback(
            raw_root,
            parquet_root,
            symbol,
            dataset.boundary.interval,
            market=dataset.boundary.market,
        )

        df = df.loc[
            (df.index >= dataset.boundary.actual_start)
            & (df.index <= dataset.effective_end)
        ].copy()

        if df.empty:
            raise ValueError(f"{symbol}: no rows inside research boundary")

        frames[symbol] = df
        sources[symbol] = source

    return frames, sources


def split_frame(
    dataset: ResearchDataset,
    frame: pd.DataFrame,
    window_name: str,
) -> pd.DataFrame:
    window = next(
        (w for w in dataset.windows if w.name == window_name),
        None,
    )
    if window is None:
        raise ValueError(f"Unknown research window: {window_name}")

    return frame.loc[
        (frame.index >= window.start)
        & (frame.index <= window.end)
    ].copy()


def split_frames(
    dataset: ResearchDataset,
    frames: dict[str, pd.DataFrame],
    window_name: str,
) -> dict[str, pd.DataFrame]:
    return {
        symbol: split_frame(dataset, frame, window_name)
        for symbol, frame in frames.items()
    }


def assert_no_future_window_leakage(
    dataset: ResearchDataset,
    frame: pd.DataFrame,
    window_name: str,
) -> None:
    window = next(
        (w for w in dataset.windows if w.name == window_name),
        None,
    )
    if window is None:
        raise ValueError(f"Unknown research window: {window_name}")

    if not frame.empty:
        first = _utc(frame.index[0])
        last = _utc(frame.index[-1])
        if first < window.start or last > window.end:
            raise AssertionError(
                f"{window_name}: frame outside authoritative boundaries"
            )


def assert_gap_policy(
    dataset: ResearchDataset,
    symbol: str,
    frame: pd.DataFrame,
) -> None:
    for ts in frame.index:
        if timestamp_in_non_tradable_gap(
            dataset.boundary, symbol, ts
        ):
            raise AssertionError(
                f"{symbol}: timestamp inside non-tradable gap: {ts}"
            )


def summarize_dataset(
    dataset: ResearchDataset,
    frames: dict[str, pd.DataFrame],
    sources: dict[str, str],
) -> dict:
    result = {
        "dataset_id": dataset.boundary.dataset_id,
        "market": dataset.boundary.market,
        "interval": dataset.boundary.interval,
        "effective_end": dataset.effective_end.isoformat(),
        "symbols": sorted(frames),
        "data_sources": sources,
        "windows": [],
    }

    for window in dataset.windows:
        entry = {
            "name": window.name,
            "start": window.start.isoformat(),
            "end": window.end.isoformat(),
            "per_symbol": {},
        }

        for symbol, frame in sorted(frames.items()):
            part = split_frame(dataset, frame, window.name)
            entry["per_symbol"][symbol] = {
                "rows": len(part),
                "first": part.index[0].isoformat() if len(part) else None,
                "last": part.index[-1].isoformat() if len(part) else None,
            }

        result["windows"].append(entry)

    return result
