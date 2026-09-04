from __future__ import annotations

from dataclasses import dataclass
from typing import Callable
import math
import pandas as pd

from .costs import CostModel


@dataclass(frozen=True)
class Signal:
    timestamp: pd.Timestamp
    side: str
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
    entry_bar_index: int
    stop_price: float
    take_profit: float | None
    tag: str
    entry_fee: float


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
    gap_bars_seen: int

    def metrics(self) -> dict:
        eq = self.equity_curve.astype(float)
        peak = eq.cummax()
        dd = (eq / peak) - 1.0
        net = [t.net_pnl for t in self.trades]
        wins = [x for x in net if x > 0]
        losses = [-x for x in net if x < 0]
        gp, gl = sum(wins), sum(losses)
        return {
            "initial": self.initial_equity,
            "final_equity": self.final_equity,
            "total_return": self.final_equity / self.initial_equity - 1.0,
            "max_drawdown": abs(float(dd.min())) if len(dd) else 0.0,
            "trades": len(self.trades),
            "win_rate": len(wins) / len(net) if net else 0.0,
            "profit_factor": gp / gl if gl else math.inf,
            "rejected_signals": self.rejected_signals,
            "skipped_gap_bars": self.skipped_gap_bars,
            "gap_bars_seen": self.gap_bars_seen,
        }


StrategyFn = Callable[[pd.DataFrame, int], Signal | None]


def _utc(ts) -> pd.Timestamp:
    t = pd.Timestamp(ts)
    return t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")


class BacktestEngine:
    """
    PHASE 2 V1.2.1.

    Execution contract:
      1. Strategy input at T is strictly pre-T history.
      2. Accepted entry executes at T OPEN.
      3. The entry candle cannot trigger the new position's SL/TP.
      4. SL/TP checks start from the next actual candle.
      5. If a later OHLC candle touches both SL and TP, STOP wins.
      6. Gap timestamps are never synthesized and never generate entries.
      7. End-of-data positions close at the final actual close.

    Gap accounting:
      - gap_bars_seen: configured gap timestamps that are actually present
        on the engine timeline.
      - skipped_gap_bars: present configured gap timestamps at which an
        entry would otherwise be evaluated.
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
        if not 0 < max_position_fraction <= 1:
            raise ValueError("max_position_fraction must be in (0,1]")
        if max_risk_fraction < 0:
            raise ValueError("max_risk_fraction must be non-negative")
        if max_positions < 1:
            raise ValueError("max_positions must be >= 1")

        self.initial_equity = float(initial_equity)
        self.cost_model = cost_model or CostModel()
        self.max_position_fraction = float(max_position_fraction)
        self.max_risk_fraction = float(max_risk_fraction)
        self.max_positions = int(max_positions)
        self.gap_indices = {
            symbol: {_utc(ts) for ts in timestamps}
            for symbol, timestamps in (gap_indices or {}).items()
        }

    def run(self, data: dict[str, pd.DataFrame], strategies: dict[str, StrategyFn]) -> BacktestResult:
        if not data or set(data) != set(strategies):
            raise ValueError("data and strategies must contain the same non-empty symbols")

        for symbol, df in data.items():
            if not isinstance(df.index, pd.DatetimeIndex):
                raise TypeError(f"{symbol}: index must be DatetimeIndex")
            if df.index.tz is None:
                raise ValueError(f"{symbol}: index must be timezone-aware")
            if not df.index.is_monotonic_increasing:
                raise ValueError(f"{symbol}: index must be sorted")
            if df.index.has_duplicates:
                raise ValueError(f"{symbol}: duplicate timestamps")
            if not {"open", "high", "low", "close"}.issubset(df.columns):
                raise ValueError(f"{symbol}: missing OHLC columns")

        timeline = sorted({_utc(ts) for df in data.values() for ts in df.index})
        if not timeline:
            raise ValueError("No timestamps available")

        timeline_sets = {
            symbol: set(_utc(ts) for ts in df.index) for symbol, df in data.items()
        }
        gap_timeline = {
            symbol: self.gap_indices.get(symbol, set()) & set(timeline)
            for symbol in data
        }
        gap_bars_seen = sum(len(x) for x in gap_timeline.values())

        equity = self.initial_equity
        positions: dict[str, Position] = {}
        trades: list[Trade] = []
        curve: list[tuple[pd.Timestamp, float]] = []
        rejected = 0
        skipped_gaps = 0

        for ts in timeline:
            current = {
                symbol: df.loc[ts]
                for symbol, df in data.items()
                if ts in df.index
            }

            for symbol, pos in list(positions.items()):
                df = data[symbol]
                i = df.index.get_indexer([ts])[0]
                if i < 0 or i <= pos.entry_bar_index:
                    continue

                bar = current.get(symbol)
                if bar is None:
                    continue

                if pos.side == "buy":
                    stop_hit = float(bar["low"]) <= pos.stop_price
                    target_hit = (
                        pos.take_profit is not None
                        and float(bar["high"]) >= pos.take_profit
                    )
                else:
                    stop_hit = float(bar["high"]) >= pos.stop_price
                    target_hit = (
                        pos.take_profit is not None
                        and float(bar["low"]) <= pos.take_profit
                    )

                if stop_hit or target_hit:
                    reason = "stop" if stop_hit else "take_profit"
                    reference = pos.stop_price if stop_hit else pos.take_profit
                    trade = self._close_position(pos, ts, float(reference), reason)
                    equity += trade.net_pnl
                    trades.append(trade)
                    del positions[symbol]

            for symbol, df in data.items():
                if ts not in df.index:
                    continue

                i = df.index.get_loc(ts)
                if not isinstance(i, int) or i <= 0:
                    continue

                if ts in gap_timeline.get(symbol, set()):
                    skipped_gaps += 1
                    continue

                if symbol in positions:
                    continue
                if len(positions) >= self.max_positions:
                    break

                history = df.iloc[:i].copy()
                signal = strategies[symbol](history, i)
                if signal is None or signal.side.lower() == "flat":
                    continue

                if _utc(signal.timestamp) != ts:
                    rejected += 1
                    continue

                side = signal.side.lower()
                if side not in {"buy", "sell"} or signal.stop_price is None:
                    rejected += 1
                    continue

                risk_fraction = min(
                    float(signal.risk_fraction or self.max_risk_fraction),
                    self.max_risk_fraction,
                )
                position_fraction = min(
                    float(signal.position_fraction or self.max_position_fraction),
                    self.max_position_fraction,
                )
                if risk_fraction <= 0 or position_fraction <= 0:
                    rejected += 1
                    continue

                entry_reference = float(df.iloc[i]["open"])
                stop_price = float(signal.stop_price)
                risk_per_unit = abs(entry_reference - stop_price)
                if risk_per_unit <= 0:
                    rejected += 1
                    continue

                risk_budget = equity * risk_fraction
                qty_by_risk = risk_budget / risk_per_unit
                qty_by_notional = equity * position_fraction / entry_reference
                qty = min(qty_by_risk, qty_by_notional)
                if qty <= 0:
                    rejected += 1
                    continue

                entry_price = self.cost_model.execution_price(
                    entry_reference, "buy" if side == "buy" else "sell"
                )
                entry_fee = self.cost_model.trading_cost(qty * entry_price)

                positions[symbol] = Position(
                    symbol=symbol,
                    side=side,
                    qty=qty,
                    entry_price=entry_price,
                    entry_time=ts,
                    entry_bar_index=i,
                    stop_price=stop_price,
                    take_profit=signal.take_profit,
                    tag=signal.tag,
                    entry_fee=entry_fee,
                )

            mtm = equity
            for symbol, pos in positions.items():
                bar = current.get(symbol)
                if bar is None:
                    continue
                close = float(bar["close"])
                unrealized = (
                    (close - pos.entry_price) * pos.qty
                    if pos.side == "buy"
                    else (pos.entry_price - close) * pos.qty
                )
                mtm += unrealized - pos.entry_fee
            curve.append((ts, mtm))

        for symbol, pos in list(positions.items()):
            df = data[symbol]
            last_ts = _utc(df.index[-1])
            last_close = float(df.iloc[-1]["close"])
            trade = self._close_position(pos, last_ts, last_close, "end_of_data")
            equity += trade.net_pnl
            trades.append(trade)

        curve.append((timeline[-1], equity))
        curve_series = pd.Series(
            [value for _, value in curve],
            index=pd.DatetimeIndex([ts for ts, _ in curve]),
            dtype=float,
        )
        curve_series = curve_series[~curve_series.index.duplicated(keep="last")].sort_index()

        return BacktestResult(
            initial_equity=self.initial_equity,
            final_equity=equity,
            equity_curve=curve_series,
            trades=trades,
            rejected_signals=rejected,
            skipped_gap_bars=skipped_gaps,
            gap_bars_seen=gap_bars_seen,
        )

    def _close_position(self, pos, timestamp, reference_price, reason):
        exit_side = "sell" if pos.side == "buy" else "buy"
        exit_price = self.cost_model.execution_price(reference_price, exit_side)
        gross = (
            (exit_price - pos.entry_price) * pos.qty
            if pos.side == "buy"
            else (pos.entry_price - exit_price) * pos.qty
        )
        exit_fee = self.cost_model.trading_cost(pos.qty * exit_price)
        fees = pos.entry_fee + exit_fee
        slippage_cost = abs(exit_price - reference_price) * pos.qty
        return Trade(
            symbol=pos.symbol,
            side=pos.side,
            entry_time=pos.entry_time.isoformat(),
            exit_time=_utc(timestamp).isoformat(),
            qty=pos.qty,
            entry_price=pos.entry_price,
            exit_price=exit_price,
            gross_pnl=gross,
            fees=fees,
            slippage_cost=slippage_cost,
            net_pnl=gross - fees,
            exit_reason=reason,
            tag=pos.tag,
        )
