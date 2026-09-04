from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from quantbot.data.audit import audit_tree, write_jsonl


def main():
    p = argparse.ArgumentParser(description="Audit QuantBot historical datasets.")
    p.add_argument("--market", choices=["spot", "um", "cm"], default="um")
    p.add_argument("--interval", required=True)
    p.add_argument("--symbols", nargs="+")
    p.add_argument("--raw", default=str(ROOT / "data/raw"))
    p.add_argument("--report", default=str(ROOT / "data/reports/dataset_audit.jsonl"))
    args = p.parse_args()

    reports = audit_tree(args.raw, args.market, args.interval, args.symbols)

    print("=" * 72)
    print(f"QuantBot Dataset Audit | market={args.market} | interval={args.interval}")
    print("=" * 72)

    for r in reports:
        print(
            f"{r.symbol:10s} "
            f"status={r.status:7s} "
            f"rows={r.rows:7,d} "
            f"missing={r.missing_bars:5,d} "
            f"gaps={r.gap_count:3d} "
            f"duplicates={r.duplicate_timestamps:3d} "
            f"invalid_ohlc={r.invalid_ohlc:3d}"
        )
        if r.gaps:
            for g in r.gaps:
                print(
                    f"  GAP: {g.previous} -> {g.next} "
                    f"missing_bars={g.missing_bars}"
                )

    path = write_jsonl(reports, args.report)
    print("-" * 72)
    print(f"Report: {path}")
    print(f"Datasets audited: {len(reports)}")

    invalid = [r for r in reports if r.status in {"INVALID", "NO_DATA"}]
    print(f"Blocking datasets: {len(invalid)}")

    return 2 if invalid else 0


if __name__ == "__main__":
    raise SystemExit(main())
