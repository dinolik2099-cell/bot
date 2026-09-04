from __future__ import annotations

import argparse
import itertools
import json
import sys
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from quantbot.backtest.engine_v2 import BacktestEngine
from quantbot.backtest.costs import CostModel
from quantbot.research.integration import find_gap_ranges
from quantbot.research.runner import build_research_dataset, load_research_frames, split_frame
from quantbot.research.evaluation import evaluate_strategy
from quantbot.strategies.models import trend_breakout, trend_pullback, volatility_breakout

SYMBOLS = ("BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT")
STRATEGIES: dict[str, Callable[..., Any]] = {
    "trend_breakout": trend_breakout,
    "trend_pullback": trend_pullback,
    "volatility_breakout": volatility_breakout,
}

# Controlled first-pass grids. No mean_reversion and no OOS-driven search.
PARAM_GRIDS: dict[str, dict[str, tuple[Any, ...]]] = {
    "trend_breakout": {
        "lookback": (20, 40, 60),
        "stop_atr": (1.5, 2.0, 2.5),
        "reward_r": (2.0, 3.0, 4.0),
    },
    "trend_pullback": {
        "ema_fast": (10, 20),
        "ema_slow": (50, 80, 120),
        "stop_atr": (1.5, 2.0, 2.5),
        "reward_r": (2.0, 3.0),
    },
    "volatility_breakout": {
        "range_lookback": (10, 20, 40),
        "stop_atr": (1.5, 2.0, 2.5),
        "reward_r": (2.0, 3.0, 4.0),
    },
}

INITIAL_EQUITY = 10_000.0
RISK_FRACTION = 0.01
POSITION_FRACTION = 1.0
MAX_POSITIONS = 1
MAX_RISK_FRACTION = 0.01
TOP_K_TRAIN = 3


def _gap_indices(dataset, symbol: str) -> set:
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
        initial_equity=INITIAL_EQUITY,
        cost_model=CostModel(fee_rate=0.0004, slippage_bps=2.0, funding_rate_per_8h=0.0),
        max_position_fraction=POSITION_FRACTION,
        max_risk_fraction=MAX_RISK_FRACTION,
        max_positions=MAX_POSITIONS,
        gap_indices={symbol: _gap_indices(dataset, symbol)},
    )


def _grid(strategy_name: str) -> list[dict[str, Any]]:
    grid = PARAM_GRIDS[strategy_name]
    keys = tuple(grid)
    return [dict(zip(keys, values)) for values in itertools.product(*(grid[k] for k in keys))]


def _score(metrics: dict[str, Any]) -> float:
    # Transparent, fixed score used only for research ranking:
    # reward return, penalize drawdown. OOS never enters this calculation.
    return float(metrics["total_return"]) - float(metrics["max_drawdown"])


def _evaluate(dataset, frame, strategy_name, strategy, symbol, window, params):
    item = evaluate_strategy(
        symbol=symbol,
        window=window,
        frame=frame,
        strategy=strategy,
        engine=_engine(dataset, symbol),
        params=params,
        risk_fraction=RISK_FRACTION,
        position_fraction=POSITION_FRACTION,
        tag=f"phase2.3:{strategy_name}:{symbol}:{window}",
    )
    metrics = item.backtest.metrics()
    return {
        "strategy": strategy_name,
        "symbol": symbol,
        "window": window,
        "params": dict(params),
        "rows": item.rows,
        "first_timestamp": item.first_timestamp,
        "last_timestamp": item.last_timestamp,
        "metrics": metrics,
        "score": _score(metrics),
    }


def _rank_key(record: dict[str, Any]):
    m = record["metrics"]
    return (
        record["score"],
        float(m["profit_factor"]),
        float(m["total_return"]),
        -float(m["max_drawdown"]),
        int(m["trades"]),
    )


def run_parameter_research(*, lock_path, raw_root, parquet_root, symbols=SYMBOLS, top_k=TOP_K_TRAIN):
    dataset = build_research_dataset(lock_path)
    frames, sources = load_research_frames(dataset, raw_root, parquet_root, list(symbols))
    windows = [w.name for w in dataset.windows]
    if windows != ["TRAIN", "VALIDATION", "OOS"]:
        raise ValueError(f"Expected TRAIN/VALIDATION/OOS windows, got {windows}")

    train_records: list[dict[str, Any]] = []
    validation_records: list[dict[str, Any]] = []
    frozen: list[dict[str, Any]] = []
    oos_records: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []

    for strategy_name, strategy in STRATEGIES.items():
        candidates = _grid(strategy_name)
        for symbol in symbols:
            train_frame = split_frame(dataset, frames[symbol], "TRAIN")
            validation_frame = split_frame(dataset, frames[symbol], "VALIDATION")
            oos_frame = split_frame(dataset, frames[symbol], "OOS")
            if train_frame.empty or validation_frame.empty or oos_frame.empty:
                errors.append({"strategy": strategy_name, "symbol": symbol, "error": "one or more research windows empty"})
                continue

            local_train: list[dict[str, Any]] = []
            for params in candidates:
                try:
                    rec = _evaluate(dataset, train_frame, strategy_name, strategy, symbol, "TRAIN", params)
                    local_train.append(rec)
                    train_records.append(rec)
                except Exception as exc:
                    errors.append({"strategy": strategy_name, "symbol": symbol, "window": "TRAIN", "params": repr(params), "error": repr(exc)})

            if not local_train:
                continue

            local_train.sort(key=_rank_key, reverse=True)
            shortlist = local_train[: min(top_k, len(local_train))]

            local_validation: list[dict[str, Any]] = []
            for train_rec in shortlist:
                params = train_rec["params"]
                try:
                    rec = _evaluate(dataset, validation_frame, strategy_name, strategy, symbol, "VALIDATION", params)
                    rec["train_score"] = train_rec["score"]
                    rec["train_metrics"] = train_rec["metrics"]
                    local_validation.append(rec)
                    validation_records.append(rec)
                except Exception as exc:
                    errors.append({"strategy": strategy_name, "symbol": symbol, "window": "VALIDATION", "params": repr(params), "error": repr(exc)})

            if not local_validation:
                continue

            selected = max(local_validation, key=_rank_key)
            frozen_rec = {
                "strategy": strategy_name,
                "symbol": symbol,
                "selected_params": selected["params"],
                "selection_rule": "top-K TRAIN by (return - max_drawdown), then highest VALIDATION score; OOS excluded",
                "train_ranked_candidates": [
                    {"params": r["params"], "score": r["score"], "metrics": r["metrics"]}
                    for r in shortlist
                ],
                "validation_candidates": [
                    {"params": r["params"], "score": r["score"], "metrics": r["metrics"]}
                    for r in local_validation
                ],
            }
            frozen.append(frozen_rec)

            try:
                oos = _evaluate(dataset, oos_frame, strategy_name, strategy, symbol, "OOS", selected["params"])
                oos["frozen_params"] = selected["params"]
                oos_records.append(oos)
            except Exception as exc:
                errors.append({"strategy": strategy_name, "symbol": symbol, "window": "OOS", "params": repr(selected["params"]), "error": repr(exc)})

    expected_pairs = len(STRATEGIES) * len(symbols)
    status = "PASS" if len(frozen) == expected_pairs and len(oos_records) == expected_pairs and not errors else "FAIL"
    return {
        "phase": "2.3",
        "mode": "controlled_parameter_research",
        "status": status,
        "dataset_id": dataset.boundary.dataset_id,
        "market": dataset.boundary.market,
        "interval": dataset.boundary.interval,
        "symbols": list(symbols),
        "strategies": list(STRATEGIES),
        "windows": windows,
        "parameter_policy": {
            "grids": PARAM_GRIDS,
            "top_k_train": top_k,
            "ranking_score": "total_return - max_drawdown",
            "selection": "rank candidates on TRAIN, carry top-K to VALIDATION, select by VALIDATION score",
            "oos_policy": "OOS is evaluated only after parameters are frozen; OOS is never used for selection",
            "mean_reversion": "excluded from Phase 2.3 first-pass research",
        },
        "backtest_parameters": {
            "initial_equity": INITIAL_EQUITY,
            "risk_fraction": RISK_FRACTION,
            "position_fraction": POSITION_FRACTION,
            "max_positions": MAX_POSITIONS,
            "max_risk_fraction": MAX_RISK_FRACTION,
            "fee_rate": 0.0004,
            "slippage_bps": 2.0,
            "funding_rate_per_8h": 0.0,
        },
        "counts": {
            "strategy_symbol_pairs": expected_pairs,
            "train_candidates_per_strategy": {k: len(_grid(k)) for k in STRATEGIES},
            "train_evaluations": len(train_records),
            "validation_evaluations": len(validation_records),
            "frozen_parameter_sets": len(frozen),
            "oos_evaluations": len(oos_records),
        },
        "data_sources": sources,
        "errors": errors,
        "frozen": frozen,
        "oos": oos_records,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lock", default=str(ROOT / "data/reports/research_boundary_lock.json"))
    parser.add_argument("--raw-root", default=str(ROOT / "data/raw"))
    parser.add_argument("--parquet-root", default=str(ROOT / "data/parquet"))
    parser.add_argument("--symbols", nargs="+", default=list(SYMBOLS))
    parser.add_argument("--top-k-train", type=int, default=TOP_K_TRAIN)
    parser.add_argument("--output", default=str(ROOT / "data/reports/phase2_3_parameter_research.json"))
    args = parser.parse_args()

    symbols = tuple(s.upper() for s in args.symbols)
    unknown = sorted(set(symbols) - set(SYMBOLS))
    if unknown:
        raise SystemExit(f"UNKNOWN_SYMBOLS: {unknown}")
    if args.top_k_train < 1:
        raise SystemExit("top-k-train must be >= 1")

    report = run_parameter_research(
        lock_path=args.lock,
        raw_root=args.raw_root,
        parquet_root=args.parquet_root,
        symbols=symbols,
        top_k=args.top_k_train,
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    print("=" * 72)
    print("QuantBot PHASE 2.3 Controlled Parameter Research")
    print("=" * 72)
    print(f"status:              {report['status']}")
    print(f"dataset_id:          {report['dataset_id']}")
    print(f"strategies:          {len(report['strategies'])}")
    print(f"symbols:             {len(report['symbols'])}")
    print(f"train_evaluations:   {report['counts']['train_evaluations']}")
    print(f"validation_evals:    {report['counts']['validation_evaluations']}")
    print(f"frozen_sets:         {report['counts']['frozen_parameter_sets']}")
    print(f"oos_evaluations:     {report['counts']['oos_evaluations']}")
    print(f"errors:              {len(report['errors'])}")
    print(f"output:              {output}")
    print("-" * 72)
    for rec in report["frozen"]:
        val = max(rec["validation_candidates"], key=lambda x: (x["score"], float(x["metrics"]["profit_factor"])))
        print(f"{rec['strategy']:20s} {rec['symbol']:9s} params={rec['selected_params']} validation_score={val['score']:+.6f}")
    print("-" * 72)
    for rec in report["oos"]:
        m = rec["metrics"]
        print(f"OOS {rec['strategy']:17s} {rec['symbol']:9s} return={m['total_return']:+.6f} dd={m['max_drawdown']:.6f} pf={m['profit_factor']:.6f} trades={m['trades']:4d}")
    print("=" * 72)
    print("PHASE2_3_PARAMETER_RESEARCH_OK" if report["status"] == "PASS" else "PHASE2_3_PARAMETER_RESEARCH_FAILED")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
