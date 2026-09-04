from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from quantbot.backtest.engine_v2 import BacktestEngine
from quantbot.backtest.costs import CostModel
from quantbot.research.integration import find_gap_ranges
from quantbot.research.runner import (
    build_research_dataset,
    load_research_frames,
    split_frame,
)
from quantbot.research.evaluation import evaluate_strategy
from quantbot.strategies.models import (
    trend_breakout,
    trend_pullback,
    volatility_breakout,
    mean_reversion,
)

SYMBOLS = (
    "BTCUSDT",
    "ETHUSDT",
    "BNBUSDT",
    "SOLUSDT",
    "XRPUSDT",
    "DOGEUSDT",
)

STRATEGIES: dict[str, Callable[..., Any]] = {
    "trend_breakout": trend_breakout,
    "trend_pullback": trend_pullback,
    "volatility_breakout": volatility_breakout,
    "mean_reversion": mean_reversion,
}

DEFAULT_INITIAL_EQUITY = 10_000.0
DEFAULT_RISK_FRACTION = 0.01
DEFAULT_POSITION_FRACTION = 1.0
DEFAULT_MAX_POSITIONS = 1
DEFAULT_MAX_RISK_FRACTION = 0.01


def _gap_indices(dataset, symbol: str) -> set:
    """Return the actual missing timestamps represented by locked gaps."""
    out = set()
    for gap in find_gap_ranges(dataset.boundary, symbol):
        step = (gap.next - gap.previous) / (gap.missing_bars + 1)
        ts = gap.previous + step
        for _ in range(gap.missing_bars):
            out.add(ts)
            ts += step
    return out


def _engine(dataset, symbol: str) -> BacktestEngine:
    return BacktestEngine(
        initial_equity=DEFAULT_INITIAL_EQUITY,
        cost_model=CostModel(
            fee_rate=0.0004,
            slippage_bps=2.0,
            funding_rate_per_8h=0.0,
        ),
        max_position_fraction=DEFAULT_POSITION_FRACTION,
        max_risk_fraction=DEFAULT_MAX_RISK_FRACTION,
        max_positions=DEFAULT_MAX_POSITIONS,
        gap_indices={symbol: _gap_indices(dataset, symbol)},
    )


def _result_record(item, strategy_name: str, source: str) -> dict[str, Any]:
    result = item.backtest
    metrics = result.metrics()
    return {
        "strategy": strategy_name,
        "symbol": item.symbol,
        "window": item.window,
        "rows": item.rows,
        "first_timestamp": item.first_timestamp,
        "last_timestamp": item.last_timestamp,
        "data_source": source,
        "initial_equity": result.initial_equity,
        "final_equity": result.final_equity,
        "halted": getattr(result, "halted", False),
        "rejected_signals": result.rejected_signals,
        "skipped_gap_bars": result.skipped_gap_bars,
        "gap_bars_seen": result.gap_bars_seen,
        "trades": len(result.trades),
        "metrics": metrics,
    }


def run_baseline(
    *,
    lock_path: str | Path,
    raw_root: str | Path,
    parquet_root: str | Path,
    symbols: tuple[str, ...] = SYMBOLS,
) -> dict[str, Any]:
    dataset = build_research_dataset(lock_path)
    frames, sources = load_research_frames(
        dataset,
        raw_root,
        parquet_root,
        list(symbols),
    )

    records: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []

    for strategy_name, strategy in STRATEGIES.items():
        for symbol in symbols:
            source = sources[symbol]
            for window in (w.name for w in dataset.windows):
                frame = split_frame(dataset, frames[symbol], window)
                if frame.empty:
                    errors.append({
                        "strategy": strategy_name,
                        "symbol": symbol,
                        "window": window,
                        "error": "empty research window",
                    })
                    continue

                try:
                    item = evaluate_strategy(
                        symbol=symbol,
                        window=window,
                        frame=frame,
                        strategy=strategy,
                        engine=_engine(dataset, symbol),
                        params=None,
                        risk_fraction=DEFAULT_RISK_FRACTION,
                        position_fraction=DEFAULT_POSITION_FRACTION,
                        tag=f"baseline:{strategy_name}:{symbol}:{window}",
                    )
                    records.append(_result_record(item, strategy_name, source))
                except Exception as exc:
                    errors.append({
                        "strategy": strategy_name,
                        "symbol": symbol,
                        "window": window,
                        "error": repr(exc),
                    })

    expected = len(STRATEGIES) * len(symbols) * len(dataset.windows)
    status = "PASS" if len(records) == expected and not errors else "FAIL"

    return {
        "phase": "2.2.2",
        "mode": "multi_strategy_multi_asset_baseline",
        "status": status,
        "dataset_id": dataset.boundary.dataset_id,
        "market": dataset.boundary.market,
        "interval": dataset.boundary.interval,
        "actual_end": dataset.effective_end.isoformat(),
        "symbols": list(symbols),
        "strategies": list(STRATEGIES),
        "windows": [w.name for w in dataset.windows],
        "expected_cells": expected,
        "completed_cells": len(records),
        "errors": errors,
        "baseline_parameters": {
            "initial_equity": DEFAULT_INITIAL_EQUITY,
            "risk_fraction": DEFAULT_RISK_FRACTION,
            "position_fraction": DEFAULT_POSITION_FRACTION,
            "max_positions": DEFAULT_MAX_POSITIONS,
            "max_risk_fraction": DEFAULT_MAX_RISK_FRACTION,
            "fee_rate": 0.0004,
            "slippage_bps": 2.0,
            "funding_rate_per_8h": 0.0,
            "strategy_parameters": "model defaults; no optimization",
        },
        "data_sources": sources,
        "records": records,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--lock",
        default=str(ROOT / "data/reports/research_boundary_lock.json"),
    )
    parser.add_argument("--raw-root", default=str(ROOT / "data/raw"))
    parser.add_argument("--parquet-root", default=str(ROOT / "data/parquet"))
    parser.add_argument(
        "--symbols",
        nargs="+",
        default=list(SYMBOLS),
    )
    parser.add_argument(
        "--output",
        default=str(ROOT / "data/reports/phase2_2_2_baseline.json"),
    )
    args = parser.parse_args()

    symbols = tuple(s.upper() for s in args.symbols)
    unknown = sorted(set(symbols) - set(SYMBOLS))
    if unknown:
        raise SystemExit(f"UNKNOWN_SYMBOLS: {unknown}")

    report = run_baseline(
        lock_path=args.lock,
        raw_root=args.raw_root,
        parquet_root=args.parquet_root,
        symbols=symbols,
    )

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )

    print("=" * 72)
    print("QuantBot PHASE 2.2.2 Multi-Strategy Multi-Asset Baseline")
    print("=" * 72)
    print(f"status:        {report['status']}")
    print(f"dataset_id:    {report['dataset_id']}")
    print(f"strategies:    {len(report['strategies'])}")
    print(f"symbols:       {len(report['symbols'])}")
    print(f"windows:       {len(report['windows'])}")
    print(f"expected_cells:{report['expected_cells']}")
    print(f"completed:     {report['completed_cells']}")
    print(f"errors:        {len(report['errors'])}")
    print(f"output:        {output}")
    print("-" * 72)

    for record in report["records"]:
        m = record["metrics"]
        print(
            f"{record['strategy']:20s} "
            f"{record['symbol']:9s} "
            f"{record['window']:10s} "
            f"return={m['total_return']:+.6f} "
            f"dd={m['max_drawdown']:.6f} "
            f"pf={m['profit_factor']:.6f} "
            f"trades={m['trades']:4d}"
        )

    if report["errors"]:
        print("-" * 72)
        print("ERRORS")
        for error in report["errors"]:
            print(
                f"{error['strategy']} {error['symbol']} "
                f"{error['window']}: {error['error']}"
            )

    print("=" * 72)
    print("PHASE2_2_2_BASELINE_OK" if report["status"] == "PASS" else "PHASE2_2_2_BASELINE_FAILED")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
