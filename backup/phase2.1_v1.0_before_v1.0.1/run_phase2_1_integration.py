from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from quantbot.research.integration import (
    load_boundary_lock,
    load_parquet,
    validate_boundary,
)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--lock", required=True)
    p.add_argument("--parquet-root", required=True)
    p.add_argument("--market", default="um")
    p.add_argument("--interval", default="1h")
    p.add_argument("--symbols", nargs="+", required=True)
    p.add_argument(
        "--report",
        default="data/reports/phase2_1_integration.json",
    )
    args = p.parse_args()

    dataset = load_boundary_lock(args.lock)

    if dataset.market != args.market:
        raise SystemExit(
            f"MARKET_MISMATCH: lock={dataset.market} cli={args.market}"
        )
    if dataset.interval != args.interval:
        raise SystemExit(
            f"INTERVAL_MISMATCH: lock={dataset.interval} cli={args.interval}"
        )
    if tuple(sorted(args.symbols)) != tuple(sorted(dataset.symbols)):
        raise SystemExit("SYMBOL_MISMATCH: CLI symbols differ from lock")

    root = Path(args.parquet_root)
    frames = {}
    missing = []

    for symbol in dataset.symbols:
        path = root / args.market / args.interval / f"{symbol}.parquet"
        if not path.exists():
            missing.append(str(path))
            continue
        frames[symbol] = load_parquet(path)

    if missing:
        raise SystemExit(
            "MISSING_PARQUET:\n" + "\n".join(missing)
        )

    validation = validate_boundary(dataset, frames)
    report = {
        "status": "PASS" if validation["ok"] else "FAIL",
        "dataset_id": dataset.dataset_id,
        "market": dataset.market,
        "interval": dataset.interval,
        "symbols": list(dataset.symbols),
        "actual_start": dataset.actual_start.isoformat(),
        "actual_end": dataset.actual_end.isoformat(),
        "requested_end": dataset.requested_end.isoformat(),
        "boundary_validation": validation,
        "frames": {
            symbol: {
                "rows": len(df),
                "first": df.index[0].isoformat(),
                "last": df.index[-1].isoformat(),
            }
            for symbol, df in frames.items()
        },
    }

    out = Path(args.report)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print("=" * 72)
    print("QuantBot PHASE 2.1 Boundary × Backtest Integration")
    print("=" * 72)
    print(f"status:        {report['status']}")
    print(f"dataset_id:    {dataset.dataset_id}")
    print(f"actual_end:    {dataset.actual_end.isoformat()}")
    print(f"requested_end: {dataset.requested_end.isoformat()}")
    print(f"symbols:       {len(frames)}")
    print(f"report:        {out}")

    if not validation["ok"]:
        for error in validation["errors"]:
            print(f"ERROR: {error}")
        raise SystemExit(1)

    print("PHASE2_1_INTEGRATION_OK")


if __name__ == "__main__":
    main()
