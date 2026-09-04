from __future__ import annotations

import os
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")

import gc
import argparse
import inspect
import json
import multiprocessing as mp
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from quantbot.backtest.costs import CostModel
from quantbot.backtest.engine_v2 import BacktestEngine
from quantbot.research.evaluation import evaluate_strategy
from quantbot.backtest.engine_v2 import Trade
from quantbot.research.integration import find_gap_ranges
from quantbot.research.runner import build_research_dataset, load_research_frames, split_frame
from quantbot.research.model_registry import list_models, register_existing_models, validate_registry
from quantbot.strategies.model_pool import register_model_pool

SYMBOLS = ("BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT")
WINDOWS = ("TRAIN", "VALIDATION")
INITIAL_EQUITY = 10_000.0
RISK_FRACTION = 0.01
POSITION_FRACTION = 1.0
MAX_POSITIONS = 1
MAX_RISK_FRACTION = 0.01


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


def _default_params(fn) -> dict[str, Any]:
    sig = inspect.signature(fn)
    out = {}
    for name, p in sig.parameters.items():
        if name == "df":
            continue
        if p.default is inspect.Parameter.empty:
            raise ValueError(f"strategy parameter without default: {name}")
        out[name] = p.default
    return out


def _metrics_extra(backtest_metrics: dict[str, Any], trades: list[Any]) -> dict[str, Any]:
    net = np.asarray([float(t.net_pnl) for t in trades], dtype=float)
    if len(net):
        expectancy = float(net.mean())
        wins = net[net > 0]
        losses = -net[net < 0]
        avg_win = float(wins.mean()) if len(wins) else 0.0
        avg_loss = float(losses.mean()) if len(losses) else 0.0
        r_win = int((net > 0).sum())
        max_consecutive_losses = 0
        cur = 0
        for x in net:
            if x < 0:
                cur += 1
                max_consecutive_losses = max(max_consecutive_losses, cur)
            else:
                cur = 0
    else:
        expectancy = avg_win = avg_loss = 0.0
        r_win = 0
        max_consecutive_losses = 0

    total_return = float(backtest_metrics["total_return"])
    max_dd = float(backtest_metrics["max_drawdown"])
    pf = float(backtest_metrics["profit_factor"])
    calmar = total_return / max_dd if max_dd > 0 else (float("inf") if total_return > 0 else 0.0)
    return {
        **backtest_metrics,
        "expectancy_per_trade": expectancy,
        "average_win": avg_win,
        "average_loss": avg_loss,
        "winning_trades": r_win,
        "max_consecutive_losses": int(max_consecutive_losses),
        "calmar_like": calmar,
        "research_score": total_return - max_dd,
        "pf_minus_one": pf - 1.0,
    }



def _fast_backtest(frame, strategy, params, symbol, dataset, window, tag):
    """Single-symbol fast path; behavior is checked against BacktestEngine in tests."""
    evaluated = strategy(frame.copy(), **params)
    required = {"signal", "stop", "target"}
    if not required.issubset(evaluated.columns):
        raise ValueError(f"{symbol}/{window}: strategy result missing {sorted(required - set(evaluated.columns))}")
    if len(evaluated) != len(frame) or not evaluated.index.equals(frame.index):
        raise ValueError(f"{symbol}/{window}: strategy result index/length mismatch")

    fee = 0.0004
    slip = 2.0 / 10000.0
    max_risk = MAX_RISK_FRACTION
    max_pos = POSITION_FRACTION
    equity = INITIAL_EQUITY
    position = None
    trades = []
    curve_values = []
    curve_times = []
    rejected = 0
    idx = frame.index
    opens = frame["open"].to_numpy(dtype=float)
    highs = frame["high"].to_numpy(dtype=float)
    lows = frame["low"].to_numpy(dtype=float)
    closes = frame["close"].to_numpy(dtype=float)
    signals = evaluated["signal"].to_numpy()
    stops = evaluated["stop"].to_numpy(dtype=float)
    targets = evaluated["target"].to_numpy(dtype=float)

    for i in range(len(frame)):
        # Manage existing position first. New positions only start managing from next candle.
        if position is not None and i > position["entry_i"]:
            if position["side"] == "buy":
                stop_hit = lows[i] <= position["stop"]
                target_hit = (not np.isnan(position["target"]) and highs[i] >= position["target"])
            else:
                stop_hit = highs[i] >= position["stop"]
                target_hit = (not np.isnan(position["target"]) and lows[i] <= position["target"])
            if stop_hit or target_hit:
                reason = "stop" if stop_hit else "take_profit"
                reference = position["stop"] if stop_hit else position["target"]
                exit_side = "sell" if position["side"] == "buy" else "buy"
                exit_price = reference * (1.0 - slip if exit_side == "sell" else 1.0 + slip)
                gross = ((exit_price - position["entry_price"]) * position["qty"] if position["side"] == "buy" else (position["entry_price"] - exit_price) * position["qty"])
                exit_fee = position["qty"] * exit_price * fee
                fees = position["entry_fee"] + exit_fee
                trades.append(Trade(symbol, position["side"], position["entry_time"], idx[i].isoformat(), position["qty"], position["entry_price"], exit_price, gross, fees, abs(exit_price-reference)*position["qty"], gross-fees, reason, tag))
                equity += gross - fees
                position = None

        # Entry at current OPEN uses only completed prior strategy row (i-1).
        if position is None and i > 0:
            side_val = int(signals[i-1]) if not np.isnan(signals[i-1]) else 0
            if side_val in (-1, 1):
                stop = stops[i-1]
                target = targets[i-1]
                if not np.isfinite(stop):
                    rejected += 1
                else:
                    side = "buy" if side_val == 1 else "sell"
                    entry_ref = opens[i]
                    risk_per_unit = abs(entry_ref - stop)
                    if risk_per_unit <= 0:
                        rejected += 1
                    else:
                        risk_budget = equity * max_risk
                        qty = min(risk_budget / risk_per_unit, equity * max_pos / entry_ref)
                        if qty <= 0:
                            rejected += 1
                        else:
                            entry_price = entry_ref * (1.0 + slip if side == "buy" else 1.0 - slip)
                            entry_fee = qty * entry_price * fee
                            position = {"side": side, "qty": qty, "entry_price": entry_price, "entry_time": idx[i].isoformat(), "entry_i": i, "stop": float(stop), "target": float(target) if np.isfinite(target) else np.nan, "entry_fee": entry_fee}

        mtm = equity
        if position is not None:
            unrealized = ((closes[i] - position["entry_price"]) * position["qty"] if position["side"] == "buy" else (position["entry_price"] - closes[i]) * position["qty"])
            mtm += unrealized - position["entry_fee"]
        curve_times.append(idx[i]); curve_values.append(mtm)

    if position is not None:
        last = len(frame)-1
        reference = closes[last]
        exit_side = "sell" if position["side"] == "buy" else "buy"
        exit_price = reference * (1.0 - slip if exit_side == "sell" else 1.0 + slip)
        gross = ((exit_price-position["entry_price"])*position["qty"] if position["side"] == "buy" else (position["entry_price"]-exit_price)*position["qty"])
        exit_fee = position["qty"]*exit_price*fee
        fees = position["entry_fee"] + exit_fee
        trades.append(Trade(symbol, position["side"], position["entry_time"], idx[last].isoformat(), position["qty"], position["entry_price"], exit_price, gross, fees, abs(exit_price-reference)*position["qty"], gross-fees, "end_of_data", tag))
        equity += gross - fees

    # Same metric contract as BacktestResult.metrics().
    eq = np.asarray(curve_values + [equity], dtype=float)
    peaks = np.maximum.accumulate(eq)
    dd = eq / peaks - 1.0
    net = np.asarray([t.net_pnl for t in trades], dtype=float)
    wins = net[net > 0]; losses = -net[net < 0]
    gp = float(wins.sum()) if len(wins) else 0.0
    gl = float(losses.sum()) if len(losses) else 0.0
    metrics = {
        "initial": INITIAL_EQUITY, "final_equity": equity, "total_return": equity/INITIAL_EQUITY-1.0,
        "max_drawdown": abs(float(dd.min())) if len(dd) else 0.0, "trades": len(trades),
        "win_rate": len(wins)/len(net) if len(net) else 0.0, "profit_factor": gp/gl if gl else float("inf"),
        "rejected_signals": rejected, "skipped_gap_bars": 0, "gap_bars_seen": 0,
    }
    return metrics, trades

def _worker(task: tuple[str, str, str, str, str]) -> dict[str, Any]:
    symbol, model_name, lock_path, raw_root, parquet_root = task
    t0 = time.perf_counter()
    dataset = build_research_dataset(lock_path)
    frames, sources = load_research_frames(dataset, raw_root, parquet_root, [symbol])
    frame = frames[symbol]

    item = next((m for m in list_models() if m.spec.name == model_name), None)
    if item is None:
        raise ValueError(f"unknown model: {model_name}")
    params = _default_params(item.strategy)

    records = []
    errors = []
    for window in WINDOWS:
        part = split_frame(dataset, frame, window)
        try:
            if part.empty:
                raise ValueError(f"{symbol}/{window}: empty frame")
            fast_metrics, fast_trades = _fast_backtest(
                part, item.strategy, params, symbol, dataset, window,
                f"phase2.3.5-C:{item.spec.name}:{symbol}:{window}:default",
            )
            m = _metrics_extra(fast_metrics, fast_trades)
            records.append({
                "model": item.spec.name,
                "category": item.spec.category,
                "symbol": symbol,
                "window": window,
                "params": params,
                "rows": len(part),
                "metrics": m,
                "data_source": sources[symbol],
            })
        except Exception as exc:
            errors.append({
                "model": item.spec.name,
                "symbol": symbol,
                "window": window,
                "error": repr(exc),
            })

    return {
        "symbol": symbol,
        "model": model_name,
        "records": records,
        "errors": errors,
        "runtime_seconds": round(time.perf_counter() - t0, 3),
    }

def _aggregate(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_model: dict[str, list[dict[str, Any]]] = {}
    for r in records:
        by_model.setdefault(r["model"], []).append(r)

    rows = []
    for model, rs in by_model.items():
        train = [r for r in rs if r["window"] == "TRAIN"]
        val = [r for r in rs if r["window"] == "VALIDATION"]
        if len(train) != 6 or len(val) != 6:
            continue
        def vals(items, key):
            return [float(x["metrics"][key]) for x in items]
        tr_ret, va_ret = vals(train, "total_return"), vals(val, "total_return")
        tr_dd, va_dd = vals(train, "max_drawdown"), vals(val, "max_drawdown")
        tr_pf, va_pf = vals(train, "profit_factor"), vals(val, "profit_factor")
        va_score = [x["metrics"]["research_score"] for x in val]
        both_positive = sum(1 for a, b in zip(tr_ret, va_ret) if a > 0 and b > 0)
        val_positive = sum(1 for x in va_ret if x > 0)
        val_pf_good = sum(1 for x in va_pf if x >= 1.0)
        median_val_score = float(np.median(va_score))
        rows.append({
            "model": model,
            "category": val[0]["category"],
            "train_positive_symbols": sum(x > 0 for x in tr_ret),
            "validation_positive_symbols": val_positive,
            "validation_pf_ge_1_symbols": val_pf_good,
            "both_train_validation_positive_symbols": both_positive,
            "train_mean_return": float(np.mean(tr_ret)),
            "validation_mean_return": float(np.mean(va_ret)),
            "train_median_return": float(np.median(tr_ret)),
            "validation_median_return": float(np.median(va_ret)),
            "train_median_drawdown": float(np.median(tr_dd)),
            "validation_median_drawdown": float(np.median(va_dd)),
            "train_median_pf": float(np.median(tr_pf)),
            "validation_median_pf": float(np.median(va_pf)),
            "validation_median_score": median_val_score,
            "validation_worst_return": float(min(va_ret)),
            "validation_worst_drawdown": float(max(va_dd)),
        })
    return sorted(rows, key=lambda x: (
        x["both_train_validation_positive_symbols"],
        x["validation_positive_symbols"],
        x["validation_pf_ge_1_symbols"],
        x["validation_median_score"],
        x["validation_median_pf"],
        -x["validation_median_drawdown"],
    ), reverse=True)


def run(args):
    register_existing_models(); register_model_pool(); validate_registry()
    model_items = list(list_models())
    if len(model_items) != 36:
        raise RuntimeError(f"expected 36 models, got {len(model_items)}")

    symbols = tuple(s.upper() for s in args.symbols)
    t0 = time.perf_counter()
    dataset = build_research_dataset(args.lock)
    frames, sources = load_research_frames(dataset, args.raw_root, args.parquet_root, list(symbols))

    records = []
    errors = []
    task_runtimes = {}
    expected = len(symbols) * len(model_items) * len(WINDOWS)

    # The baseline deliberately loads each symbol only once. The fast single-symbol
    # execution path is numerically checked against BacktestEngine before release.
    for symbol in symbols:
        print(f"开始模型基线：{symbol}", flush=True)
        frame = frames[symbol]
        for item in model_items:
            params = _default_params(item.strategy)
            for window in WINDOWS:
                part = split_frame(dataset, frame, window)
                task_key = f"{symbol}:{item.spec.name}:{window}"
                started = time.perf_counter()
                try:
                    if part.empty:
                        raise ValueError(f"{symbol}/{window}: empty frame")
                    fast_metrics, fast_trades = _fast_backtest(
                        part, item.strategy, params, symbol, dataset, window,
                        f"phase2.3.5-C:{item.spec.name}:{symbol}:{window}:default",
                    )
                    m = _metrics_extra(fast_metrics, fast_trades)
                    records.append({
                        "model": item.spec.name,
                        "category": item.spec.category,
                        "symbol": symbol,
                        "window": window,
                        "params": params,
                        "rows": len(part),
                        "metrics": m,
                        "data_source": sources[symbol],
                    })
                except Exception as exc:
                    errors.append({"model": item.spec.name, "symbol": symbol, "window": window, "error": repr(exc)})
                finally:
                    task_runtimes[task_key] = round(time.perf_counter() - started, 4)
                    gc.collect()

    summary = _aggregate(records)
    gated = [x for x in summary if (
        x["validation_positive_symbols"] >= 3
        and x["validation_pf_ge_1_symbols"] >= 3
        and x["both_train_validation_positive_symbols"] >= 2
        and x["validation_median_pf"] >= 1.0
    )]
    shortlist = gated[:args.shortlist]

    report = {
        "phase": "2.3.5-C",
        "version": "1.0",
        "status": "PASS" if len(records) == expected and not errors else "FAIL",
        "dataset_id": dataset.boundary.dataset_id,
        "market": dataset.boundary.market,
        "interval": dataset.boundary.interval,
        "symbols": list(symbols),
        "models": len(model_items),
        "windows": list(WINDOWS),
        "purpose": "模型池默认参数真实数据基线筛选；不进行参数优化；不读取或使用OOS",
        "parameter_policy": "使用每个策略函数的代码默认参数；参数网格仅保留到下一阶段，不在本阶段搜索",
        "costs": {"fee_rate": 0.0004, "slippage_bps": 2.0, "funding_rate_per_8h": 0.0},
        "risk": {"initial_equity": INITIAL_EQUITY, "risk_fraction": RISK_FRACTION, "position_fraction": POSITION_FRACTION, "max_positions": MAX_POSITIONS, "max_risk_fraction": MAX_RISK_FRACTION},
        "counts": {
            "expected_evaluations": expected,
            "completed_evaluations": len(records),
            "errors": len(errors),
            "shortlist_gate_passed": len(gated),
            "shortlist_selected": len(shortlist),
        },
        "screening_gate": {
            "validation_positive_symbols_min": 3,
            "validation_pf_ge_1_symbols_min": 3,
            "both_train_validation_positive_symbols_min": 2,
            "validation_median_pf_min": 1.0,
            "shortlist_max": args.shortlist,
            "note": "这是下一阶段研究资源控制门槛，不是最终交易模型判定；最终模型必须继续TRAIN→VALIDATION→冻结→OOS。",
        },
        "runtime_seconds": round(time.perf_counter() - t0, 3),
        "task_runtime_seconds": task_runtimes,
        "data_sources": sources,
        "errors": errors,
        "model_summary": summary,
        "shortlist": shortlist,
        "raw_records": records,
    }
    return report


def main() -> int:
    p = argparse.ArgumentParser(description="Phase 2.3.5-C model discovery baseline")
    p.add_argument("--lock", default=str(ROOT / "data/reports/research_boundary_lock.json"))
    p.add_argument("--raw-root", default=str(ROOT / "data/raw"))
    p.add_argument("--parquet-root", default=str(ROOT / "data/parquet"))
    p.add_argument("--symbols", nargs="+", default=list(SYMBOLS))
    p.add_argument("--shortlist", type=int, default=12)
    p.add_argument("--output", default=str(ROOT / "data/reports/phase2_3_5_model_discovery_baseline.json"))
    args = p.parse_args()
    args.symbols = tuple(s.upper() for s in args.symbols)
    unknown = sorted(set(args.symbols) - set(SYMBOLS))
    if unknown:
        raise SystemExit(f"未知币种: {unknown}")
    if args.shortlist < 1:
        raise SystemExit("shortlist 必须 >= 1")

    report = run(args)
    out = Path(args.output); out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    print("=" * 72)
    print("Phase 2.3.5-C 模型池真实数据基线筛选")
    print("=" * 72)
    print(f"状态：{'通过' if report['status'] == 'PASS' else '失败'}")
    print(f"数据集：{report['dataset_id']}")
    print(f"模型：{report['models']}")
    print(f"币种：{len(report['symbols'])}")
    print(f"窗口：TRAIN + VALIDATION（不读取 OOS）")
    print(f"评估：{report['counts']['completed_evaluations']}/{report['counts']['expected_evaluations']}")
    print(f"错误：{report['counts']['errors']}")
    print(f"通过筛选门槛：{report['counts']['shortlist_gate_passed']}")
    print(f"进入下一阶段：{report['counts']['shortlist_selected']}")
    print(f"总耗时：{report['runtime_seconds']} 秒")
    print("执行方式：单进程顺序评估，避免重复加载数据和CPU过度并发")
    print("-" * 72)
    print("下一阶段候选：")
    for i, x in enumerate(report["shortlist"], 1):
        print(f"{i:02d}. {x['model']:28s}  验证正收益 {x['validation_positive_symbols']}/6  PF≥1 {x['validation_pf_ge_1_symbols']}/6  中位PF {x['validation_median_pf']:.3f}  中位收益 {x['validation_median_return']:+.2%}  中位DD {x['validation_median_drawdown']:.2%}")
    print("-" * 72)
    print(f"报告：{out}")
    print("=" * 72)
    ok = report["status"] == "PASS"
    print("PHASE2_3_5_MODEL_DISCOVERY_BASELINE_OK" if ok else "PHASE2_3_5_MODEL_DISCOVERY_BASELINE_FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
