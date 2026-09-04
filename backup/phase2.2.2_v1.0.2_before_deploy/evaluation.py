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


StrategyFn = Callable[..., pd.DataFrame]


def strategy_frame_to_signal_frame(
    strategy_frame: pd.DataFrame,
    *,
    risk_fraction: float,
    position_fraction: float,
    tag: str,
) -> dict[pd.Timestamp, Signal]:
    required = {"signal", "stop", "target"}
    missing = required - set(strategy_frame.columns)
    if missing:
        raise ValueError(f"strategy frame missing columns: {sorted(missing)}")

    if not isinstance(strategy_frame.index, pd.DatetimeIndex):
        raise TypeError("strategy frame index must be DatetimeIndex")
    if strategy_frame.index.tz is None:
        raise ValueError("strategy frame index must be timezone-aware")
    if not strategy_frame.index.is_monotonic_increasing:
        raise ValueError("strategy frame timestamps are not monotonic")
    if strategy_frame.index.has_duplicates:
        raise ValueError("strategy frame contains duplicate timestamps")

    result: dict[pd.Timestamp, Signal] = {}

    for ts, row in strategy_frame.iterrows():
        side = int(row["signal"])
        if side not in (-1, 0, 1):
            raise ValueError(f"invalid strategy signal at {ts}: {side}")

        if side == 0:
            continue

        stop = row["stop"]
        target = row["target"]

        stop_price = None if pd.isna(stop) else float(stop)
        take_profit = None if pd.isna(target) else float(target)

        result[ts] = Signal(
            timestamp=ts,
            side="buy" if side == 1 else "sell",
            stop_price=stop_price,
            take_profit=take_profit,
            risk_fraction=float(risk_fraction),
            position_fraction=float(position_fraction),
            tag=tag,
        )

    return result


def make_strategy_adapter(
    strategy: StrategyFn,
    *,
    params: Mapping[str, Any] | None = None,
    risk_fraction: float,
    position_fraction: float,
    tag: str,
) -> Callable[[pd.DataFrame, int], Signal | None]:
    params = dict(params or {})

    def adapter(df: pd.DataFrame, i: int) -> Signal | None:
        if i < 0 or i >= len(df):
            raise IndexError(f"strategy index out of range: {i}")

        # Compute the strategy only on history strictly before execution T.
        history = df.iloc[:i]
        if history.empty:
            return None

        evaluated = strategy(history, **params)

        # The final row is the most recent information available before T.
        if evaluated.empty:
            return None

        row = evaluated.iloc[-1]
        side = int(row["signal"])
        if side == 0:
            return None
        if side not in (-1, 1):
            raise ValueError(f"invalid strategy signal: {side}")

        stop = row["stop"]
        target = row["target"]

        return Signal(
            timestamp=df.index[i],
            side="buy" if side == 1 else "sell",
            stop_price=None if pd.isna(stop) else float(stop),
            take_profit=None if pd.isna(target) else float(target),
            risk_fraction=float(risk_fraction),
            position_fraction=float(position_fraction),
            tag=tag,
        )

    return adapter


def evaluate_strategy(
    *,
    symbol: str,
    window: str,
    frame: pd.DataFrame,
    strategy: StrategyFn,
    engine: BacktestEngine,
    params: Mapping[str, Any] | None = None,
    risk_fraction: float = 0.01,
    position_fraction: float = 1.0,
    tag: str = "",
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

    adapter = make_strategy_adapter(
        strategy,
        params=params,
        risk_fraction=risk_fraction,
        position_fraction=position_fraction,
        tag=tag or f"{symbol}:{window}",
    )

    result = engine.run({symbol: frame}, {symbol: adapter})

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
    params: Mapping[str, Any] | None = None,
    risk_fraction: float = 0.01,
    position_fraction: float = 1.0,
    tag: str = "",
) -> list[StrategyEvaluation]:
    return [
        evaluate_strategy(
            symbol=symbol,
            window=window,
            frame=frame,
            strategy=strategy,
            engine=engine_factory(),
            params=params,
            risk_fraction=risk_fraction,
            position_fraction=position_fraction,
            tag=tag or f"{symbol}:{window}",
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
