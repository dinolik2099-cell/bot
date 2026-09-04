from __future__ import annotations

import argparse
import inspect
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from quantbot.backtest.costs import CostModel
from quantbot.backtest.engine_v2 import BacktestEngine
from quantbot.research.integration import load_boundary_lock
from quantbot.research.evaluation import make_strategy_adapter
from quantbot.research.model_registry import (
    get_model,
    list_models,
    register_existing_models,
    validate_registry,
)
from quantbot.research.runner import load_research_frames, split_frame, build_research_dataset
from quantbot.strategies.model_pool import register_model_pool


INITIAL_EQUITY = 10_000.0
RISK_FRACTION = 0.01
POSITION_FRACTION = 1.0
MAX_RISK_FRACTION = 0.01
MAX_POSITIONS = 1


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Phase 2.3.5 真实数据预检")
    p.add_argument("--symbol", default="BTCUSDT")
    p.add_argument("--window", default="TRAIN", choices=["TRAIN", "VALIDATION", "OOS"])
    p.add_argument("--boundary", default="data/reports/research_boundary_lock.json")
    p.add_argument("--raw-root", default="data/raw")
    p.add_argument("--parquet-root", default="data/parquet")
    p.add_argument("--rows", type=int, default=4000, help="预检使用的TRAIN代表性K线数；0表示全部")
    p.add_argument("--output", default="data/reports/phase2_3_5_real_data_preflight.json")
    return p.parse_args()


def default_params(fn) -> dict[str, Any]:
    sig = inspect.signature(fn)
    out: dict[str, Any] = {}
    for name, param in sig.parameters.items():
        if name == "df" or param.default is inspect.Parameter.empty:
            continue
        out[name] = param.default
    return out


def utc(value) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    return ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")


def gap_indices(dataset, symbol: str) -> set[pd.Timestamp]:
    out: set[pd.Timestamp] = set()
    for gap in dataset.boundary.gaps:
        if gap.symbol != symbol:
            continue
        step = (gap.next - gap.previous) / (gap.missing_bars + 1)
        ts = gap.previous + step
        for _ in range(gap.missing_bars):
            out.add(ts)
            ts += step
    return out


def engine_for(dataset, symbol: str) -> BacktestEngine:
    return BacktestEngine(
        initial_equity=INITIAL_EQUITY,
        cost_model=CostModel(fee_rate=0.0004, slippage_bps=2.0, funding_rate_per_8h=0.0),
        max_position_fraction=POSITION_FRACTION,
        max_risk_fraction=MAX_RISK_FRACTION,
        max_positions=MAX_POSITIONS,
        gap_indices={symbol: gap_indices(dataset, symbol)},
    )


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


def future_sensitivity_check(strategy, frame: pd.DataFrame, params: dict[str, Any]) -> None:
    n = len(frame)
    if n < 200:
        raise ValueError("真实数据预检需要至少 200 根 K 线")
    cut = n // 2
    a = strategy(frame.copy(), **params)
    bframe = frame.copy()
    future_slice = bframe.iloc[cut:].copy()
    # Deliberately alter only data strictly after the checked prefix.
    bframe.loc[bframe.index[cut:], "close"] *= 1.137
    bframe.loc[bframe.index[cut:], "high"] *= 1.137
    bframe.loc[bframe.index[cut:], "low"] *= 1.137
    b = strategy(bframe, **params)
    cols = ["signal", "stop", "target"]
    left = a.iloc[:cut][cols].to_numpy(dtype=float)
    right = b.iloc[:cut][cols].to_numpy(dtype=float)
    if not np.allclose(left, right, equal_nan=True, rtol=0.0, atol=1e-12):
        raise AssertionError("未来数据敏感性检查失败：未来K线改变了此前信号")


def main() -> int:
    args = parse_args()
    boundary = load_boundary_lock(args.boundary)
    dataset = build_research_dataset(args.boundary)
    frames, sources = load_research_frames(
        dataset, args.raw_root, args.parquet_root, [args.symbol]
    )
    frame = split_frame(dataset, frames[args.symbol], args.window)
    validate_frame(frame, args.symbol, args.window)
    source_rows = len(frame)
    if args.rows < 0:
        raise ValueError("--rows 不能小于0")
    if args.rows:
        if args.rows < 200:
            raise ValueError("--rows 至少需要200")
        frame = frame.iloc[: min(args.rows, len(frame))].copy()
    validate_frame(frame, args.symbol, args.window)

    register_existing_models()
    register_model_pool()
    validate_registry()
    models = list_models()
    if len(models) != 36:
        raise AssertionError(f"模型数量异常：期望36，实际{len(models)}")

    results: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []

    for item in models:
        name = item.spec.name
        params = default_params(item.strategy)
        record: dict[str, Any] = {
            "model": name,
            "category": item.spec.category,
            "params": params,
            "status": "失败",
        }
        try:
            future_sensitivity_check(item.strategy, frame, params)
            evaluated = item.strategy(frame.copy(), **params)
            if len(evaluated) != len(frame):
                raise ValueError("策略输出长度与输入不一致")
            if not evaluated.index.equals(frame.index):
                raise ValueError("策略输出时间索引与输入不一致")

            signal_rows = evaluated.loc[evaluated["signal"] != 0]
            if not signal_rows.empty:
                finite_stop = np.isfinite(signal_rows["stop"].astype(float).to_numpy())
                finite_target = np.isfinite(signal_rows["target"].astype(float).to_numpy())
                if not finite_stop.all() or not finite_target.all():
                    raise ValueError("存在非零信号但止损/止盈不是有限数值")

            adapter = make_strategy_adapter(
                item.strategy,
                full_frame=frame,
                params=params,
                risk_fraction=RISK_FRACTION,
                position_fraction=POSITION_FRACTION,
                tag=f"phase2.3.5-preflight:{name}:{args.symbol}:{args.window}",
            )
            result = engine_for(dataset, args.symbol).run(
                {args.symbol: frame}, {args.symbol: adapter}
            )
            metrics = result.metrics()
            record.update({
                "status": "通过",
                "rows": len(frame),
        "source_window_rows": source_rows,
                "signal_rows": int(len(signal_rows)),
                "trades": int(metrics["trades"]),
                "rejected_signals": int(metrics["rejected_signals"]),
                "skipped_gap_bars": int(metrics["skipped_gap_bars"]),
                "gap_bars_seen": int(metrics["gap_bars_seen"]),
                "total_return": float(metrics["total_return"]),
                "max_drawdown": float(metrics["max_drawdown"]),
                "profit_factor": float(metrics["profit_factor"]) if np.isfinite(metrics["profit_factor"]) else None,
            })
            results.append(record)
        except Exception as exc:
            record["error"] = repr(exc)
            results.append(record)
            errors.append({"model": name, "error": repr(exc)})

    report = {
        "status": "通过" if not errors else "失败",
        "dataset_id": boundary.dataset_id,
        "market": boundary.market,
        "interval": boundary.interval,
        "symbol": args.symbol,
        "window": args.window,
        "data_source": sources[args.symbol],
        "rows": len(frame),
        "first_timestamp": frame.index[0].isoformat(),
        "last_timestamp": frame.index[-1].isoformat(),
        "model_count": len(models),
        "passed": len(models) - len(errors),
        "failed": len(errors),
        "results": results,
        "errors": errors,
        "policies": {
            "lookahead": "future_sensitivity + existing pre-T strategy adapter",
            "execution": "T OPEN",
            "cost": "fee 0.04%, slippage 2bps",
            "oos_used": False,
            "parameter_search": False,
        },
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=" * 72)
    print("QuantBot Phase 2.3.5 真实数据预检")
    print("=" * 72)
    print(f"数据集：{boundary.dataset_id}")
    print(f"范围：{args.symbol} / {args.window}")
    print(f"数据源：{sources[args.symbol]}")
    print(f"预检K线数：{len(frame)} / TRAIN完整窗口：{source_rows}")
    print(f"模型数：{len(models)}")
    print(f"通过：{len(models) - len(errors)}")
    print(f"失败：{len(errors)}")
    print(f"报告：{output.resolve()}")
    if errors:
        print("\n失败模型：")
        for err in errors:
            print(f"- {err['model']}: {err['error']}")
        print("PHASE2_3_5_REAL_DATA_PREFLIGHT_FAILED")
        return 1

    print("全部36个模型完成：真实数据→因果检查→Strategy Adapter→Backtest Engine")
    print("本次只做接口/因果/执行链路预检，不代表正式研究结果")
    print("OOS 未参与，未进行参数搜索")
    print("PHASE2_3_5_REAL_DATA_PREFLIGHT_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
