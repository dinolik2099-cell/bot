from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from quantbot.data.binance_public import download_month
from quantbot.data.converter import convert_symbol_csv_to_parquet


def month_range(start: str, end: str):
    sy, sm = map(int, start.split("-"))
    ey, em = map(int, end.split("-"))
    y, m = sy, sm
    while (y, m) <= (ey, em):
        yield y, m
        m += 1
        if m == 13:
            y, m = y + 1, 1


def main():
    p = argparse.ArgumentParser(description="Build and validate QuantBot Binance historical dataset.")
    p.add_argument("--market", choices=["spot", "um", "cm"], default="um")
    p.add_argument("--symbols", nargs="+", required=True)
    p.add_argument("--intervals", nargs="+", default=["1h"])
    p.add_argument("--start", default="2021-01")
    p.add_argument("--end", default=f"{date.today().year}-{date.today().month:02d}")
    p.add_argument("--workers", type=int, default=8)
    p.add_argument("--checksum", action="store_true")
    p.add_argument("--raw", default=str(ROOT / "data/raw"))
    p.add_argument("--parquet", default=str(ROOT / "data/parquet"))
    p.add_argument("--report", default=str(ROOT / "data/reports/dataset_manifest.jsonl"))
    args = p.parse_args()

    tasks = []
    for symbol in args.symbols:
        for interval in args.intervals:
            for year, month in month_range(args.start, args.end):
                out_dir = Path(args.raw) / args.market / interval / symbol.upper()
                tasks.append((symbol, interval, year, month, out_dir))

    Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    results = []

    def worker(t):
        symbol, interval, year, month, out_dir = t
        return download_month(args.market, symbol, interval, year, month, out_dir,
                              verify_checksum=args.checksum)

    print(f"Tasks: {len(tasks)} | market={args.market} | workers={args.workers}", flush=True)
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(worker, t) for t in tasks]
        for fut in as_completed(futures):
            r = fut.result()
            d = r.__dict__
            results.append(d)
            print(f"{r.market} {r.symbol} {r.interval} {r.year}-{r.month:02d}: {r.status}", flush=True)

    with open(args.report, "a", encoding="utf-8") as fh:
        for r in results:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    failures = [r for r in results if r["status"] in {"NETWORK_ERROR", "HTTP_ERROR", "CORRUPTED"}]
    print(f"Download complete: {len(results)} tasks, {len(failures)} retry-worthy failures.", flush=True)

    # Convert only symbols for which at least one raw CSV exists.
    converted = 0
    for symbol in args.symbols:
        for interval in args.intervals:
            try:
                result = convert_symbol_csv_to_parquet(args.raw, args.parquet, args.market, symbol, interval)
                print(f"CONVERT {args.market} {symbol} {interval}: {result['quality']}", flush=True)
                converted += 1
            except FileNotFoundError:
                print(f"CONVERT {args.market} {symbol} {interval}: NO_DATA", flush=True)

    print(f"Parquet conversion attempts: {converted}", flush=True)
    if failures:
        print("Some failures were recorded. Re-run the same command to retry missing/failed months.", flush=True)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
