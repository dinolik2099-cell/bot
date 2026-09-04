from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
import json
import pandas as pd

from .load import normalize_kline_frame
from .validator import INTERVAL_MS, validate_frame


@dataclass
class Gap:
    previous: str
    next: str
    missing_bars: int

    def to_dict(self):
        return asdict(self)


@dataclass
class DatasetAudit:
    market: str
    symbol: str
    interval: str
    files: int
    rows: int
    first_timestamp: str | None
    last_timestamp: str | None
    expected_bars: int | None
    actual_bars: int
    missing_bars: int
    gap_count: int
    gaps: list[Gap]
    duplicate_timestamps: int
    non_monotonic: int
    invalid_ohlc: int
    non_positive_prices: int
    negative_volume: int
    nan_core: int
    status: str
    notes: list[str]

    def to_dict(self):
        d = asdict(self)
        d["gaps"] = [g.to_dict() if isinstance(g, Gap) else g for g in self.gaps]
        return d


def _status(report, gap_count: int) -> str:
    if report.rows == 0:
        return "NO_DATA"
    if report.duplicate_timestamps or report.non_monotonic or report.invalid_ohlc:
        return "INVALID"
    if gap_count:
        return "PARTIAL"
    return "READY"


def audit_symbol(raw_root: str | Path, market: str, symbol: str, interval: str) -> DatasetAudit:
    root = Path(raw_root) / market / interval / symbol.upper()
    files = sorted(root.glob("*.csv"))
    if not files:
        return DatasetAudit(
            market, symbol.upper(), interval, 0, 0, None, None, None, 0, 0, 0, [],
            0, 0, 0, 0, 0, 0, "NO_DATA", [f"directory not found or contains no CSV: {root}"]
        )

    frames = [normalize_kline_frame(pd.read_csv(f, header=None)) for f in files]
    df = pd.concat(frames).sort_index()
    duplicate_before = int(df.index.duplicated().sum())
    df = df[~df.index.duplicated(keep="first")]

    report = validate_frame(df, interval)
    idx = pd.DatetimeIndex(df.index)

    gaps: list[Gap] = []
    expected_ms = INTERVAL_MS.get(interval)
    if expected_ms and len(idx) > 1:
        expected_delta = pd.Timedelta(milliseconds=expected_ms)
        diffs = idx.to_series().diff()
        for ts, delta in diffs[diffs > expected_delta * 1.01].items():
            missing = max(0, int(round(delta / expected_delta)) - 1)
            gaps.append(Gap((ts - delta).isoformat(), ts.isoformat(), missing))

    missing_bars = sum(g.missing_bars for g in gaps)
    expected_bars = None
    if expected_ms and len(idx) > 1:
        span_ms = (idx[-1] - idx[0]).total_seconds() * 1000
        expected_bars = int(round(span_ms / expected_ms)) + 1

    notes = []
    if gaps:
        notes.append("Missing historical intervals are preserved as gaps; no synthetic candles are created.")
    if idx.min().month == 1 and idx.min().day == 1:
        notes.append("Dataset begins on a calendar-year boundary; this is not proof of market listing date.")

    return DatasetAudit(
        market=market,
        symbol=symbol.upper(),
        interval=interval,
        files=len(files),
        rows=len(df),
        first_timestamp=idx.min().isoformat(),
        last_timestamp=idx.max().isoformat(),
        expected_bars=expected_bars,
        actual_bars=len(df),
        missing_bars=missing_bars,
        gap_count=len(gaps),
        gaps=gaps,
        duplicate_timestamps=duplicate_before + report.duplicate_timestamps,
        non_monotonic=report.non_monotonic,
        invalid_ohlc=report.invalid_ohlc,
        non_positive_prices=report.non_positive_prices,
        negative_volume=report.negative_volume,
        nan_core=report.nan_core,
        status=_status(report, len(gaps)),
        notes=notes,
    )


def audit_tree(raw_root: str | Path, market: str, interval: str, symbols: list[str] | None = None) -> list[DatasetAudit]:
    base = Path(raw_root) / market / interval
    if symbols:
        names = [s.upper() for s in symbols]
    else:
        names = sorted(p.name for p in base.iterdir() if p.is_dir()) if base.exists() else []

    return [audit_symbol(raw_root, market, s, interval) for s in names]


def write_jsonl(reports: list[DatasetAudit], path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".part")
    with tmp.open("w", encoding="utf-8") as f:
        for report in reports:
            f.write(json.dumps(report.to_dict(), ensure_ascii=False) + "\n")
    tmp.replace(path)
    return path
