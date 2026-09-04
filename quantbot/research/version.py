from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
import hashlib
import json
import platform
import sys
from datetime import datetime, timezone


@dataclass(frozen=True)
class DatasetVersion:
    dataset_id: str
    created_at_utc: str
    market: str
    symbols: tuple[str, ...]
    intervals: tuple[str, ...]
    raw_root: str
    parquet_root: str
    audit_report: str
    split_config: dict
    code_version: str = "QuantBot-ResearchFoundation-1.0"

    def to_dict(self):
        return asdict(self)


def sha256_file(path: str | Path, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        while chunk := f.read(chunk_size):
            h.update(chunk)
    return h.hexdigest()


def make_dataset_id(market: str, symbols: list[str], intervals: list[str],
                    split_config: dict, audit_report: str) -> str:
    payload = {
        "market": market,
        "symbols": sorted(s.upper() for s in symbols),
        "intervals": sorted(intervals),
        "split_config": split_config,
        "audit_report": audit_report,
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()[:12].upper()
    return f"{market.upper()}_{'_'.join(sorted(i.upper() for i in intervals))}_{digest}"


def environment_snapshot() -> dict:
    return {
        "python": sys.version,
        "platform": platform.platform(),
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
    }


def write_manifest(version: DatasetVersion, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = version.to_dict()
    payload["environment"] = environment_snapshot()
    tmp = path.with_suffix(path.suffix + ".part")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
    return path
