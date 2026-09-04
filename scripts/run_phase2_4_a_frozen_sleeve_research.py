#!/usr/bin/env python3
"""Phase 2.4-A: frozen-sleeve portfolio research on TRAIN/VALIDATION only.

Purpose:
- Re-run the 72 D-1 frozen Model×Symbol sleeves on TRAIN and VALIDATION only.
- Build validation-only correlation diagnostics and predeclared portfolio candidates.
- Do NOT read D-2/D-3/OOS outputs and do NOT change frozen parameters.

This is a sleeve-level portfolio research stage, not the final shared-capital
multi-position execution backtest. Phase 2.4-B should validate the frozen
portfolio recipes with a true portfolio/risk engine before Paper Trading.
"""
from __future__ import annotations

import argparse
import json
import math
import multiprocessing as mp
import statistics
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
DEFAULT_LOCK = ROOT / "data/reports/research_boundary_lock.json"
DEFAULT_FREEZE = ROOT / "data/reports/phase2_3_5_d1_freeze_manifest.json"
DEFAULT_OUT = ROOT / "data/reports/phase2_4_a_frozen_sleeve_research.json"
DEFAULT_CURVES = ROOT / "data/reports/phase2_4_a_sleeve_equity_curves.jsonl"
DEFAULT_RAW = ROOT / "data/raw"
DEFAULT_PARQUET = ROOT / "data/parquet"

MODELS = [
    "price_ema_momentum", "rsi_momentum", "roc_momentum", "higher_high_lower_low",
    "volume_trend", "bollinger_breakout", "ema_slope", "donchian_breakout",
    "volume_breakout", "volatility_regime_trend", "trend_breakout", "macd_trend",
]
SYMBOLS = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT"]
EXPECTED = {(m, s) for m in MODELS for s in SYMBOLS}

# Predeclared validation candidate gate. This is applied before constructing
# portfolio candidates and is never informed by OOS results.
MIN_TRADES = 20
MAX_DD = 0.35
MIN_PF = 1.0
CORR_CAP = 0.70
MAX_PER_SYMBOL = 2
MAX_PER_MODEL = 2
PORTFOLIO_SIZES = (8, 12)


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def register_all_models():
    from quantbot.research.model_registry import list_models, register_existing_models
    if not list_models():
        register_existing_models()
        from quantbot.strategies.model_pool import register_model_pool
        register_model_pool()


def utc(v):
    t = pd.Timestamp(v)
    return t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")


def gap_indices_for_symbol(boundary, symbol):
    # Missing candles are not inserted. The engine only needs present gap
    # timestamps for its gap accounting; known missing ranges have no rows.
    return set()


def evaluate_symbol(payload):
    # multiprocessing spawn does not reliably inherit the project root on the
    # server; make the package import path explicit inside every worker.
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    symbol, records, lock_path, raw_root, parquet_root = payload
    from quantbot.backtest.costs import CostModel
    from quantbot.backtest.engine_v2 import BacktestEngine
    from quantbot.research.integration import load_boundary_lock
    from quantbot.research.runner import build_research_dataset, load_research_frames, split_frame
    from quantbot.research.evaluation import make_strategy_adapter
    from quantbot.research.model_registry import get_model

    register_all_models()
    boundary = load_boundary_lock(lock_path)
    dataset = build_research_dataset(lock_path)
    frames, sources = load_research_frames(dataset, raw_root, parquet_root, [symbol])
    full = frames[symbol]
    out = []

    for rec in records:
        model = rec["model"]
        params = rec["params"]
        registered = get_model(model)
        for window in ("TRAIN", "VALIDATION"):
            frame = split_frame(dataset, full, window)
            if frame.empty:
                raise ValueError(f"{symbol}/{window}: empty")
            adapter = make_strategy_adapter(
                registered.strategy,
                full_frame=frame,
                params=params,
                risk_fraction=0.01,
                position_fraction=1.0,
                tag=f"P24A:{model}:{symbol}:{window}",
            )
            engine = BacktestEngine(
                initial_equity=10000.0,
                cost_model=CostModel(fee_rate=0.0004, slippage_bps=2.0, funding_rate_per_8h=0.0),
                max_position_fraction=1.0,
                max_risk_fraction=0.01,
                max_positions=1,
                gap_indices={symbol: gap_indices_for_symbol(boundary, symbol)},
            )
            result = engine.run({symbol: frame}, {symbol: adapter})
            metrics = result.metrics()
            curve = [(pd.Timestamp(ts).isoformat(), float(v)) for ts, v in result.equity_curve.items()]
            out.append({
                "model": model,
                "category": rec.get("category"),
                "symbol": symbol,
                "params": params,
                "window": window,
                "rows": len(frame),
                "data_source": sources[symbol],
                "metrics": metrics,
                "curve": curve,
            })
    return out


def sharpe(curve):
    vals = np.asarray([v for _, v in curve], dtype=float)
    if len(vals) < 3 or np.any(vals <= 0):
        return 0.0
    r = vals[1:] / vals[:-1] - 1.0
    r = r[np.isfinite(r)]
    if len(r) < 2 or np.std(r, ddof=1) == 0:
        return 0.0
    return float(np.mean(r) / np.std(r, ddof=1) * math.sqrt(24 * 365))


def max_dd(curve):
    vals = np.asarray([v for _, v in curve], dtype=float)
    if len(vals) == 0:
        return 0.0
    peak = np.maximum.accumulate(vals)
    return float(abs(np.min(vals / peak - 1.0)))


def returns_series(curve):
    d = dict(curve)
    ts = sorted(d)
    vals = np.asarray([d[t] for t in ts], dtype=float)
    if len(vals) < 3:
        return {}
    r = vals[1:] / vals[:-1] - 1.0
    return {ts[i + 1]: float(r[i]) for i in range(len(r)) if np.isfinite(r[i])}


def corr(a, b):
    common = sorted(set(a) & set(b))
    if len(common) < 20:
        return 0.0, len(common)
    x = np.asarray([a[t] for t in common], dtype=float)
    y = np.asarray([b[t] for t in common], dtype=float)
    if np.std(x) == 0 or np.std(y) == 0:
        return 0.0, len(common)
    return float(np.corrcoef(x, y)[0, 1]), len(common)


def validate_freeze(freeze):
    if freeze.get("phase") != "2.3.5-D-1":
        raise ValueError("freeze manifest phase must be 2.3.5-D-1")
    recs = freeze.get("records", [])
    if len(recs) != 72:
        raise ValueError(f"freeze manifest must contain 72 records, got {len(recs)}")
    keys = {(r.get("model"), r.get("symbol")) for r in recs}
    if keys != EXPECTED:
        raise ValueError("freeze manifest is not the locked 12x6 matrix")
    if any(r.get("status") != "FROZEN" or not r.get("oos_authorized") for r in recs):
        raise ValueError("all D-1 records must be FROZEN and OOS-authorized")


def portfolio_curve(selected, sleeve_curves):
    # Equal-weight normalized sleeve equity. This is intentionally a sleeve
    # abstraction; it does not pretend to model shared-capital order execution.
    series = []
    master = sorted(set().union(*(set(dict(sleeve_curves[k])) for k in selected)))
    normalized = {}
    for k in selected:
        d = dict(sleeve_curves[k])
        idx = pd.DatetimeIndex(master)
        s = pd.Series([d.get(ts.isoformat(), np.nan) for ts in idx], index=idx, dtype=float)
        s = s.ffill().fillna(10000.0)
        normalized[k] = s / 10000.0
    w = 1.0 / len(selected)
    p = sum(normalized[k] * w for k in selected)
    return [(ts.isoformat(), float(v * 10000.0)) for ts, v in p.items()]


def portfolio_metrics(curve, sleeves=None):
    vals = np.asarray([v for _, v in curve], dtype=float)
    ret = float(vals[-1] / vals[0] - 1.0)
    dd = max_dd(curve)
    sh = sharpe(curve)
    cal = ret / dd if dd > 0 else (float("inf") if ret > 0 else 0.0)
    return {"initial": float(vals[0]), "final_equity": float(vals[-1]), "total_return": ret,
            "max_drawdown": dd, "sharpe_like": sh, "calmar_like": cal,
            "sleeves": int(sleeves) if sleeves is not None else 1}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lock", default=str(DEFAULT_LOCK))
    ap.add_argument("--freeze", default=str(DEFAULT_FREEZE))
    ap.add_argument("--raw-root", default=str(DEFAULT_RAW))
    ap.add_argument("--parquet-root", default=str(DEFAULT_PARQUET))
    ap.add_argument("--workers", type=int, default=min(6, len(SYMBOLS)))
    ap.add_argument("--output", default=str(DEFAULT_OUT))
    ap.add_argument("--curves-output", default=str(DEFAULT_CURVES))
    args = ap.parse_args()

    freeze = load_json(args.freeze)
    validate_freeze(freeze)
    dataset_id = freeze.get("dataset_id")
    boundary = load_json(args.lock)
    if boundary.get("dataset_id") != dataset_id:
        raise ValueError("freeze manifest and boundary lock dataset_id mismatch")

    by_symbol = defaultdict(list)
    for rec in freeze["records"]:
        by_symbol[rec["symbol"]].append(rec)

    payloads = [(s, by_symbol[s], args.lock, args.raw_root, args.parquet_root) for s in SYMBOLS]
    ctx = mp.get_context("spawn")
    with ctx.Pool(processes=max(1, min(args.workers, len(SYMBOLS)))) as pool:
        chunks = pool.map(evaluate_symbol, payloads)

    results = [x for chunk in chunks for x in chunk]
    if len(results) != 144:
        raise RuntimeError(f"expected 144 TRAIN/VALIDATION sleeve evaluations, got {len(results)}")

    metrics = {(r["model"], r["symbol"], r["window"]): r for r in results}
    curves = {(r["model"], r["symbol"], r["window"]): r["curve"] for r in results}

    # Write curves separately for auditability.
    cp = Path(args.curves_output); cp.parent.mkdir(parents=True, exist_ok=True)
    with cp.open("w", encoding="utf-8") as f:
        for key in sorted(curves):
            model, symbol, window = key
            for ts, eq in curves[key]:
                f.write(json.dumps({"model": model, "symbol": symbol, "window": window, "timestamp": ts, "equity": eq}, ensure_ascii=False) + "\n")

    # Validation-only candidate gate.
    candidates = []
    for m in MODELS:
        for s in SYMBOLS:
            r = metrics[(m, s, "VALIDATION")]
            mm = r["metrics"]
            if (float(mm["total_return"]) > 0 and float(mm["profit_factor"]) >= MIN_PF
                    and float(mm["max_drawdown"]) <= MAX_DD and int(mm["trades"]) >= MIN_TRADES):
                candidates.append({"key": (m, s), "validation_score": float(mm["total_return"] - mm["max_drawdown"]),
                                   "validation_return": float(mm["total_return"]), "validation_dd": float(mm["max_drawdown"]),
                                   "validation_pf": float(mm["profit_factor"]), "validation_trades": int(mm["trades"])})
    candidates.sort(key=lambda x: (x["validation_score"], x["validation_pf"], x["validation_trades"]), reverse=True)

    val_returns = {k: returns_series(curves[(k[0], k[1], "VALIDATION")]) for k in EXPECTED}
    corr_diag = []
    for i, a in enumerate(sorted(EXPECTED)):
        for b in sorted(EXPECTED)[i + 1:]:
            c, n = corr(val_returns[a], val_returns[b])
            if n >= 20:
                corr_diag.append({"left": list(a), "right": list(b), "correlation": c, "observations": n})
    corr_diag.sort(key=lambda x: abs(x["correlation"]))

    candidate_keys = [x["key"] for x in candidates]

    def greedy(size, use_corr=True):
        selected = []
        for key in candidate_keys:
            if len(selected) >= size:
                break
            if sum(1 for x in selected if x[1] == key[1]) >= MAX_PER_SYMBOL:
                continue
            if sum(1 for x in selected if x[0] == key[0]) >= MAX_PER_MODEL:
                continue
            if use_corr and any(abs(corr(val_returns[key], val_returns[x])[0]) > CORR_CAP for x in selected):
                continue
            selected.append(key)
        return selected

    portfolios = []
    top8 = candidate_keys[:8]
    if len(top8) == 8:
        portfolios.append({"name": "P24A_TOP8_VALIDATION", "construction": "validation_score top 8; no correlation filter", "sleeves": [list(x) for x in top8]})
    for size in PORTFOLIO_SIZES:
        sel = greedy(size, True)
        if len(sel) == size:
            portfolios.append({"name": f"P24A_DIVERSIFIED_{size}", "construction": f"validation_score greedy; abs(correlation)<= {CORR_CAP}; max {MAX_PER_SYMBOL} per symbol; max {MAX_PER_MODEL} per model", "sleeves": [list(x) for x in sel]})

    for p in portfolios:
        keys = [tuple(x) for x in p["sleeves"]]
        curve = portfolio_curve(keys, {(m, s): curves[(m, s, "VALIDATION")] for m, s in keys})
        pm = portfolio_metrics(curve, sleeves=len(keys))
        p["validation_metrics"] = pm
        p["weights"] = {f"{m}:{s}": 1.0 / len(keys) for m, s in keys}

    out = {
        "phase": "2.4-A", "version": "1.0.3", "status": "PASS",
        "purpose": "冻结参数的TRAIN/VALIDATION组合研究；OOS完全不读取。",
        "dataset_id": dataset_id,
        "inputs": {"freeze_manifest": str(args.freeze), "boundary_lock": str(args.lock)},
        "research_contract": {
            "windows": ["TRAIN", "VALIDATION"], "oos_read": False,
            "parameters_modified": False, "d1_freeze_modified": False,
            "cost_model": {"fee_rate": 0.0004, "slippage_bps": 2.0, "funding_rate_per_8h": 0.0},
            "risk_fraction": 0.01, "position_fraction": 1.0,
            "portfolio_note": "当前组合曲线为独立冻结策略sleeve的归一化等权组合，不等同于共享资金的真实多仓执行回测。"
        },
        "counts": {"frozen_sleeves": 72, "evaluations": len(results), "validation_candidates": len(candidates), "correlation_pairs": len(corr_diag)},
        "validation_candidate_gate": {"return_gt": 0, "profit_factor_gte": MIN_PF, "max_drawdown_lte": MAX_DD, "trades_gte": MIN_TRADES},
        "validation_candidates": [{**x, "key": list(x["key"])} for x in candidates],
        "correlation_diagnostics": {"lowest_abs_10": corr_diag[:10], "highest_abs_10": sorted(corr_diag, key=lambda x: abs(x["correlation"]), reverse=True)[:10]},
        "portfolio_candidates": portfolios,
        "sleeve_metrics": [
            {k: r[k] for k in ("model", "category", "symbol", "params", "window", "rows", "data_source", "metrics")}
            for r in sorted(results, key=lambda x: (x["window"], x["model"], x["symbol"]))
        ],
        "next_stage": "2.4-B true shared-capital portfolio/risk backtest using only frozen portfolio recipes; OOS must remain untouched until the portfolio recipe is frozen."
    }
    op = Path(args.output); op.parent.mkdir(parents=True, exist_ok=True); op.write_text(json.dumps(out, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    md = op.with_name("phase2_4_a_summary.md")
    lines = ["# Phase 2.4-A 冻结Sleeve组合研究", "", "状态：通过", "", f"- 冻结Sleeve：72", f"- TRAIN/VALIDATION评估：{len(results)}", f"- Validation候选：{len(candidates)}", f"- 相关性Pairs：{len(corr_diag)}", "", "## 组合研究纪律", "- 只读取D-1冻结清单与TRAIN/VALIDATION数据。", "- 不读取D-2/D-3/OOS结果。", "- 不修改冻结参数。", "- 当前组合曲线仅用于研究候选，不代表共享资金真实执行。", "", "## Validation候选前10", "", "|排名|模型|币种|Return|DD|PF|Trades|Score|", "|---:|---|---|---:|---:|---:|---:|---:|"]
    for i, x in enumerate(candidates[:10], 1):
        lines.append(f"|{i}|{x['key'][0]}|{x['key'][1]}|{x['validation_return']:+.2%}|{x['validation_dd']:.2%}|{x['validation_pf']:.3f}|{x['validation_trades']}|{x['validation_score']:+.3f}|")
    lines += ["", "## Portfolio candidates", ""]
    for p in portfolios:
        pm = p["validation_metrics"]
        lines += [f"### {p['name']}", f"- {p['construction']}", f"- Validation Return: {pm['total_return']:+.2%}", f"- Validation Max DD: {pm['max_drawdown']:.2%}", f"- Validation Sharpe-like: {pm['sharpe_like']:.3f}", "- Sleeves:"]
        lines += [f"  - {m} / {s}" for m, s in p["sleeves"]]
    md.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("=" * 72)
    print("Phase 2.4-A 冻结Sleeve组合研究")
    print("=" * 72)
    print("状态：通过")
    print(f"冻结Sleeve：72/72")
    print(f"TRAIN/VALIDATION评估：{len(results)}/144")
    print(f"Validation候选：{len(candidates)}")
    print(f"相关性Pairs：{len(corr_diag)}")
    for p in portfolios:
        pm = p["validation_metrics"]
        print(f"{p['name']}：{len(p['sleeves'])} sleeves，Validation Return={pm['total_return']:+.2%}，DD={pm['max_drawdown']:.2%}")
    print(f"报告：{op}")
    print(f"曲线：{cp}")
    print(f"总结：{md}")
    print("PHASE2_4_A_FROZEN_SLEEVE_RESEARCH_OK")


if __name__ == "__main__":
    main()
