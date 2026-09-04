from __future__ import annotations

import argparse
import concurrent.futures
import gc
import itertools
import json
import os
import sys
import subprocess
import time
from pathlib import Path
from typing import Any

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from quantbot.research.integration import find_gap_ranges
from quantbot.research.model_registry import get_model, register_existing_models, list_models, validate_registry
from quantbot.research.runner import build_research_dataset, load_research_frames, split_frame
from quantbot.strategies.model_pool import register_model_pool
from scripts.run_phase2_3_5_model_discovery_baseline import _fast_backtest, _metrics_extra

SYMBOLS = ("BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT")
WINDOWS = ("TRAIN", "VALIDATION")
INITIAL_EQUITY = 10_000.0
RISK_FRACTION = 0.01
POSITION_FRACTION = 1.0
MAX_POSITIONS = 1
MAX_RISK_FRACTION = 0.01
TOP_K_TRAIN = 5
SHORTLIST_REPORT = ROOT / "data/reports/phase2_3_5_model_discovery_baseline.json"


def _gap_indices(dataset, symbol: str) -> set:
    out = set()
    for gap in find_gap_ranges(dataset.boundary, symbol):
        step = (gap.next - gap.previous) / (gap.missing_bars + 1)
        ts = gap.previous + step
        for _ in range(gap.missing_bars):
            out.add(ts)
            ts += step
    return out


def _grid(spec) -> list[dict[str, Any]]:
    keys = list(spec.parameter_grid)
    values = [tuple(v) for v in spec.parameter_grid.values()]
    return [dict(zip(keys, combo)) for combo in itertools.product(*values)]


def _score(metrics: dict[str, Any]) -> float:
    return float(metrics["total_return"]) - float(metrics["max_drawdown"])


def _param_key(params: dict[str, Any]) -> tuple:
    return tuple((k, params[k]) for k in params)


def _stability(train_results: list[dict[str, Any]], candidate: dict[str, Any], grid_spec) -> dict[str, Any]:
    best_score = float(candidate["score"])
    keys = list(grid_spec.parameter_grid)
    value_sets = {k: set(v) for k, v in grid_spec.parameter_grid.items()}
    lookup = {_param_key(r["params"]): r for r in train_results}
    neighbors = []
    for key in keys:
        for value in value_sets[key]:
            if value == candidate["params"][key]:
                continue
            p = dict(candidate["params"])
            p[key] = value
            r = lookup.get(_param_key(p))
            if r is not None:
                neighbors.append(float(r["score"]))
    boundary = [k for k in keys if candidate["params"][k] in {min(value_sets[k]), max(value_sets[k])}]
    top_scores = [float(r["score"]) for r in train_results[:TOP_K_TRAIN]]
    return {
        "boundary_parameters": boundary,
        "is_boundary_optimum": bool(boundary),
        "neighbor_count": len(neighbors),
        "neighbor_median_score": float(__import__("numpy").median(neighbors)) if neighbors else None,
        "neighbor_min_score": float(min(neighbors)) if neighbors else None,
        "neighbor_max_score": float(max(neighbors)) if neighbors else None,
        "best_minus_neighbor_median": (best_score - float(__import__("numpy").median(neighbors))) if neighbors else None,
        "top5_score_spread": (top_scores[0] - top_scores[-1]) if len(top_scores) >= 2 else 0.0,
        "note": "稳定性为诊断指标，不单独改变参数选择；边界最优仅产生警告，不自动扩大参数空间。",
    }


def _evaluate(frame, strategy, params, symbol, dataset, window, tag):
    fast_metrics, trades = _fast_backtest(frame, strategy, params, symbol, dataset, window, tag)
    return _metrics_extra(fast_metrics, trades)


def _worker(symbol: str, model_name: str, lock_path: str, raw_root: str, parquet_root: str) -> dict[str, Any]:
    started = time.perf_counter()
    register_existing_models()
    register_model_pool()
    validate_registry()
    dataset = build_research_dataset(lock_path)
    frames, sources = load_research_frames(dataset, raw_root, parquet_root, [symbol])
    frame = frames[symbol]
    all_train = []
    all_validation = []
    frozen = []
    errors = []

    for model_name in (model_name,):
        item = get_model(model_name)
        candidates = _grid(item.spec)
        train_results = []
        for params in candidates:
            try:
                part = split_frame(dataset, frame, "TRAIN")
                if part.empty:
                    raise ValueError(f"{symbol}/TRAIN: empty frame")
                metrics = _evaluate(part, item.strategy, params, symbol, dataset, "TRAIN", f"phase2.3.5-D-1:{model_name}:{symbol}:TRAIN")
                train_results.append({"params": params, "metrics": metrics, "score": _score(metrics)})
            except Exception as exc:
                errors.append({"model": model_name, "symbol": symbol, "window": "TRAIN", "params": params, "error": repr(exc)})
        train_results.sort(key=lambda r: (r["score"], r["metrics"]["profit_factor"], -r["metrics"]["max_drawdown"], r["metrics"]["trades"]), reverse=True)
        top = train_results[:TOP_K_TRAIN]
        for rank, r in enumerate(train_results, 1):
            all_train.append({"model": model_name, "symbol": symbol, "rank": rank, **r})

        validation_results = []
        for train_rank, candidate in enumerate(top, 1):
            try:
                part = split_frame(dataset, frame, "VALIDATION")
                if part.empty:
                    raise ValueError(f"{symbol}/VALIDATION: empty frame")
                metrics = _evaluate(part, item.strategy, candidate["params"], symbol, dataset, "VALIDATION", f"phase2.3.5-D-1:{model_name}:{symbol}:VALIDATION")
                validation_results.append({
                    "train_rank": train_rank,
                    "params": candidate["params"],
                    "metrics": metrics,
                    "score": _score(metrics),
                })
            except Exception as exc:
                errors.append({"model": model_name, "symbol": symbol, "window": "VALIDATION", "params": candidate.get("params"), "error": repr(exc)})
        validation_results.sort(key=lambda r: (r["score"], r["metrics"]["profit_factor"], -r["metrics"]["max_drawdown"], r["metrics"]["trades"]), reverse=True)
        for rank, r in enumerate(validation_results, 1):
            all_validation.append({"model": model_name, "symbol": symbol, "validation_rank": rank, **r})

        if not validation_results:
            continue
        selected = validation_results[0]
        stability = _stability(train_results, top[0], item.spec) if top else {}
        vm = selected["metrics"]
        viable = float(vm["total_return"]) > 0.0 and float(vm["profit_factor"]) >= 1.0
        status = "FROZEN" if viable else "HOLD"
        freeze_reason = "Validation return > 0 and PF >= 1.0" if viable else "Validation did not satisfy basic viability gate; OOS not authorized"
        frozen.append({
            "model": model_name,
            "symbol": symbol,
            "status": status,
            "params": selected["params"],
            "train_rank_of_selected": selected["train_rank"],
            "train_metrics": top[selected["train_rank"] - 1]["metrics"] if selected["train_rank"] <= len(top) else None,
            "validation_metrics": vm,
            "train_score": top[selected["train_rank"] - 1]["score"] if selected["train_rank"] <= len(top) else None,
            "validation_score": selected["score"],
            "stability": stability,
            "freeze_reason": freeze_reason,
            "oos_authorized": viable,
        })

    return {
        "symbol": symbol,
        "dataset_id": dataset.boundary.dataset_id,
        "data_source": sources[symbol],
        "train": all_train,
        "validation": all_validation,
        "frozen": frozen,
        "errors": errors,
        "runtime_seconds": round(time.perf_counter() - started, 3),
    }



def _worker_star(task):
    try:
        return _worker(*task)
    except Exception as exc:
        return {"fatal_error": repr(exc), "symbol": task[0], "model": task[1]}

def _load_shortlist(path: Path) -> list[str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("status") != "PASS":
        raise RuntimeError(f"C阶段基线报告状态不是PASS: {data.get('status')}")
    names = [x["model"] for x in data.get("shortlist", [])]
    if len(names) != 12:
        raise RuntimeError(f"C阶段shortlist不是12个模型，而是{len(names)}个")
    return names


def run(args) -> dict[str, Any]:
    models = _load_shortlist(Path(args.shortlist_report))
    expected_models = {
        "price_ema_momentum", "rsi_momentum", "roc_momentum", "higher_high_lower_low",
        "volume_trend", "bollinger_breakout", "ema_slope", "donchian_breakout",
        "volume_breakout", "volatility_regime_trend", "trend_breakout", "macd_trend",
    }
    if set(models) != expected_models:
        raise RuntimeError(f"C阶段shortlist与D-1锁定模型集合不一致: {models}")
    symbols = tuple(s.upper() for s in args.symbols)
    if set(symbols) != set(SYMBOLS):
        raise RuntimeError("D-1默认研究必须覆盖全部6个Universe币种；如需子集测试请使用 --allow-subset")

    t0 = time.perf_counter()
    tasks = [(s, m, args.lock, args.raw_root, args.parquet_root) for s in symbols for m in models]
    worker_results = []
    worker_errors = []
    # Use short-lived OS child processes instead of a long-lived Pool. Each child
    # performs exactly one Model×Symbol task and exits, preventing pandas allocator
    # growth and avoiding cross-task state contamination.
    tmp_dir = ROOT / "data/reports/.d1_workers"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    pending = list(tasks)
    while pending:
        batch = pending[:min(args.workers, len(pending))]
        pending = pending[len(batch):]
        procs = []
        paths = []
        for symbol, model_name, lock, raw, parquet in batch:
            out_path = tmp_dir / f"{symbol}__{model_name}.json"
            paths.append(out_path)
            cmd = [sys.executable, str(Path(__file__).resolve()), "--single-symbol", symbol, "--single-model", model_name,
                   "--lock", lock, "--raw-root", raw, "--parquet-root", parquet, "--worker-output", str(out_path)]
            procs.append((symbol, model_name, out_path, subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)))
        for symbol, model_name, out_path, proc in procs:
            stderr = proc.communicate()[1]
            if proc.returncode != 0:
                worker_errors.append({"symbol": symbol, "model": model_name, "error": stderr[-4000:] or f"worker exit {proc.returncode}"})
                print(f"失败 {symbol}/{model_name}", flush=True)
                continue
            try:
                result = json.loads(out_path.read_text(encoding="utf-8"))
                if result.get("fatal_error"):
                    worker_errors.append({"symbol": symbol, "model": model_name, "error": result["fatal_error"]})
                    print(f"失败 {symbol}/{model_name}: {result['fatal_error']}", flush=True)
                else:
                    worker_results.append(result)
                    print(f"完成 {symbol}/{model_name}", flush=True)
            except Exception as exc:
                worker_errors.append({"symbol": symbol, "model": model_name, "error": repr(exc)})
                print(f"失败 {symbol}/{model_name}: 无法读取worker结果", flush=True)
            finally:
                try: out_path.unlink()
                except FileNotFoundError: pass

    train = [r for w in worker_results for r in w["train"]]
    validation = [r for w in worker_results for r in w["validation"]]
    frozen = [r for w in worker_results for r in w["frozen"]]
    errors = [r for w in worker_results for r in w["errors"]] + worker_errors
    grid_counts = {}
    register_existing_models(); register_model_pool(); validate_registry()
    for name in models:
        grid_counts[name] = len(_grid(get_model(name).spec))
    expected_train = sum(grid_counts.values()) * len(symbols)
    expected_validation = TOP_K_TRAIN * len(models) * len(symbols)
    completed_train = len(train)
    completed_validation = len(validation)
    frozen_viable = [x for x in frozen if x["status"] == "FROZEN"]
    holds = [x for x in frozen if x["status"] == "HOLD"]
    status = "PASS" if not errors and completed_train == expected_train and completed_validation == expected_validation and len(frozen) == len(models) * len(symbols) else "FAIL"
    dataset_ids = sorted({w["dataset_id"] for w in worker_results})
    report = {
        "phase": "2.3.5-D-1",
        "version": "1.0",
        "status": status,
        "purpose": "对C阶段12个shortlist模型进行受控参数空间研究；TRAIN全Grid、Top-5进入Validation、选择后形成Freeze/Hold；OOS完全不读取。",
        "dataset_id": dataset_ids[0] if len(dataset_ids) == 1 else dataset_ids,
        "market": "BINANCE_UM",
        "interval": "1h",
        "symbols": list(symbols),
        "models": models,
        "windows": list(WINDOWS),
        "shortlist_source": str(Path(args.shortlist_report)),
        "parameter_policy": {
            "grid_source": "quantbot.research.model_registry ModelSpec.parameter_grid",
            "train_search": "每个Model×Symbol扫描登记的全部参数组合",
            "top_k_train": TOP_K_TRAIN,
            "ranking_score": "total_return - max_drawdown",
            "validation_selection": "仅对TRAIN Top-5验证；按Validation score降序，PF/DD/trades作确定性平手排序",
            "stability": "记录边界最优与Hamming距离1邻域稳定性；仅诊断，不自动改变选择或扩大Grid",
            "freeze_gate": "Validation total_return > 0 且 profit_factor >= 1.0",
            "hold_policy": "未通过基础可行性门槛的Model×Symbol标记HOLD，不授权OOS",
            "oos_policy": "D-1程序不加载、不读取、不评价OOS",
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
            "models": len(models),
            "symbols": len(symbols),
            "model_symbol_cells": len(models) * len(symbols),
            "expected_train_evaluations": expected_train,
            "completed_train_evaluations": completed_train,
            "expected_validation_evaluations": expected_validation,
            "completed_validation_evaluations": completed_validation,
            "freeze_records": len(frozen),
            "frozen_viable": len(frozen_viable),
            "hold": len(holds),
            "errors": len(errors),
        },
        "grid_counts": grid_counts,
        "data_sources": {w["symbol"]: w["data_source"] for w in worker_results},
        "errors": errors,
        "train_records": train,
        "validation_records": validation,
        "freeze_manifest": frozen,
        "runtime_seconds": round(time.perf_counter() - t0, 3),
        "workers": len(tasks),
    }
    return report


def main() -> int:
    p = argparse.ArgumentParser(description="Phase 2.3.5-D-1 controlled parameter research")
    p.add_argument("--lock", default=str(ROOT / "data/reports/research_boundary_lock.json"))
    p.add_argument("--raw-root", default=str(ROOT / "data/raw"))
    p.add_argument("--parquet-root", default=str(ROOT / "data/parquet"))
    p.add_argument("--shortlist-report", default=str(SHORTLIST_REPORT))
    p.add_argument("--symbols", nargs="+", default=list(SYMBOLS))
    p.add_argument("--workers", type=int, default=6)
    p.add_argument("--single-symbol", default=None)
    p.add_argument("--single-model", default=None)
    p.add_argument("--worker-output", default=None)
    p.add_argument("--output", default=str(ROOT / "data/reports/phase2_3_5_d1_parameter_research.json"))
    args = p.parse_args()
    if args.single_symbol or args.single_model or args.worker_output:
        if not (args.single_symbol and args.single_model and args.worker_output):
            raise SystemExit("single worker参数必须同时提供 --single-symbol --single-model --worker-output")
        result = _worker_star((args.single_symbol.upper(), args.single_model, args.lock, args.raw_root, args.parquet_root))
        Path(args.worker_output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.worker_output).write_text(json.dumps(result, ensure_ascii=False, default=str), encoding="utf-8")
        return 0 if not result.get("fatal_error") else 1
    if args.workers < 1:
        raise SystemExit("workers必须 >= 1")
    report = run(args)
    out = Path(args.output); out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    freeze_out = out.with_name("phase2_3_5_d1_freeze_manifest.json")
    freeze_out.write_text(json.dumps({
        "phase": report["phase"], "version": report["version"], "dataset_id": report["dataset_id"],
        "selection_rule": report["parameter_policy"], "records": report["freeze_manifest"]
    }, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    summary_out = out.with_name("phase2_3_5_d1_summary.md")
    lines = [
        "# Phase 2.3.5-D-1 参数研究总结", "",
        f"状态：{'通过' if report['status']=='PASS' else '失败'}",
        f"模型：{report['counts']['models']}；币种：{report['counts']['symbols']}；Model×Symbol：{report['counts']['model_symbol_cells']}",
        f"TRAIN：{report['counts']['completed_train_evaluations']}/{report['counts']['expected_train_evaluations']}",
        f"VALIDATION：{report['counts']['completed_validation_evaluations']}/{report['counts']['expected_validation_evaluations']}",
        f"FROZEN：{report['counts']['frozen_viable']}；HOLD：{report['counts']['hold']}；错误：{report['counts']['errors']}",
        f"总耗时：{report['runtime_seconds']} 秒", "", "## Freeze / Hold", "",
    ]
    for x in sorted(report["freeze_manifest"], key=lambda z:(z["model"],z["symbol"])):
        vm=x["validation_metrics"]
        lines.append(f"- {x['model']} / {x['symbol']}: **{x['status']}** | Validation Return {vm['total_return']:+.2%} | DD {vm['max_drawdown']:.2%} | PF {vm['profit_factor']:.3f} | Params `{json.dumps(x['params'], ensure_ascii=False, sort_keys=True)}`")
    summary_out.write_text("\n".join(lines)+"\n", encoding="utf-8")
    print("="*72)
    print("Phase 2.3.5-D-1 受控参数研究")
    print("="*72)
    print(f"状态：{'通过' if report['status']=='PASS' else '失败'}")
    print(f"TRAIN：{report['counts']['completed_train_evaluations']}/{report['counts']['expected_train_evaluations']}")
    print(f"VALIDATION：{report['counts']['completed_validation_evaluations']}/{report['counts']['expected_validation_evaluations']}")
    print(f"FROZEN：{report['counts']['frozen_viable']}  HOLD：{report['counts']['hold']}  错误：{report['counts']['errors']}")
    print(f"报告：{out}")
    print(f"冻结清单：{freeze_out}")
    print(f"总结：{summary_out}")
    print("PHASE2_3_5_D1_PARAMETER_RESEARCH_OK" if report['status']=='PASS' else "PHASE2_3_5_D1_PARAMETER_RESEARCH_FAILED")
    return 0 if report['status']=='PASS' else 1

if __name__ == "__main__":
    raise SystemExit(main())
