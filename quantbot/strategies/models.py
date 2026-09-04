from __future__ import annotations
import numpy as np
import pandas as pd
from .indicators import ema, atr, rolling_z


def _base(df):
    x = df.copy()
    x["atr"] = atr(x, 14)
    x["signal"] = 0
    x["stop"] = np.nan
    x["target"] = np.nan
    return x


def trend_breakout(df, lookback=40, stop_atr=2.0, reward_r=3.0):
    x = _base(df)
    hh = x.high.shift(1).rolling(lookback).max()
    ll = x.low.shift(1).rolling(lookback).min()
    e20 = ema(x.close, 20); e80 = ema(x.close, 80)
    long = (e20 > e80) & (x.close > hh)
    short = (e20 < e80) & (x.close < ll)
    x.loc[long, "signal"] = 1
    x.loc[short, "signal"] = -1
    x.loc[long, "stop"] = x.close[long] - stop_atr*x.atr[long]
    x.loc[short, "stop"] = x.close[short] + stop_atr*x.atr[short]
    x.loc[long, "target"] = x.close[long] + reward_r*(x.close[long]-x.stop[long])
    x.loc[short, "target"] = x.close[short] - reward_r*(x.stop[short]-x.close[short])
    return x


def trend_pullback(df, ema_fast=20, ema_slow=80, stop_atr=2.0, reward_r=3.0):
    x = _base(df)
    f, s = ema(x.close, ema_fast), ema(x.close, ema_slow)
    long_trend = f > s
    short_trend = f < s
    pull_long = (x.low <= f) & (x.close > f) & (x.close > x.open)
    pull_short = (x.high >= f) & (x.close < f) & (x.close < x.open)
    long = long_trend & pull_long
    short = short_trend & pull_short
    x.loc[long, "signal"] = 1
    x.loc[short, "signal"] = -1
    x.loc[long, "stop"] = x.close[long] - stop_atr*x.atr[long]
    x.loc[short, "stop"] = x.close[short] + stop_atr*x.atr[short]
    x.loc[long, "target"] = x.close[long] + reward_r*(x.close[long]-x.stop[long])
    x.loc[short, "target"] = x.close[short] - reward_r*(x.stop[short]-x.close[short])
    return x


def volatility_breakout(df, range_lookback=20, stop_atr=2.0, reward_r=3.0):
    x = _base(df)
    hh = x.high.shift(1).rolling(range_lookback).max()
    ll = x.low.shift(1).rolling(range_lookback).min()
    atr_ma = x.atr.rolling(50).mean()
    expansion = x.atr > atr_ma * 1.15
    long = expansion & (x.close > hh)
    short = expansion & (x.close < ll)
    x.loc[long, "signal"] = 1
    x.loc[short, "signal"] = -1
    x.loc[long, "stop"] = x.close[long] - stop_atr*x.atr[long]
    x.loc[short, "stop"] = x.close[short] + stop_atr*x.atr[short]
    x.loc[long, "target"] = x.close[long] + reward_r*(x.close[long]-x.stop[long])
    x.loc[short, "target"] = x.close[short] - reward_r*(x.stop[short]-x.close[short])
    return x


def mean_reversion(df, lookback=40, z_entry=2.5, z_exit=0.75, stop_atr=2.0):
    x = _base(df)
    z = rolling_z(x.close, lookback)
    long = z < -z_entry
    short = z > z_entry
    x.loc[long, "signal"] = 1
    x.loc[short, "signal"] = -1
    x.loc[long, "stop"] = x.close[long] - stop_atr*x.atr[long]
    x.loc[short, "stop"] = x.close[short] + stop_atr*x.atr[short]
    # target is mean proxy; exit engine also supports explicit target.
    mean = x.close.rolling(lookback).mean()
    x.loc[long, "target"] = mean[long]
    x.loc[short, "target"] = mean[short]
    return x
