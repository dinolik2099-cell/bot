from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from quantbot.research.boundary import load_audit, lock_boundaries, write_lock


def make_id(market, symbols, interval, audit_path):
    payload = {
        "market": market,
        "symbols": sorted(s.upper() for s in symbols),
        "interval": interval,
        "audit_sha256": hashlib.sha256(Path(audit_path).read_bytes()).hexdigest(),
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()[:12].upper()
    return f"{market.upper()}_{interval.upper()}_{digest}"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--audit", default=str(ROOT / "data/reports/dataset_audit.jsonl"))
    p.add_argument("--market", default="um")
    p.add_argument("--interval", default="1h")
    p.add_argument("--symbols", nargs="+", required=True)
    p.add_argument("--train-end", default="2024-12-31T23:00:00Z")
    p.add_argument("--validation-end", default="2025-12-31T23:00:00Z")
    p.add_argument("--oos-end", default="2026-08-31T23:00:00Z")
    p.add_argument("--output", default=str(ROOT / "data/reports/research_boundary_lock.json"))
    args = p.parse_args()

    rows = load_audit(args.audit, args.symbols, args.market, args.interval)
    missing = {s.upper() for s in args.symbols} - {r["symbol"].upper() for r in rows}
    if missing:
        raise SystemExit(f"MISSING_AUDIT_DATASETS: {sorted(missing)}")

    dataset_id = make_id(args.market, args.symbols, args.interval, args.audit)
    lock = lock_boundaries(
        rows, dataset_id, args.interval,
        args.train_end, args.validation_end, args.oos_end
    )
    out = write_lock(lock, args.output)

    print("=" * 72)
    print("QuantBot Research Boundary Lock")
    print("=" * 72)
    print(f"status:        {lock.status}")
    print(f"dataset_id:    {lock.dataset_id}")
    print(f"actual_start:  {lock.actual_start}")
    print(f"actual_end:    {lock.actual_end}")
    print(f"requested_end: {lock.requested_end}")
    print()
    for s in lock.splits:
        print(f"{s.name:12s} {s.start} -> {s.end}")
    print()
    print(f"gap_ranges:    {len(lock.gaps)}")
    for g in lock.gaps:
        print(f"  {g['symbol']}: {g['previous']} -> {g['next']} missing={g['missing_bars']}")
    print("-" * 72)
    print(f"LOCK_OK: {out}")


if __name__ == "__main__":
    raise SystemExit(main())
