from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
import json
import pandas as pd


@dataclass(frozen=True)
class Boundary:
    name: str
    start: str
    end: str
    rows: int
    available: bool

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class BoundaryLock:
    dataset_id: str
    market: str
    interval: str
    requested_end: str
    actual_start: str | None
    actual_end: str | None
    splits: tuple[Boundary, ...]
    gaps: tuple[dict, ...]
    policies: dict
    status: str

    def to_dict(self):
        d = asdict(self)
        d["splits"] = [x.to_dict() for x in self.splits]
        return d


def _ts(value: str) -> pd.Timestamp:
    t = pd.Timestamp(value)
    if t.tzinfo is None:
        return t.tz_localize("UTC")
    return t.tz_convert("UTC")


def _bar_floor(ts: pd.Timestamp, interval: str) -> pd.Timestamp:
    # Current Phase 1-C.1 targets 1h research. Keep explicit rather than
    # silently guessing for unsupported intervals.
    if interval == "1h":
        return ts.floor("h")
    raise ValueError(f"Boundary locking for interval {interval!r} is not implemented")


def load_audit(audit_jsonl: str | Path, symbols: list[str], market: str, interval: str) -> list[dict]:
    selected = {s.upper() for s in symbols}
    path = Path(audit_jsonl)
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        if (
            item.get("market") == market
            and item.get("interval") == interval
            and item.get("symbol", "").upper() in selected
        ):
            rows.append(item)
    return rows


def lock_boundaries(audit_rows: list[dict], dataset_id: str,
                    interval: str,
                    train_end: str,
                    validation_end: str,
                    requested_oos_end: str) -> BoundaryLock:
    if not audit_rows:
        raise ValueError("No audited datasets supplied")

    actual_start = min(_ts(r["first_timestamp"]) for r in audit_rows)
    actual_end = max(_ts(r["last_timestamp"]) for r in audit_rows)

    train_end_ts = _bar_floor(_ts(train_end), interval)
    validation_end_ts = _bar_floor(_ts(validation_end), interval)
    requested_oos_end_ts = _bar_floor(_ts(requested_oos_end), interval)
    effective_oos_end = min(actual_end, requested_oos_end_ts)

    if not (actual_start <= train_end_ts < validation_end_ts < effective_oos_end):
        raise ValueError(
            "Invalid effective research boundaries: "
            f"actual_start={actual_start}, train_end={train_end_ts}, "
            f"validation_end={validation_end_ts}, effective_oos_end={effective_oos_end}"
        )

    # Boundaries are expressed on actual candle timestamps. Validation starts
    # at the next bar after train end; OOS starts at the next bar after validation.
    train_start = actual_start
    validation_start = train_end_ts + pd.Timedelta(hours=1)
    oos_start = validation_end_ts + pd.Timedelta(hours=1)

    split_rows = (
        Boundary("TRAIN", train_start.isoformat(), train_end_ts.isoformat(), 0, True),
        Boundary("VALIDATION", validation_start.isoformat(), validation_end_ts.isoformat(), 0, True),
        Boundary("OOS", oos_start.isoformat(), effective_oos_end.isoformat(), 0, True),
    )

    gaps = []
    for r in audit_rows:
        for g in r.get("gaps", []):
            gaps.append({
                "symbol": r["symbol"],
                "previous": g["previous"],
                "next": g["next"],
                "missing_bars": g["missing_bars"],
            })

    return BoundaryLock(
        dataset_id=dataset_id,
        market=audit_rows[0]["market"],
        interval=interval,
        requested_end=requested_oos_end_ts.isoformat(),
        actual_start=actual_start.isoformat(),
        actual_end=actual_end.isoformat(),
        splits=split_rows,
        gaps=tuple(gaps),
        policies={
            "timezone": "UTC",
            "boundary_unit": "completed_candle_timestamp",
            "synthetic_candles": False,
            "gap_policy": "non_tradable",
            "oos_end_policy": "min(requested_end, actual_dataset_end)",
            "lookahead_policy": "execution_at_T_uses_information_strictly_before_T",
        },
        status="LOCKED",
    )


def write_lock(lock: BoundaryLock, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".part")
    tmp.write_text(json.dumps(lock.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
    return path
