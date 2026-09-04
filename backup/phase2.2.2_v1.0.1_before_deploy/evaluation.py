from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping, Any

import pandas as pd

from quantbot.backtest.engine_v2 import BacktestEngine, BacktestResult, Signal


@dataclass(frozen=True)
class StrategyEvaluation:
    symbol: str
    window: str
    rows: int
    first_timestamp: str | None
    last_timestamp: str | None
    backtest: BacktestResult


StrategyFn = Callable[[pd.DataFrame, int], Signal | None]


def evaluate_strategy(
    *,
    symbol: str,
    window: str,
    frame: pd.DataFrame,
    strategy: StrategyFn,
    engine: BacktestEngine,
) -> StrategyEvaluation:
    if frame.empty:
        raise ValueError(f"{symbol}/{window}: empty research frame")
    if not isinstance(frame.index, pd.DatetimeIndex):
        raise TypeError(f"{symbol}/{window}: index must be DatetimeIndex")
    if frame.index.tz is None:
        raise ValueError(f"{symbol}/{window}: index must be timezone-aware")
    if not frame.index.is_monotonic_increasing:
        raise ValueError(f"{symbol}/{window}: timestamps are not monotonic")
    if frame.index.has_duplicates:
        raise ValueError(f"{symbol}/{window}: duplicate timestamps")

    result = engine.run({symbol: frame}, {symbol: strategy})

    return StrategyEvaluation(
        symbol=symbol,
        window=window,
        rows=len(frame),
        first_timestamp=frame.index[0].isoformat(),
        last_timestamp=frame.index[-1].isoformat(),
        backtest=result,
    )


def evaluate_windows(
    *,
    symbol: str,
    frames_by_window: Mapping[str, pd.DataFrame],
    strategy: StrategyFn,
    engine_factory: Callable[[], BacktestEngine],
) -> list[StrategyEvaluation]:
    return [
        evaluate_strategy(
            symbol=symbol,
            window=window,
            frame=frame,
            strategy=strategy,
            engine=engine_factory(),
        )
        for window, frame in frames_by_window.items()
    ]


def evaluation_to_dict(item: StrategyEvaluation) -> dict[str, Any]:
    result = item.backtest
    trades = []

    for trade in result.trades:
        trades.append({
            "symbol": trade.symbol,
            "entry_time": trade.entry_time,
            "exit_time": trade.exit_time,
            "side": trade.side,
            "qty": trade.qty,
            "entry_price": trade.entry_price,
            "exit_price": trade.exit_price,
            "gross_pnl": trade.gross_pnl,
            "fees": trade.fees,
            "slippage_cost": trade.slippage_cost,
            "net_pnl": trade.net_pnl,
            "exit_reason": trade.exit_reason,
            "tag": trade.tag,
        })

    return {
        "symbol": item.symbol,
        "window": item.window,
        "rows": item.rows,
        "first_timestamp": item.first_timestamp,
        "last_timestamp": item.last_timestamp,
        "initial_equity": result.initial_equity,
        "final_equity": result.final_equity,
        "halted": getattr(result, "halted", False),
        "rejected_signals": result.rejected_signals,
        "skipped_gap_bars": result.skipped_gap_bars,
        "gap_bars_seen": result.gap_bars_seen,
        "trades": trades,
        "metrics": result.metrics(),
    }
