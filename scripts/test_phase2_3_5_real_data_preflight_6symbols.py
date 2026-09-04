from __future__ import annotations

import argparse
import inspect
import json
import sys
import time
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from quantbot.backtest.costs import CostModel
from quantbot.backtest.engine_v2 import BacktestEngine
from quantbot.research.evaluation import make_strategy_adapter
from quantbot.research.integration import load_boundary_lock
from quantbot.research.model_registry import list_models, register_existing_models, validate_registry
from quantbot.research.runner import build_research_dataset, load_research_frames, split_frame
from quantbot.strategies.model_pool import register_model_pool

SYMBOLS = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT"]
INITIAL_EQUITY = 10_000.0
RISK_FRACTION = 0.01
POSITION_FRACTION = 1.0
MAX_RISK_FRACTION = 0.01
MAX_POSITIONS = 1


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Phase 2.3.5-B 六币种×36模型真实数据预检")
    p.add_argument("--symbol", default=None, choices=SYMBOLS, help=argparse.SUPPRESS)
    p.add_argument("--window", default="TRAIN", choices=["TRAIN", "VALIDATION", "OOS"])
    p.add_argument("--boundary", default="data/reports/research_boundary_lock.json")
    p.add_argument("--raw-root", default="data/raw")
    p.add_argument("--parquet-root", default="data/parquet")
    p.add_argument("--rows", type=int, default=1500, help="每个币种用于完整执行链预检的代表性K线数；0表示整个窗口")
    p.add_argument("--gap-probe-rows", type=int, default=120, help="每个缺口两侧额外检查的K线数量")
    p.add_argument("--output", default="data/reports/phase2_3_5_real_data_preflight_6symbols.json")
    return p.parse_args()


def default_params(fn) -> dict[str, Any]:
    sig = inspect.signature(fn)
    return {
        name: param.default
        for name, param in sig.parameters.items()
        if name != "df" and param.default is not inspect.Parameter.empty
    }


def validate_frame(frame: pd.DataFrame, symbol: str, window: str) -> None:
    if frame.empty:
        raise ValueError(f"{symbol}/{window}: 数据为空")
    if not isinstance(frame.index, pd.DatetimeIndex):
        raise TypeError(f"{symbol}/{window}: index 不是 DatetimeIndex")
    if frame.index.tz is None:
        raise ValueError(f"{symbol}/{window}: index 没有时区")
    if not frame.index.is_monotonic_increasing:
        raise ValueError(f"{symbol}/{window}: 时间未排序")
    if frame.index.has_duplicates:
        raise ValueError(f"{symbol}/{window}: 存在重复时间戳")
    required = {"open", "high", "low", "close", "volume"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"{symbol}/{window}: 缺少字段 {sorted(missing)}")
    values = frame[["open", "high", "low", "close", "volume"]].to_numpy(dtype=float)
    if not np.isfinite(values).all():
        raise ValueError(f"{symbol}/{window}: OHLCV 存在 NaN/Inf")
    if (frame["high"] < frame[["open", "close"]].max(axis=1)).any():
        raise ValueError(f"{symbol}/{window}: high 小于 open/close")
    if (frame["low"] > frame[["open", "close"]].min(axis=1)).any():
        raise ValueError(f"{symbol}/{window}: low 大于 open/close")
    if (frame["low"] <= 0).any() or (frame["open"] <= 0).any() or (frame["close"] <= 0).any():
        raise ValueError(f"{symbol}/{window}: OHLC 存在非正价格")
    if (frame["volume"] < 0).any():
        raise ValueError(f"{symbol}/{window}: volume 存在负数")


def future_sensitivity_check(strategy, frame: pd.DataFrame, params: dict[str, Any]) -> None:
    n = len(frame)
    if n < 200:
        raise ValueError("真实数据预检需要至少200根K线")
    cut = n // 2
    a = strategy(frame.copy(), **params)
    bframe = frame.copy()
    bframe.loc[bframe.index[cut:], "close"] *= 1.137
    bframe.loc[bframe.index[cut:], "high"] *= 1.137
    bframe.loc[bframe.index[cut:], "low"] *= 1.137
    b = strategy(bframe, **params)
    cols = ["signal", "stop", "target"]
    left = a.iloc[:cut][cols].to_numpy(dtype=float)
    right = b.iloc[:cut][cols].to_numpy(dtype=float)
    if not np.allclose(left, right, equal_nan=True, rtol=0.0, atol=1e-12):
        raise AssertionError("未来数据敏感性检查失败：未来K线改变了此前信号")


def gap_info(dataset, symbol: str) -> list[dict[str, Any]]:
    out = []
    for gap in dataset.boundary.gaps:
        if gap.symbol != symbol:
            continue
        out.append({
            "previous": pd.Timestamp(gap.previous).isoformat(),
            "next": pd.Timestamp(gap.next).isoformat(),
            "missing_bars": int(gap.missing_bars),
        })
    return out


def gap_probe_frames(frame: pd.DataFrame, gaps: list[dict[str, Any]], rows: int) -> list[pd.DataFrame]:
    if rows <= 0 or not gaps:
        return []
    probes = []
    for gap in gaps:
        previous = pd.Timestamp(gap["previous"])
        nxt = pd.Timestamp(gap["next"])
        mask = (frame.index >= previous - pd.Timedelta(hours=rows)) & (frame.index <= nxt + pd.Timedelta(hours=rows))
        part = frame.loc[mask].copy()
        if not part.empty:
            probes.append(part)
    return probes


def engine_for() -> BacktestEngine:
    return BacktestEngine(
        initial_equity=INITIAL_EQUITY,
        cost_model=CostModel(fee_rate=0.0004, slippage_bps=2.0, funding_rate_per_8h=0.0),
        max_position_fraction=POSITION_FRACTION,
        max_risk_fraction=MAX_RISK_FRACTION,
        max_positions=MAX_POSITIONS,
    )


def run_symbol(symbol: str, window: str, boundary_path: str, raw_root: str, parquet_root: str, rows: int, gap_probe_rows: int) -> dict[str, Any]:
    boundary = load_boundary_lock(boundary_path)
    dataset = build_research_dataset(boundary_path)
    frames, sources = load_research_frames(dataset, raw_root, parquet_root, [symbol])
    if not list_models():
        register_existing_models()
        register_model_pool()
    validate_registry()
    models = list_models()
    if len(models) != 36:
        raise AssertionError(f"模型数量异常：期望36，实际{len(models)}")

    source_frame = split_frame(dataset, frames[symbol], window)
    validate_frame(source_frame, symbol, window)
    full_rows = len(source_frame)
    test_frame = source_frame if rows == 0 else source_frame.iloc[: min(rows, full_rows)].copy()
    validate_frame(test_frame, symbol, window)
    gaps = gap_info(dataset, symbol)
    probes = gap_probe_frames(source_frame, gaps, gap_probe_rows)

    results: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for item in models:
        name = item.spec.name
        params = default_params(item.strategy)
        record: dict[str, Any] = {
            "symbol": symbol, "model": name, "category": item.spec.category,
            "params": params, "window": window, "status": "失败",
            "rows": len(test_frame), "source_window_rows": full_rows,
            "configured_gaps": gaps,
        }
        try:
            future_sensitivity_check(item.strategy, test_frame, params)
            evaluated = item.strategy(test_frame.copy(), **params)
            if len(evaluated) != len(test_frame):
                raise ValueError("策略输出长度与输入不一致")
            if not evaluated.index.equals(test_frame.index):
                raise ValueError("策略输出时间索引与输入不一致")
            required_output = {"signal", "stop", "target"}
            if not required_output.issubset(evaluated.columns):
                raise ValueError(f"策略输出缺少字段：{sorted(required_output - set(evaluated.columns))}")
            signal_rows = evaluated.loc[evaluated["signal"] != 0]
            if not signal_rows.empty:
                if not np.isfinite(signal_rows["stop"].astype(float).to_numpy()).all():
                    raise ValueError("存在非零信号但止损不是有限数值")
                if not np.isfinite(signal_rows["target"].astype(float).to_numpy()).all():
                    raise ValueError("存在非零信号但止盈不是有限数值")
            adapter = make_strategy_adapter(
                strategy=item.strategy, full_frame=test_frame, params=params,
                risk_fraction=RISK_FRACTION, position_fraction=POSITION_FRACTION,
                tag=f"phase2.3.5-B:{name}:{symbol}:{window}",
            )
            metrics = engine_for().run({symbol: test_frame}, {symbol: adapter}).metrics()
            probe_trade_count = 0
            for probe in probes:
                if len(probe) < 200:
                    continue
                probe_adapter = make_strategy_adapter(
                    strategy=item.strategy, full_frame=probe, params=params,
                    risk_fraction=RISK_FRACTION, position_fraction=POSITION_FRACTION,
                    tag=f"phase2.3.5-B-gap:{name}:{symbol}:{window}",
                )
                probe_metrics = engine_for().run({symbol: probe}, {symbol: probe_adapter}).metrics()
                probe_trade_count += int(probe_metrics["trades"])
            record.update({
                "status": "通过", "signal_rows": int(len(signal_rows)),
                "trades": int(metrics["trades"]), "rejected_signals": int(metrics["rejected_signals"]),
                "skipped_gap_bars": int(metrics["skipped_gap_bars"]), "gap_bars_seen": int(metrics["gap_bars_seen"]),
                "gap_probe_count": len(probes), "gap_probe_trades": probe_trade_count,
                "total_return": float(metrics["total_return"]), "max_drawdown": float(metrics["max_drawdown"]),
                "profit_factor": float(metrics["profit_factor"]) if np.isfinite(metrics["profit_factor"]) else None,
            })
        except Exception as exc:
            record["error"] = repr(exc)
            errors.append({"model": name, "error": repr(exc)})
        results.append(record)

    return {
        "symbol": symbol, "data_source": sources[symbol], "source_window_rows": full_rows,
        "preflight_rows": len(test_frame), "first_timestamp": test_frame.index[0].isoformat(),
        "last_timestamp": test_frame.index[-1].isoformat(), "configured_gap_count": len(gaps),
        "configured_missing_bars": int(sum(g["missing_bars"] for g in gaps)),
        "gap_probe_count": len(probes), "passed": 36 - len(errors), "failed": len(errors),
        "errors": errors, "results": results,
    }


def write_child_report(summary: dict[str, Any], output: str, boundary, window: str) -> int:
    report = {
        "status": "通过" if summary["passed"] == 36 and summary["failed"] == 0 else "失败",
        "phase": "2.3.5-B-child", "dataset_id": boundary.dataset_id,
        "market": boundary.market, "interval": boundary.interval, "window": window,
        "symbol": summary["symbol"], "model_count": 36,
        "passed": summary["passed"], "failed": summary["failed"],
        "symbol_summary": {k: v for k, v in summary.items() if k != "results"},
        "errors": summary["errors"], "results": summary["results"],
    }
    path = Path(output); path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{summary['symbol']}: {summary['passed']}/36 通过，失败 {summary['failed']}，缺口 {summary['configured_gap_count']} 个/{summary['configured_missing_bars']} 根", flush=True)
    return 0 if report["status"] == "通过" else 1


def child_main(args: argparse.Namespace) -> int:
    boundary = load_boundary_lock(args.boundary)
    summary = run_symbol(args.symbol, args.window, args.boundary, args.raw_root, args.parquet_root, args.rows, args.gap_probe_rows)
    return write_child_report(summary, args.output, boundary, args.window)


def run_child_process(symbol: str, args: argparse.Namespace, output: str) -> tuple[str, int, str]:
    cmd = [
        sys.executable, str(Path(__file__).resolve()),
        "--symbol", symbol, "--window", args.window,
        "--boundary", args.boundary, "--raw-root", args.raw_root,
        "--parquet-root", args.parquet_root, "--rows", str(args.rows),
        "--gap-probe-rows", str(args.gap_probe_rows), "--output", output,
    ]
    proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True)
    return symbol, proc.returncode, (proc.stdout + proc.stderr).strip()


def main() -> int:
    args = parse_args()
    if args.symbol:
        return child_main(args)
    if args.rows < 0 or args.gap_probe_rows < 0:
        raise ValueError("--rows 和 --gap-probe-rows 不能小于0")
    if args.rows and args.rows < 200:
        raise ValueError("--rows 至少需要200")

    started = time.perf_counter()
    boundary = load_boundary_lock(args.boundary)
    all_results: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    summaries: dict[str, Any] = {}

    with tempfile.TemporaryDirectory(prefix="quantbot_p235b_") as tmpdir:
        # 每个币种使用独立Python进程，避免注册表/全局状态在多币种连续运行时互相污染。
        # 顺序执行优先保证确定性和稳定性；单币种约十几秒，总耗时通常在两分钟以内。
        for symbol in SYMBOLS:
            out = str(Path(tmpdir) / f"{symbol}.json")
            got_symbol, rc, log = run_child_process(symbol, args, out)
            if Path(out).exists():
                child_report = json.loads(Path(out).read_text(encoding="utf-8"))
                all_results.extend(child_report.get("results", []))
                summaries[symbol] = child_report.get("symbol_summary", {})
                errors.extend({"symbol": symbol, **e} for e in child_report.get("errors", []))
                print(log.splitlines()[-1] if log else f"{symbol}: 子进程完成", flush=True)
            else:
                summaries[symbol] = {"passed": 0, "failed": 36, "errors": [{"error": log or f"子进程退出码 {rc}"}]}
                errors.append({"symbol": symbol, "model": "<symbol-worker>", "error": log or f"returncode={rc}"})

    passed = sum(1 for r in all_results if r.get("status") == "通过")
    failed = 216 - passed
    report = {
        "status": "通过" if passed == 216 else "失败",
        "phase": "2.3.5-B", "dataset_id": boundary.dataset_id,
        "market": boundary.market, "interval": boundary.interval, "window": args.window,
        "symbols": SYMBOLS, "model_count": 36, "expected_cells": 216,
        "completed_cells": len(all_results), "passed": passed, "failed": failed,
        "symbol_summary": dict(sorted(summaries.items())), "errors": errors,
        "results": all_results, "parallel_workers": 1,
        "policies": {
            "lookahead": "future_sensitivity + existing pre-T strategy adapter",
            "execution": "T OPEN", "cost": "fee 0.04%, slippage 2bps",
            "gaps": "不补K线；缺口时间不存在可交易bar；缺口前后额外做局部执行链预检",
            "oos_used_for_selection": False, "parameter_search": False, "parameter_selection": False,
            "purpose": "六币种×36模型真实数据接口/因果/执行链预检，不代表正式研究结果",
        },
        "runtime_seconds": round(time.perf_counter() - started, 3),
    }
    output = Path(args.output); output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("=" * 72)
    print("QuantBot Phase 2.3.5-B 六币种×36模型真实数据预检")
    print("=" * 72)
    print(f"数据集：{boundary.dataset_id}")
    print(f"范围：{args.window}")
    print(f"币种：{', '.join(SYMBOLS)}")
    print("模型：36")
    print(f"组合：{len(all_results)}/216")
    print(f"通过：{passed}")
    print(f"失败：{failed}")
    print("独立子进程：逐币种顺序执行")
    print(f"耗时：{report['runtime_seconds']} 秒")
    print(f"报告：{output.resolve()}")
    if failed:
        print("\n失败组合：")
        for err in errors:
            print(f"- {err['symbol']} / {err['model']}: {err['error']}")
        print("PHASE2_3_5_REAL_DATA_PREFLIGHT_6SYMBOLS_FAILED")
        return 1
    print("216个组合全部通过：真实数据→因果检查→Strategy Adapter→Backtest Engine")
    print("SOL/XRP历史缺口未补K线，并完成缺口前后局部执行链预检")
    print("本次不做参数搜索、不做模型选择、不使用OOS进行筛选")
    print("PHASE2_3_5_REAL_DATA_PREFLIGHT_6SYMBOLS_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
