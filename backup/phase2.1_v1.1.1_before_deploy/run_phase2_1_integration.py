from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from quantbot.research.integration import (
    build_split_summary,
    effective_end,
    load_boundary_lock,
    load_symbol_with_parquet_fallback,
    validate_boundary,
)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--lock", required=True)
    p.add_argument("--raw-root", default="data/raw")
    p.add_argument("--parquet-root", default="data/parquet")
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

    frames = {}
    sources = {}
    errors = []

    for symbol in args.symbols:
        try:
            df, source = load_symbol_with_parquet_fallback(
                args.raw_root,
                args.parquet_root,
                symbol,
                args.interval,
                market=args.market,
                validate=True,
            )
            frames[symbol] = df
            sources[symbol] = source
        except Exception as exc:
            errors.append(f"{symbol}: {exc!r}")

    if errors:
        print("DATA_LOAD_ERRORS:")
        for error in errors:
            print(error)
        raise SystemExit(1)

    gap_symbols = {gap.symbol for gap in dataset.gaps}
    if not gap_symbols.issubset(set(args.symbols)):
        raise SystemExit(
            "GAP_SYMBOL_MISMATCH: boundary gap symbol is not in CLI universe"
        )

    validation = validate_boundary(dataset, frames)
    summary = build_split_summary(dataset, frames)
    end = effective_end(dataset)

    report = {
        "status": "PASS" if validation["ok"] else "FAIL",
        "dataset_id": dataset.dataset_id,
        "market": dataset.market,
        "interval": dataset.interval,
        "symbols": list(args.symbols),
        "data_sources": sources,
        "actual_start": dataset.actual_start.isoformat(),
        "actual_end": dataset.actual_end.isoformat(),
        "requested_end": dataset.requested_end.isoformat(),
        "effective_end": end.isoformat(),
        "boundary_validation": validation,
        "splits": summary,
        "gaps": [
            {
                "symbol": g.symbol,
                "previous": g.previous.isoformat(),
                "next": g.next.isoformat(),
                "missing_bars": g.missing_bars,
            }
            for g in dataset.gaps
        ],
        "policies": {
            "synthetic_candles": dataset.synthetic_candles,
            "gap_policy": dataset.gap_policy,
            "lookahead_policy": dataset.lookahead_policy,
        },
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
    print("QuantBot PHASE 2.1 Canonical Data Loader Integration V1.1")
    print("=" * 72)
    print(f"status:        {report['status']}")
    print(f"dataset_id:    {dataset.dataset_id}")
    print(f"actual_end:    {dataset.actual_end.isoformat()}")
    print(f"requested_end: {dataset.requested_end.isoformat()}")
    print(f"effective_end: {end.isoformat()}")
    print(f"symbols:       {len(frames)}")
    print(f"gaps:          {len(dataset.gaps)}")
    print("data_sources:")
    for symbol in args.symbols:
        print(f"  {symbol:<10} {sources[symbol]}")

    for split in summary:
        print(
            f"{split['name']:<12} rows={split['rows']:>8,} "
            f"{split['start']} -> {split['end']}"
        )

    if not validation["ok"]:
        for error in validation["errors"]:
            print(f"ERROR: {error}")
        raise SystemExit(1)

    print("PHASE2_1_V1_1_CANONICAL_LOADER_INTEGRATION_OK")


if __name__ == "__main__":
    main()
