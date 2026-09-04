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
        }


StrategyFn = Callable[[pd.DataFrame, int], Signal | None]


def _utc(ts) -> pd.Timestamp:
    t = pd.Timestamp(ts)
    return t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")


class BacktestEngine:
    """
    V1.0.1 conservative single-position event loop.

    Execution contract:
      1. At execution timestamp T the strategy receives df.iloc[:i].
      2. A new entry, if accepted, executes at the current candle OPEN.
      3. Existing positions are checked for stop/target before new entries.
      4. If stop and target are both touched in one candle, STOP wins.
      5. A signal timestamp must equal T.
      6. Missing/gap timestamps supplied to the engine are non-tradable.
      7. Open positions are force-closed at the final available close.
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
            s: {_utc(x) for x in values} for s, values in (gap_indices or {}).items()
        }

    def run(self, data: dict[str, pd.DataFrame], strategies: dict[str, StrategyFn]) -> BacktestResult:
        if not data or set(data) != set(strategies):
            raise ValueError("data and strategies must contain the same non-empty symbols")

        for symbol, df in data.items():
            if not isinstance(df.index, pd.DatetimeIndex):
                raise TypeError(f"{symbol}: index must be DatetimeIndex")
            if not df.index.is_monotonic_increasing:
                raise ValueError(f"{symbol}: index must be sorted")
            required = {"open", "high", "low", "close"}
            if not required.issubset(df.columns):
                raise ValueError(f"{symbol}: missing OHLC columns")

        timeline = sorted({_utc(ts) for df in data.values() for ts in df.index})
        equity = self.initial_equity
        positions: dict[str, Position] = {}
        trades: list[Trade] = []
        curve = []
        rejected = 0
        skipped_gaps = 0

        for ts in timeline:
            current = {
                symbol: df.loc[ts]
                for symbol, df in data.items()
                if ts in df.index
            }

            # Exits first.
            for symbol, pos in list(positions.items()):
                bar = current.get(symbol)
                if bar is None:
                    continue

                stop_hit = False
                target_hit = False
                if pos.side == "buy":
                    stop_hit = float(bar["low"]) <= pos.stop_price
                    target_hit = pos.take_profit is not None and float(bar["high"]) >= pos.take_profit
                else:
                    stop_hit = float(bar["high"]) >= pos.stop_price
                    target_hit = pos.take_profit is not None and float(bar["low"]) <= pos.take_profit

                if stop_hit or target_hit:
                    reason = "stop" if stop_hit else "take_profit"
                    ref = pos.stop_price if stop_hit else pos.take_profit
                    trade = self._close_position(pos, ts, float(ref), reason)
                    equity += trade.net_pnl
                    trades.append(trade)
                    del positions[symbol]

            # Entries.
            for symbol, df in data.items():
                if symbol in positions:
                    continue
                if len(positions) >= self.max_positions:
                    break
                if ts not in df.index:
                    continue
                if ts in self.gap_indices.get(symbol, set()):
                    skipped_gaps += 1
                    continue

                i = df.index.get_loc(ts)
                if not isinstance(i, int) or i <= 0:
                    continue

                signal = strategies[symbol](df.iloc[:i].copy(), i)
                if signal is None or signal.side.lower() == "flat":
                    continue
                if _utc(signal.timestamp) != ts:
                    rejected += 1
                    continue

                side = signal.side.lower()
                if side not in {"buy", "sell"}:
                    rejected += 1
                    continue
                if signal.stop_price is None:
                    rejected += 1
                    continue

                risk_fraction = signal.risk_fraction or self.max_risk_fraction
                position_fraction = signal.position_fraction or self.max_position_fraction
                risk_fraction = min(float(risk_fraction), self.max_risk_fraction)
                position_fraction = min(float(position_fraction), self.max_position_fraction)
                if risk_fraction <= 0 or position_fraction <= 0:
                    rejected += 1
                    continue

                entry_ref = float(df.iloc[i]["open"])
                risk_per_unit = abs(entry_ref - float(signal.stop_price))
                if risk_per_unit <= 0:
                    rejected += 1
                    continue

                risk_budget = equity * risk_fraction
                qty_by_risk = risk_budget / risk_per_unit
                qty_by_notional = (equity * position_fraction) / entry_ref
                qty = min(qty_by_risk, qty_by_notional)
                if qty <= 0:
                    rejected += 1
                    continue

                exec_price = self.cost_model.execution_price(
                    entry_ref, "buy" if side == "buy" else "sell"
                )
                fee = self.cost_model.trading_cost(qty * exec_price)

                positions[symbol] = Position(
                    symbol=symbol,
                    side=side,
                    qty=qty,
                    entry_price=exec_price,
                    entry_time=ts,
                    stop_price=float(signal.stop_price),
                    take_profit=signal.take_profit,
                    tag=signal.tag,
                    entry_fee=fee,
                )

            # Conservative mark-to-market. Entry fee is not deducted twice here;
            # final PnL calculation includes both entry and exit fees.
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

        if not timeline:
            raise ValueError("No timestamps available")

        for symbol, pos in list(positions.items()):
            df = data[symbol]
            last_ts = _utc(df.index[-1])
            last_close = float(df.iloc[-1]["close"])
            trade = self._close_position(pos, last_ts, last_close, "end_of_data")
            equity += trade.net_pnl
            trades.append(trade)
            del positions[symbol]

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
        )

    def _close_position(self, pos: Position, ts: pd.Timestamp,
                        reference_price: float, reason: str) -> Trade:
        exit_side = "sell" if pos.side == "buy" else "buy"
        exit_price = self.cost_model.execution_price(reference_price, exit_side)

        gross = (
            (exit_price - pos.entry_price) * pos.qty
            if pos.side == "buy"
            else (pos.entry_price - exit_price) * pos.qty
        )
        exit_fee = self.cost_model.trading_cost(pos.qty * exit_price)
        fees = pos.entry_fee + exit_fee

        # This isolates the price impact from the ideal reference exit.
        slippage_cost = abs(exit_price - reference_price) * pos.qty
        net = gross - fees

        return Trade(
            symbol=pos.symbol,
            side=pos.side,
            entry_time=pos.entry_time.isoformat(),
            exit_time=_utc(ts).isoformat(),
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
