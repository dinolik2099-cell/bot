from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from quantbot.backtest.engine_v2 import BacktestEngine
from quantbot.backtest.costs import CostModel
from quantbot.research.evaluation import make_strategy_adapter
from quantbot.research.integration import find_gap_ranges
from quantbot.research.authorization_gate import require_oos_authorized
from quantbot.research.model_registry import get_model, register_existing_models, validate_registry, list_models
from quantbot.research.runner import build_research_dataset, load_research_frames, split_frame
from quantbot.strategies.model_pool import register_model_pool
from scripts.run_phase2_3_5_model_discovery_baseline import _metrics_extra

SYMBOLS = ("BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT")
EXPECTED_MODELS = (
    "price_ema_momentum", "rsi_momentum", "roc_momentum", "higher_high_lower_low",
    "volume_trend", "bollinger_breakout", "ema_slope", "donchian_breakout",
    "volume_breakout", "volatility_regime_trend", "trend_breakout", "macd_trend",
)
INITIAL_EQUITY = 10_000.0
RISK_FRACTION = 0.01
POSITION_FRACTION = 1.0
MAX_RISK_FRACTION = 0.01
MAX_POSITIONS = 1
DEFAULT_FREEZE = ROOT / "data/reports/phase2_3_5_d1_freeze_manifest.json"


def _utc(ts):
    import pandas as pd
    t = pd.Timestamp(ts)
    return t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")


def _load_freeze(path: Path, dataset_id: str) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("phase") != "2.3.5-D-1":
        raise RuntimeError(f"Freeze manifest phase不正确: {data.get('phase')}")
    if data.get("dataset_id") != dataset_id:
        raise RuntimeError(
            f"D-1 dataset_id与当前Boundary Lock不一致: {data.get('dataset_id')} != {dataset_id}"
        )
    records = data.get("records")
    if not isinstance(records, list):
        raise RuntimeError("Freeze manifest缺少records")
    expected = {(m, s) for m in EXPECTED_MODELS for s in SYMBOLS}
    actual = {(r.get("model"), r.get("symbol")) for r in records}
    if actual != expected:
        raise RuntimeError(f"D-1 Freeze矩阵不完整: expected={len(expected)} actual={len(actual)}")
    bad = [r for r in records if r.get("status") != "FROZEN" or not r.get("oos_authorized", False)]
    if bad:
        raise RuntimeError(f"存在未授权OOS的Freeze记录: {len(bad)}")
    return records


def _gap_blocked_entry_times(dataset, symbol: str, frame) -> set:
    # A configured gap has no synthetic timestamps. Prevent the first actual
    # candle after a gap from opening a position based on pre-gap information.
    idx = set(frame.index)
    return {
        _utc(gap.next)
        for gap in find_gap_ranges(dataset.boundary, symbol)
        if _utc(gap.next) in idx
    }


def _evaluate_oos(frame, strategy, params, symbol, dataset, tag):
    blocked = _gap_blocked_entry_times(dataset, symbol, frame)
    base = make_strategy_adapter(
        strategy,
        full_frame=frame,
        params=params,
        risk_fraction=RISK_FRACTION,
        position_fraction=POSITION_FRACTION,
        tag=tag,
    )

    def adapter(history, i):
        ts = _utc(frame.index[i])
        if ts in blocked:
            return None
        return base(history, i)

    # The immutable gaps are retained in the report; there are no synthetic
    # candles. The adapter blocks a first post-gap entry so pre-gap information
    # cannot create a trade across a data discontinuity.
    engine = BacktestEngine(
        initial_equity=INITIAL_EQUITY,
        cost_model=CostModel(fee_rate=0.0004, slippage_bps=2.0, funding_rate_per_8h=0.0),
        max_position_fraction=POSITION_FRACTION,
        max_risk_fraction=MAX_RISK_FRACTION,
        max_positions=MAX_POSITIONS,
        gap_indices=None,
    )
    result = engine.run({symbol: frame}, {symbol: adapter})
    metrics = _metrics_extra(result.metrics(), result.trades)
    curve = [(ts.isoformat(), float(v)) for ts, v in result.equity_curve.items()]
    trades = [
        {
            "symbol": t.symbol,
            "side": t.side,
            "entry_time": t.entry_time,
            "exit_time": t.exit_time,
            "qty": float(t.qty),
            "entry_price": float(t.entry_price),
            "exit_price": float(t.exit_price),
            "gross_pnl": float(t.gross_pnl),
            "fees": float(t.fees),
            "slippage_cost": float(t.slippage_cost),
            "net_pnl": float(t.net_pnl),
            "exit_reason": t.exit_reason,
            "tag": t.tag,
        }
        for t in result.trades
    ]
    return metrics, curve, trades, sorted(x.isoformat() for x in blocked)


def _worker(record: dict[str, Any], lock_path: str, raw_root: str, parquet_root: str) -> dict[str, Any]:
    started = time.perf_counter()
    if not list_models():
        register_existing_models()
        register_model_pool()
    validate_registry()
    dataset = build_research_dataset(lock_path)
    symbol = str(record["symbol"]).upper()
    model_name = str(record["model"])
    frames, sources = load_research_frames(dataset, raw_root, parquet_root, [symbol])
    part = split_frame(dataset, frames[symbol], "OOS")
    if part.empty:
        raise ValueError(f"{symbol}/OOS: empty frame")
    item = get_model(model_name)
    metrics, curve, trades, blocked = _evaluate_oos(
        part, item.strategy, record["params"], symbol, dataset,
        f"phase2.3.5-D-2:{model_name}:{symbol}:OOS:frozen",
    )
    return {
        "model": model_name,
        "category": item.spec.category,
        "symbol": symbol,
        "window": "OOS",
        "params": record["params"],
        "d1_train_rank": record.get("train_rank_of_selected"),
        "d1_train_metrics": record.get("train_metrics"),
        "d1_validation_metrics": record.get("validation_metrics"),
        "oos_metrics": metrics,
        "rows": len(part),
        "first_timestamp": part.index[0].isoformat(),
        "last_timestamp": part.index[-1].isoformat(),
        "data_source": sources[symbol],
        "blocked_post_gap_entries": blocked,
        "equity_curve": curve,
        "trades": trades,
        "runtime_seconds": round(time.perf_counter() - started, 3),
    }


def _worker_star(args):
    try:
        return _worker(*args)
    except Exception as exc:
        return {"fatal_error": repr(exc), "model": args[0].get("model"), "symbol": args[0].get("symbol")}


def run(args) -> dict[str, Any]:
    require_oos_authorized(ROOT / "docs/handoff/CANDIDATE_UNIVERSE_FREEZE_N3.json", json.loads(Path(args.lock).read_text(encoding="utf-8")))
    register_existing_models(); register_model_pool(); validate_registry()
    dataset = build_research_dataset(args.lock)
    freeze = _load_freeze(Path(args.freeze_manifest), dataset.boundary.dataset_id)
    tasks = [(r, args.lock, args.raw_root, args.parquet_root) for r in freeze]
    results = []
    errors = []
    t0 = time.perf_counter()
    with concurrent.futures.ProcessPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(_worker_star, t) for t in tasks]
        for fut in concurrent.futures.as_completed(futs):
            r = fut.result()
            if r.get("fatal_error"):
                errors.append(r)
                print(f"失败 {r.get('symbol')}/{r.get('model')}", flush=True)
            else:
                results.append(r)
                print(f"完成 {r['symbol']}/{r['model']}", flush=True)
    results.sort(key=lambda x: (x["model"], x["symbol"]))
    report = {
        "phase": "2.3.5-D-2",
        "version": "1.0",
        "status": "PASS" if not errors and len(results) == len(tasks) else "FAIL",
        "purpose": "对D-1冻结参数进行一次性OOS样本外验证；不重新选择、不修改参数、不使用OOS反馈优化。",
        "dataset_id": dataset.boundary.dataset_id,
        "market": dataset.boundary.market,
        "interval": dataset.boundary.interval,
        "symbols": list(SYMBOLS),
        "models": list(EXPECTED_MODELS),
        "window": "OOS",
        "oos_boundary": next(w for w in dataset.windows if w.name == "OOS").__dict__ if False else {
            "start": next(w for w in dataset.windows if w.name == "OOS").start.isoformat(),
            "end": next(w for w in dataset.windows if w.name == "OOS").end.isoformat(),
        },
        "freeze_manifest": str(Path(args.freeze_manifest)),
        "selection_policy": "D-1冻结参数原样执行；OOS只做评估，不参与任何选择、调参或阈值修改。",
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
            "expected_evaluations": len(tasks),
            "completed_evaluations": len(results),
            "errors": len(errors),
            "positive_return": sum(1 for r in results if r["oos_metrics"]["total_return"] > 0),
            "pf_ge_1": sum(1 for r in results if r["oos_metrics"]["profit_factor"] >= 1.0),
            "positive_and_pf_ge_1": sum(1 for r in results if r["oos_metrics"]["total_return"] > 0 and r["oos_metrics"]["profit_factor"] >= 1.0),
        },
        "errors": errors,
        "results": results,
        "runtime_seconds": round(time.perf_counter() - t0, 3),
    }
    return report


def main() -> int:
    p = argparse.ArgumentParser(description="Phase 2.3.5-D-2 frozen OOS validation")
    p.add_argument("--lock", default=str(ROOT / "data/reports/research_boundary_lock.json"))
    p.add_argument("--raw-root", default=str(ROOT / "data/raw"))
    p.add_argument("--parquet-root", default=str(ROOT / "data/parquet"))
    p.add_argument("--freeze-manifest", default=str(DEFAULT_FREEZE))
    p.add_argument("--workers", type=int, default=6)
    p.add_argument("--output", default=str(ROOT / "data/reports/phase2_3_5_d2_oos_validation.json"))
    args = p.parse_args()
    if args.workers < 1:
        raise SystemExit("workers必须 >= 1")
    report = run(args)
    out = Path(args.output); out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    curve_path = out.with_name("phase2_3_5_d2_oos_equity_curves.jsonl")
    trade_path = out.with_name("phase2_3_5_d2_oos_trades.jsonl")
    with curve_path.open("w", encoding="utf-8") as fcurve, trade_path.open("w", encoding="utf-8") as ftrade:
        for r in report["results"]:
            for ts, equity in r["equity_curve"]:
                fcurve.write(json.dumps({"model": r["model"], "symbol": r["symbol"], "timestamp": ts, "equity": equity}, ensure_ascii=False) + "\n")
            for t in r["trades"]:
                ftrade.write(json.dumps({"model": r["model"], "symbol": r["symbol"], **t}, ensure_ascii=False) + "\n")
    summary_path = out.with_name("phase2_3_5_d2_summary.md")
    lines = [
        "# Phase 2.3.5-D-2 OOS验证总结", "",
        f"状态：{'通过' if report['status']=='PASS' else '失败'}",
        f"OOS评估：{report['counts']['completed_evaluations']}/{report['counts']['expected_evaluations']}",
        f"正收益：{report['counts']['positive_return']}/{report['counts']['completed_evaluations']}",
        f"PF≥1：{report['counts']['pf_ge_1']}/{report['counts']['completed_evaluations']}",
        f"正收益且PF≥1：{report['counts']['positive_and_pf_ge_1']}/{report['counts']['completed_evaluations']}",
        f"错误：{report['counts']['errors']}", "",
        "> 注意：这里的OOS结果只用于样本外评价，不自动改变D-1冻结参数，也不用于重新筛选。", "",
        "## OOS结果", "",
    ]
    for r in report["results"]:
        m = r["oos_metrics"]
        lines.append(f"- {r['model']} / {r['symbol']}: Return {m['total_return']:+.2%} | DD {m['max_drawdown']:.2%} | PF {m['profit_factor']:.3f} | Trades {m['trades']} | Params `{json.dumps(r['params'], ensure_ascii=False, sort_keys=True)}`")
    summary_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("=" * 72)
    print("Phase 2.3.5-D-2 冻结参数 OOS 验证")
    print("=" * 72)
    print(f"状态：{'通过' if report['status']=='PASS' else '失败'}")
    print(f"OOS：{report['counts']['completed_evaluations']}/{report['counts']['expected_evaluations']}")
    print(f"正收益：{report['counts']['positive_return']}/{report['counts']['completed_evaluations']}")
    print(f"PF>=1：{report['counts']['pf_ge_1']}/{report['counts']['completed_evaluations']}")
    print(f"错误：{report['counts']['errors']}")
    print(f"报告：{out}")
    print(f"资金曲线：{curve_path}")
    print(f"交易明细：{trade_path}")
    print(f"总结：{summary_path}")
    print("PHASE2_3_5_D2_OOS_VALIDATION_OK" if report["status"] == "PASS" else "PHASE2_3_5_D2_OOS_VALIDATION_FAILED")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
