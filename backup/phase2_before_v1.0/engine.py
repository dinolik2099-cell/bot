from __future__ import annotations
from dataclasses import dataclass
import math
import numpy as np
import pandas as pd

@dataclass
class Trade:
    entry_time: object
    exit_time: object
    side: int
    entry: float
    exit: float
    qty: float
    pnl: float
    fee: float
    reason: str


def backtest(df: pd.DataFrame, signals: pd.DataFrame, initial=10000.0,
             risk_pct=0.005, max_position_pct=0.30, fee_rate=0.0004,
             slippage_bps=2.0, max_drawdown_stop=0.10):
    equity = initial
    peak = initial
    halted = False
    position = None
    trades = []
    curve = []
    idx = df.index
    slip = slippage_bps / 10000.0

    for i in range(1, len(df)):
        ts = idx[i]
        row = df.iloc[i]
        prev = signals.iloc[i-1]  # only completed prior bar is used

        if position is not None:
            side = position["side"]
            stop = position["stop"]
            target = position["target"]
            hit_stop = (row.low <= stop) if side == 1 else (row.high >= stop)
            hit_target = (row.high >= target) if side == 1 else (row.low <= target)
            # Conservative same-bar ambiguity: if both are hit, assume stop first.
            reason = None
            exit_px = None
            if hit_stop:
                reason = "stop"; exit_px = stop
            elif hit_target:
                reason = "target"; exit_px = target
            if reason:
                exit_px *= (1-slip) if side == 1 else (1+slip)
                gross = (exit_px-position["entry"])*position["qty"]*side
                fee = (position["entry"]*position["qty"] + exit_px*position["qty"])*fee_rate
                pnl = gross-fee
                equity += pnl
                trades.append(Trade(position["entry_time"], ts, side, position["entry"], exit_px, position["qty"], pnl, fee, reason))
                position = None

        peak = max(peak, equity)
        dd = 1 - equity/peak
        if dd >= max_drawdown_stop:
            halted = True

        if position is None and not halted and prev.signal != 0 and np.isfinite(prev.stop) and np.isfinite(prev.target):
            side = int(prev.signal)
            entry = float(row.open) * ((1+slip) if side == 1 else (1-slip))
            stop = float(prev.stop); target = float(prev.target)
            risk_per_unit = abs(entry-stop)
            if risk_per_unit > 0:
                risk_cash = equity*risk_pct
                qty = min(risk_cash/risk_per_unit, equity*max_position_pct/entry)
                if qty > 0:
                    fee = entry*qty*fee_rate
                    equity -= fee
                    position = {"side": side, "entry": entry, "stop": stop, "target": target,
                                "qty": qty, "entry_time": ts}

        curve.append((ts, equity))

    if position is not None:
        exit_px = float(df.iloc[-1].close)
        side = position["side"]
        gross = (exit_px-position["entry"])*position["qty"]*side
        fee = (position["entry"]*position["qty"] + exit_px*position["qty"])*fee_rate
        pnl = gross-fee
        equity += pnl
        trades.append(Trade(position["entry_time"], idx[-1], side, position["entry"], exit_px, position["qty"], pnl, fee, "end"))

    curve_df = pd.DataFrame(curve, columns=["time","equity"]).set_index("time")
    return curve_df, pd.DataFrame([t.__dict__ for t in trades]), halted


def metrics(curve: pd.DataFrame, trades: pd.DataFrame, initial=10000.0):
    if curve.empty:
        return {}
    eq = curve.equity
    peak = eq.cummax()
    dd = 1-eq/peak
    wins = trades.loc[trades.pnl > 0, "pnl"] if not trades.empty else pd.Series(dtype=float)
    losses = trades.loc[trades.pnl < 0, "pnl"] if not trades.empty else pd.Series(dtype=float)
    gp = wins.sum(); gl = -losses.sum()
    pf = gp/gl if gl > 0 else float("inf") if gp > 0 else 0.0
    max_con = 0; cur = 0
    for p in trades.pnl if not trades.empty else []:
        if p < 0: cur += 1; max_con = max(max_con, cur)
        else: cur = 0
    return {
        "initial": initial,
        "final_equity": float(eq.iloc[-1]),
        "total_return": float(eq.iloc[-1]/initial-1),
        "max_drawdown": float(dd.max()),
        "profit_factor": float(pf),
        "win_rate": float((trades.pnl > 0).mean()) if len(trades) else 0.0,
        "avg_trade": float(trades.pnl.mean()) if len(trades) else 0.0,
        "trades": int(len(trades)),
        "max_consecutive_losses": int(max_con),
    }
