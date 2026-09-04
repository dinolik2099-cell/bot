from __future__ import annotations

import json
from pathlib import Path
import pandas as pd


def build_research_manifest(audit_jsonl: str | Path, symbols: list[str],
                            interval: str, splits: list[dict]) -> dict:
    path = Path(audit_jsonl)
    if not path.exists():
        raise FileNotFoundError(path)

    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))

    selected = {s.upper() for s in symbols}
    datasets = [
        r for r in rows
        if r.get("symbol", "").upper() in selected and r.get("interval") == interval
    ]

    return {
        "manifest_version": "1.0",
        "interval": interval,
        "symbols": sorted(selected),
        "splits": splits,
        "datasets": datasets,
        "policy": {
            "missing_candles": "preserve_gap",
            "synthetic_candles": False,
            "lookahead": "execution_at_timestamp_uses_previous_completed_bar",
            "partial_dataset": "allowed_but_gap_periods_are_non_tradable",
        },
    }


def write_json(payload: dict, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".part")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
    return path
