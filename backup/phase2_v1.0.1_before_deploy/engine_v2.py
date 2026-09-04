from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Callable, Iterable
import math
import pandas as pd

from .costs import CostModel


@dataclass(frozen=True)
class Signal:
    timestamp: pd.Timestamp
    side: str  # buy / sell / flat
    stop_price: float | None = None
    take_profit: float | None = None
    risk_fraction: float = 0.0
    position_fraction: float = 0.0
    tag: str = ""


@dataclass
class Position:
    symbol: str
    side: str
    qty: float
    entry_price: float
    entry_time: pd.Timestamp
    stop_price: float | None = None
    take_profit: float | None = None
    tag: str = ""
    entry_fee: float = 0.0

    @property
    def notional(self) -> float:
        return abs(self.qty * self.entry_price)


@dataclass
class Trade:
    symbol: str
    side: str
    entry_time: str
    exit_time: str
    qty: float
    entry_price: float
    exit_price: float
    gross_pnl: float
    fees: float
    slippage_cost: float
    net_pnl: float
    exit_reason: str
    tag: str


@dataclass
class BacktestResult:
    initial_equity: float
    final_equity: float
    equity_curve: pd.Series
    trades: list[Trade]
    rejected_signals: int
    skipped_gap_bars: int

    def metrics(self) -> dict:
        eq = self.equity_curve.astype(float)
        peak = eq.cummax()
        dd = (eq / peak) - 1.0
        net = [t.net_pnl for t in self.trades]
        wins = [x for x in net if x > 0]
        losses = [-x for x in net if x < 0]
        gross_profit = sum(wins)
        gross_loss = sum(losses)
        return {
            "initial": self.initial_equity,
            "final_equity": self.final_equity,
            "total_return": self.final_equity / self.initial_equity - 1.0,
            "max_drawdown": abs(float(dd.min())) if len(dd) else 0.0,
            "trades": len(self.trades),
            "win_rate": len(wins) / len(net) if net else 0.0,
            "profit_factor": gross_profit / gross_loss if gross_loss else math.inf,
            "rejected_signals": self.rejected_signals,
            "skipped_gap_bars": self.skipped_gap_bars,
        }


StrategyFn = Callable[[pd.DataFrame, int], Signal | None]


def _utc_ts(ts) -> pd.Timestamp:
    t = pd.Timestamp(ts)
    if t.tzinfo is None:
        return t.tz_localize("UTC")
    return t.tz_convert("UTC")


class BacktestEngine:
    """
    Conservative single-position event loop.

    Convention:
      - A strategy is evaluated at execution timestamp T.
      - It receives data strictly before T.
      - If a signal is accepted, entry is executed at T's open.
      - Exits are checked against the current candle high/low.
      - If stop and target are both touched in the same candle, stop wins
        (conservative ordering; no intrabar information is assumed).
      - One position per symbol in this V1 engine.
    """

    def __init__(
        self,
        initial_equity: float,
        cost_model: CostModel | None = None,
        max_position_fraction: float = 1.0,
        max_risk_fraction: float = 0.01,
        max_positions: int = 1,
        gap_indices: dict[str, set[pd.Timestamp]] | None = None,
    ):
        if initial_equity <= 0:
            raise ValueError("initial_equity must be positive")
        if not (0 < max_position_fraction <= 1):
            raise ValueError("max_position_fraction must be in (0,1]")
        if max_risk_fraction < 0:
            raise ValueError("max_risk_fraction must be non-negative")
        if max_positions < 1:
            raise ValueError("max_positions must be >= 1")

        self.initial_equity = float(initial_equity)
        self.cost_model = cost_model or CostModel()
        self.max_position_fraction = max_position_fraction
        self.max_risk_fraction = max_risk_fraction
        self.max_positions = max_positions
        self.gap_indices = gap_indices or {}

    def run(self, data: dict[str, pd.DataFrame], strategies: dict[str, StrategyFn]) -> BacktestResult:
        if set(data) != set(strategies):
            raise ValueError("data and strategies must contain the same symbols")

        timeline = sorted({_utc_ts(ts) for df in data.values() for ts in df.index})
        equity = self.initial_equity
        positions: dict[str, Position] = {}
        trades: list[Trade] = []
        curve = []
        rejected = 0
        skipped_gaps = 0

        for ts in timeline:
            # Mark-to-market at current candle close for reporting.
            current_bars = {
                symbol: df.loc[ts]
                for symbol, df in data.items()
                if ts in df.index
            }

            # Exit existing positions first.
            for symbol, pos in list(positions.items()):
                if symbol not in current_bars:
                    continue
                bar = current_bars[symbol]
                exit_reason = None
                exit_ref = None

                if pos.side == "buy":
                    stop_hit = pos.stop_price is not None and float(bar["low"]) <= pos.stop_price
                    tp_hit = pos.take_profit is not None and float(bar["high"]) >= pos.take_profit
                else:
                    stop_hit = pos.stop_price is not None and float(bar["high"]) >= pos.stop_price
                    tp_hit = pos.take_profit is not None and float(bar["low"]) <= pos.take_profit

                if stop_hit:
                    exit_reason, exit_ref = "stop", pos.stop_price
                elif tp_hit:
                    exit_reason, exit_ref = "take_profit", pos.take_profit

                if exit_ref is not None:
                    trade = self._close_position(pos, ts, float(exit_ref), exit_reason)
                    equity += trade.net_pnl
                    trades.append(trade)
                    del positions[symbol]

            # New entries at current candle open, but strategy sees only prior data.
            for symbol, df in data.items():
                if symbol in positions:
                    continue
                if ts not in df.index:
                    continue
                if ts in self.gap_indices.get(symbol, set()):
                    skipped_gaps += 1
                    continue
                if len(positions) >= self.max_positions:
                    break

                i = df.index.get_loc(ts)
                if i == 0:
                    continue
                if isinstance(i, slice):
                    continue

                signal = strategies[symbol](df, i)
                if signal is None or signal.side == "flat":
                    continue
                if _utc_ts(signal.timestamp) != ts:
                    rejected += 1
                    continue

                risk_fraction = signal.risk_fraction or self.max_risk_fraction
                position_fraction = signal.position_fraction or self.max_position_fraction
                if risk_fraction <= 0 or position_fraction <= 0:
                    rejected += 1
                    continue
                risk_fraction = min(risk_fraction, self.max_risk_fraction)
                position_fraction = min(position_fraction, self.max_position_fraction)

                bar = df.iloc[i]
                entry_ref = float(bar["open"])
                side = signal.side.lower()
                if side not in {"buy", "sell"}:
                    rejected += 1
                    continue

                stop = signal.stop_price
                if stop is None:
                    rejected += 1
                    continue

                risk_per_unit = abs(entry_ref - stop)
                if risk_per_unit <= 0:
                    rejected += 1
                    continue

                risk_budget = equity * risk_fraction
                qty_by_risk = risk_budget / risk_per_unit
                max_notional = equity * position_fraction
                qty_by_notional = max_notional / entry_ref
                qty = min(qty_by_risk, qty_by_notional)
                if qty <= 0:
                    rejected += 1
                    continue

                exec_price = self.cost_model.execution_price(entry_ref, "buy" if side == "buy" else "sell")
                notional = qty * exec_price
                fee = self.cost_model.trading_cost(notional)

                positions[symbol] = Position(
                    symbol=symbol,
                    side=side,
                    qty=qty,
                    entry_price=exec_price,
                    entry_time=ts,
                    stop_price=stop,
                    take_profit=signal.take_profit,
                    tag=signal.tag,
                    entry_fee=fee,
                )

            mtm = equity
            for symbol, pos in positions.items():
                if symbol in current_bars:
                    close = float(current_bars[symbol]["close"])
                    if pos.side == "buy":
                        mtm += (close - pos.entry_price) * pos.qty - pos.entry_fee
                    else:
                        mtm += (pos.entry_price - close) * pos.qty - pos.entry_fee
            curve.append((ts, mtm))

        # Force-close at last available close. This makes final equity explicit.
        for symbol, pos in list(positions.items()):
            df = data[symbol]
            last_ts = _utc_ts(df.index[-1])
            last_close = float(df.iloc[-1]["close"])
            trade = self._close_position(pos, last_ts, last_close, "end_of_data")
            equity += trade.net_pnl
            trades.append(trade)
            del positions[symbol]

        curve.append((timeline[-1], equity))
        curve_df = pd.Series({ts: val for ts, val in curve}).sort_index()
        return BacktestResult(
            initial_equity=self.initial_equity,
            final_equity=equity,
            equity_curve=curve_df,
            trades=trades,
            rejected_signals=rejected,
            skipped_gap_bars=skipped_gaps,
        )

    def _close_position(self, pos: Position, ts: pd.Timestamp,
                        reference_price: float, reason: str) -> Trade:
        exit_side = "sell" if pos.side == "buy" else "buy"
        exit_price = self.cost_model.execution_price(reference_price, exit_side)
        notional_entry = pos.qty * pos.entry_price
        notional_exit = pos.qty * exit_price

        if pos.side == "buy":
            gross = (exit_price - pos.entry_price) * pos.qty
        else:
            gross = (pos.entry_price - exit_price) * pos.qty

        exit_fee = self.cost_model.trading_cost(notional_exit)
        fees = pos.entry_fee + exit_fee
        ideal_exit = reference_price
        slippage_cost = abs(exit_price - ideal_exit) * pos.qty
        net = gross - fees

        return Trade(
            symbol=pos.symbol,
            side=pos.side,
            entry_time=pos.entry_time.isoformat(),
            exit_time=_utc_ts(ts).isoformat(),
            qty=pos.qty,
            entry_price=pos.entry_price,
            exit_price=exit_price,
            gross_pnl=gross,
            fees=fees,
            slippage_cost=slippage_cost,
            net_pnl=net,
            exit_reason=reason,
            tag=pos.tag,
        )
