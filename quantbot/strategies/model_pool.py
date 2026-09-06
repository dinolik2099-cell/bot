from __future__ import annotations

import numpy as np
import pandas as pd

from .indicators import atr, ema, rolling_z
from quantbot.research.model_registry import ModelSpec, register_model


def _base(df: pd.DataFrame) -> pd.DataFrame:
    required = {"open", "high", "low", "close"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"model frame missing columns: {sorted(missing)}")
    x = df.copy()
    x["atr"] = atr(x, 14)
    x["signal"] = 0
    x["stop"] = np.nan
    x["target"] = np.nan
    return x


def _finish(x: pd.DataFrame, long: pd.Series, short: pd.Series, stop_atr: float, reward_r: float) -> pd.DataFrame:
    long = long.fillna(False)
    short = short.fillna(False)
    x.loc[long, "signal"] = 1
    x.loc[short, "signal"] = -1
    x.loc[long, "stop"] = x.loc[long, "close"] - stop_atr * x.loc[long, "atr"]
    x.loc[short, "stop"] = x.loc[short, "close"] + stop_atr * x.loc[short, "atr"]
    x.loc[long, "target"] = x.loc[long, "close"] + reward_r * (x.loc[long, "close"] - x.loc[long, "stop"])
    x.loc[short, "target"] = x.loc[short, "close"] - reward_r * (x.loc[short, "stop"] - x.loc[short, "close"])
    return x


def ema_trend(df, fast=20, slow=80, stop_atr=2.0, reward_r=3.0):
    x = _base(df); f, s = ema(x.close, fast), ema(x.close, slow)
    return _finish(x, f > s, f < s, stop_atr, reward_r)


def ema_cross(df, fast=10, slow=50, stop_atr=2.0, reward_r=3.0):
    x = _base(df); f, s = ema(x.close, fast), ema(x.close, slow)
    long = (f > s) & (f.shift(1) <= s.shift(1)); short = (f < s) & (f.shift(1) >= s.shift(1))
    return _finish(x, long, short, stop_atr, reward_r)


def price_ema_momentum(df, ema_period=50, momentum=10, threshold=0.0, stop_atr=2.0, reward_r=3.0):
    x = _base(df)
    e = ema(x.close, ema_period)
    mom = x.close.pct_change(momentum)
    return _finish(
        x,
        (x.close > e) & (mom > threshold),
        (x.close < e) & (mom < -threshold),
        stop_atr,
        reward_r,
    )


def roc_momentum(df, period=20, threshold=0.01, stop_atr=2.0, reward_r=3.0):
    x = _base(df); roc = x.close.pct_change(period)
    return _finish(x, roc > threshold, roc < -threshold, stop_atr, reward_r)


def multi_period_momentum(df, short=10, long=40, stop_atr=2.0, reward_r=3.0):
    x = _base(df); a = x.close.pct_change(short); b = x.close.pct_change(long)
    return _finish(x, (a > 0) & (b > 0) & (a > b), (a < 0) & (b < 0) & (a < b), stop_atr, reward_r)


def donchian_breakout(df, lookback=20, stop_atr=2.0, reward_r=3.0):
    x = _base(df); hh = x.high.shift(1).rolling(lookback).max(); ll = x.low.shift(1).rolling(lookback).min()
    return _finish(x, x.close > hh, x.close < ll, stop_atr, reward_r)


def donchian_retest(df, lookback=20, retest_bars=3, stop_atr=2.0, reward_r=3.0):
    x = _base(df); hh = x.high.shift(1).rolling(lookback).max(); ll = x.low.shift(1).rolling(lookback).min()
    prior_long = x.close.shift(1) > hh.shift(1); prior_short = x.close.shift(1) < ll.shift(1)
    long = prior_long.rolling(retest_bars).max().fillna(0).astype(bool) & (x.low <= hh) & (x.close > hh)
    short = prior_short.rolling(retest_bars).max().fillna(0).astype(bool) & (x.high >= ll) & (x.close < ll)
    return _finish(x, long, short, stop_atr, reward_r)


def atr_expansion(df, atr_window=50, expansion=1.15, stop_atr=2.0, reward_r=3.0):
    x = _base(df); baseline = x.atr.rolling(atr_window).mean(); up = x.close > x.high.shift(1); dn = x.close < x.low.shift(1)
    return _finish(x, (x.atr > baseline * expansion) & up, (x.atr > baseline * expansion) & dn, stop_atr, reward_r)


def atr_compression_breakout(df, atr_window=50, compression=0.75, stop_atr=2.0, reward_r=3.0):
    x = _base(df); base = x.atr.rolling(atr_window).mean(); compressed = x.atr.shift(1) < base.shift(1) * compression
    return _finish(x, compressed & (x.close > x.high.shift(1)), compressed & (x.close < x.low.shift(1)), stop_atr, reward_r)


def bollinger_breakout(df, period=20, width=2.0, stop_atr=2.0, reward_r=3.0):
    x = _base(df); m = x.close.rolling(period).mean(); sd = x.close.rolling(period).std(ddof=0)
    up, dn = m + width * sd, m - width * sd
    return _finish(x, x.close > up.shift(1), x.close < dn.shift(1), stop_atr, reward_r)


def bollinger_reversion(df, period=20, width=2.0, stop_atr=2.0, reward_r=1.5):
    x = _base(df); m = x.close.rolling(period).mean(); sd = x.close.rolling(period).std(ddof=0)
    return _finish(x, x.close < m - width * sd, x.close > m + width * sd, stop_atr, reward_r)


def rsi_momentum(df, period=14, threshold=55.0, stop_atr=2.0, reward_r=3.0):
    x = _base(df); d = x.close.diff(); gain = d.clip(lower=0).ewm(alpha=1/period, adjust=False).mean(); loss = (-d.clip(upper=0)).ewm(alpha=1/period, adjust=False).mean(); rsi = 100 - 100 / (1 + gain / loss.replace(0, np.nan))
    return _finish(x, rsi > threshold, rsi < 100-threshold, stop_atr, reward_r)


def rsi_reversal(df, period=14, low=30.0, high=70.0, stop_atr=2.0, reward_r=1.5):
    x = _base(df); d = x.close.diff(); gain = d.clip(lower=0).ewm(alpha=1/period, adjust=False).mean(); loss = (-d.clip(upper=0)).ewm(alpha=1/period, adjust=False).mean(); rsi = 100 - 100 / (1 + gain / loss.replace(0, np.nan))
    return _finish(x, rsi < low, rsi > high, stop_atr, reward_r)


def zscore_reversion(df, lookback=40, entry=2.0, stop_atr=2.0, reward_r=1.5):
    x = _base(df); z = rolling_z(x.close, lookback)
    return _finish(x, z < -entry, z > entry, stop_atr, reward_r)


def short_term_reversal(df, period=3, threshold=0.015, stop_atr=2.0, reward_r=1.5):
    x = _base(df); r = x.close.pct_change(period)
    return _finish(x, r < -threshold, r > threshold, stop_atr, reward_r)


def extreme_reversal(df, period=20, threshold=2.5, stop_atr=2.0, reward_r=1.5):
    x = _base(df); z = rolling_z(x.close.pct_change(), period)
    return _finish(x, z < -threshold, z > threshold, stop_atr, reward_r)


def range_reversal(df, period=30, band=0.15, stop_atr=2.0, reward_r=1.5):
    x = _base(df); hi = x.high.rolling(period).max(); lo = x.low.rolling(period).min(); width = (hi-lo).replace(0, np.nan)
    pos = (x.close-lo)/width
    return _finish(x, pos < band, pos > 1-band, stop_atr, reward_r)


def ema_pullback(df, fast=20, slow=80, stop_atr=2.0, reward_r=2.0):
    x = _base(df); f, s = ema(x.close, fast), ema(x.close, slow)
    return _finish(x, (f>s)&(x.low<=f)&(x.close>f)&(x.close>x.open), (f<s)&(x.high>=f)&(x.close<f)&(x.close<x.open), stop_atr, reward_r)


def ema_slope(df, period=50, slope_bars=5, stop_atr=2.0, reward_r=3.0):
    x = _base(df); e = ema(x.close, period); slope = e.pct_change(slope_bars)
    return _finish(x, slope > 0, slope < 0, stop_atr, reward_r)


def trend_strength(df, fast=20, slow=80, min_spread=0.01, stop_atr=2.0, reward_r=3.0):
    x = _base(df); f, s = ema(x.close, fast), ema(x.close, slow); spread=(f/s-1).abs()
    return _finish(x, (f>s)&(spread>min_spread), (f<s)&(spread>min_spread), stop_atr, reward_r)


def higher_high_lower_low(df, lookback=5, stop_atr=2.0, reward_r=3.0):
    x = _base(df); ph=x.high.rolling(lookback).max(); pl=x.low.rolling(lookback).min()
    return _finish(x, (x.high>ph.shift(1))&(x.low>x.low.shift(lookback)), (x.low<pl.shift(1))&(x.high<x.high.shift(lookback)), stop_atr, reward_r)


def candle_engulfing(df, stop_atr=2.0, reward_r=2.0):
    x = _base(df); prev_o=x.open.shift(1); prev_c=x.close.shift(1)
    bull=(x.close>x.open)&(prev_c<prev_o)&(x.close>=prev_o)&(x.open<=prev_c)
    bear=(x.close<x.open)&(prev_c>prev_o)&(x.open>=prev_c)&(x.close<=prev_o)
    return _finish(x, bull, bear, stop_atr, reward_r)


def pinbar(df, wick_ratio=2.0, stop_atr=2.0, reward_r=2.0):
    x = _base(df); body=(x.close-x.open).abs(); upper=x.high-x[["open","close"]].max(axis=1); lower=x[["open","close"]].min(axis=1)-x.low
    bull=(lower>body*wick_ratio)&(x.close>x.open); bear=(upper>body*wick_ratio)&(x.close<x.open)
    return _finish(x, bull, bear, stop_atr, reward_r)


def three_bar_momentum(df, threshold=0.005, stop_atr=2.0, reward_r=2.0):
    x = _base(df); r=x.close.pct_change(); up=(r>threshold)&(r.shift(1)>threshold)&(r.shift(2)>threshold); dn=(r<-threshold)&(r.shift(1)<-threshold)&(r.shift(2)<-threshold)
    return _finish(x, up, dn, stop_atr, reward_r)


def inside_bar_breakout(df, stop_atr=2.0, reward_r=3.0):
    x = _base(df); inside=(x.high<x.high.shift(1))&(x.low>x.low.shift(1));
    return _finish(x, inside.shift(1)&(x.close>x.high.shift(1)), inside.shift(1)&(x.close<x.low.shift(1)), stop_atr, reward_r)


def volume_breakout(df, volume_window=30, volume_mult=1.5, stop_atr=2.0, reward_r=3.0):
    x = _base(df)
    if "volume" not in x.columns: raise ValueError("model requires volume")
    vm=x.volume.rolling(volume_window).mean()
    return _finish(x, (x.volume>vm*volume_mult)&(x.close>x.high.shift(1)), (x.volume>vm*volume_mult)&(x.close<x.low.shift(1)), stop_atr, reward_r)


def volume_trend(df, volume_window=30, volume_mult=1.1, ema_period=50, stop_atr=2.0, reward_r=3.0):
    x = _base(df)
    if "volume" not in x.columns: raise ValueError("model requires volume")
    vm=x.volume.rolling(volume_window).mean(); e=ema(x.close, ema_period)
    return _finish(x, (x.close>e)&(x.volume>vm*volume_mult), (x.close<e)&(x.volume>vm*volume_mult), stop_atr, reward_r)


def volatility_regime_trend(df, atr_window=100, min_ratio=1.1, ema_period=50, stop_atr=2.0, reward_r=3.0):
    x = _base(df); base=x.atr.rolling(atr_window).mean(); e=ema(x.close, ema_period); highvol=x.atr>base*min_ratio
    return _finish(x, highvol&(x.close>e), highvol&(x.close<e), stop_atr, reward_r)


def low_volatility_breakout(df, atr_window=50, compression=0.8, lookback=20, stop_atr=2.0, reward_r=3.0):
    x = _base(df); base=x.atr.rolling(atr_window).mean(); compressed=x.atr.shift(1)<base.shift(1)*compression; hh=x.high.shift(1).rolling(lookback).max(); ll=x.low.shift(1).rolling(lookback).min()
    return _finish(x, compressed&(x.close>hh), compressed&(x.close<ll), stop_atr, reward_r)


def macd_momentum(df, fast=12, slow=26, signal_period=9, stop_atr=2.0, reward_r=3.0):
    x = _base(df); m=ema(x.close,fast)-ema(x.close,slow); s=ema(m,signal_period)
    return _finish(x, (m>s)&(m.shift(1)<=s.shift(1)), (m<s)&(m.shift(1)>=s.shift(1)), stop_atr, reward_r)


def macd_trend(df, fast=12, slow=26, signal_period=9, stop_atr=2.0, reward_r=3.0):
    x = _base(df); m=ema(x.close,fast)-ema(x.close,slow); s=ema(m,signal_period)
    return _finish(x, (m>s)&(m>0), (m<s)&(m<0), stop_atr, reward_r)


def bollinger_squeeze_breakout(df, period=20, width=2.0, squeeze_window=50, squeeze_ratio=0.8, stop_atr=2.0, reward_r=3.0):
    x = _base(df); m=x.close.rolling(period).mean(); sd=x.close.rolling(period).std(ddof=0); bw=(2*width*sd/m.abs()).replace(0,np.nan); base=bw.rolling(squeeze_window).mean(); sq=bw.shift(1)<base.shift(1)*squeeze_ratio
    return _finish(x, sq&(x.close>m+width*sd), sq&(x.close<m-width*sd), stop_atr, reward_r)


# 32 model-pool candidates + 4 existing candidates = 36 registered candidates.
_SPECS = [
    ("ema_trend", "趋势", ema_trend, {"fast":(10,20),"slow":(50,80),"stop_atr":(1.5,2.0,2.5),"reward_r":(2.0,3.0,4.0)}),
    ("ema_cross", "趋势/交叉", ema_cross, {"fast":(10,20),"slow":(50,80,120),"stop_atr":(1.5,2.0,2.5),"reward_r":(2.0,3.0)}),
    ("price_ema_momentum", "趋势/动量", price_ema_momentum, {"ema_period":(20,50,80),"momentum":(5,10,20),"threshold":(0.0,0.01),"stop_atr":(1.5,2.0,2.5),"reward_r":(2.0,3.0)}),
    ("roc_momentum", "动量", roc_momentum, {"period":(10,20,40),"threshold":(0.005,0.01,0.02),"stop_atr":(1.5,2.0,2.5),"reward_r":(2.0,3.0,4.0)}),
    ("multi_period_momentum", "动量", multi_period_momentum, {"short":(5,10),"long":(30,40,60),"stop_atr":(1.5,2.0,2.5),"reward_r":(2.0,3.0)}),
    ("donchian_breakout", "突破", donchian_breakout, {"lookback":(10,20,40,60),"stop_atr":(1.5,2.0,2.5),"reward_r":(2.0,3.0,4.0)}),
    ("donchian_retest", "突破/回踩", donchian_retest, {"lookback":(20,40),"retest_bars":(2,3,5),"stop_atr":(1.5,2.0,2.5),"reward_r":(2.0,3.0)}),
    ("atr_expansion", "波动率", atr_expansion, {"atr_window":(30,50,100),"expansion":(1.1,1.15,1.25),"stop_atr":(1.5,2.0,2.5),"reward_r":(2.0,3.0)}),
    ("atr_compression_breakout", "波动率/突破", atr_compression_breakout, {"atr_window":(30,50,100),"compression":(0.7,0.8,0.9),"stop_atr":(1.5,2.0,2.5),"reward_r":(2.0,3.0)}),
    ("bollinger_breakout", "突破", bollinger_breakout, {"period":(20,40),"width":(1.5,2.0,2.5),"stop_atr":(1.5,2.0,2.5),"reward_r":(2.0,3.0)}),
    ("bollinger_reversion", "反转", bollinger_reversion, {"period":(20,40),"width":(1.5,2.0,2.5),"stop_atr":(1.5,2.0,2.5),"reward_r":(1.0,1.5,2.0)}),
    ("rsi_momentum", "动量", rsi_momentum, {"period":(7,14,21),"threshold":(52,55,60),"stop_atr":(1.5,2.0,2.5),"reward_r":(2.0,3.0)}),
    ("rsi_reversal", "反转", rsi_reversal, {"period":(7,14,21),"low":(25,30,35),"high":(65,70,75),"stop_atr":(1.5,2.0,2.5),"reward_r":(1.0,1.5,2.0)}),
    ("zscore_reversion", "反转/均值回归", zscore_reversion, {"lookback":(20,40,60),"entry":(1.5,2.0,2.5,3.0),"stop_atr":(1.5,2.0,2.5),"reward_r":(1.0,1.5,2.0)}),
    ("short_term_reversal", "反转", short_term_reversal, {"period":(2,3,5),"threshold":(0.01,0.015,0.02),"stop_atr":(1.5,2.0,2.5),"reward_r":(1.0,1.5,2.0)}),
    ("extreme_reversal", "反转", extreme_reversal, {"period":(10,20,40),"threshold":(2.0,2.5,3.0),"stop_atr":(1.5,2.0,2.5),"reward_r":(1.0,1.5,2.0)}),
    ("range_reversal", "震荡/反转", range_reversal, {"period":(20,30,50),"band":(0.1,0.15,0.2),"stop_atr":(1.5,2.0,2.5),"reward_r":(1.0,1.5,2.0)}),
    ("ema_pullback", "趋势/回调", ema_pullback, {"fast":(10,20),"slow":(50,80,120),"stop_atr":(1.5,2.0,2.5),"reward_r":(2.0,3.0)}),
    ("ema_slope", "趋势", ema_slope, {"period":(20,50,80),"slope_bars":(3,5,10),"stop_atr":(1.5,2.0,2.5),"reward_r":(2.0,3.0)}),
    ("trend_strength", "趋势", trend_strength, {"fast":(10,20),"slow":(50,80),"min_spread":(0.005,0.01,0.02),"stop_atr":(1.5,2.0,2.5),"reward_r":(2.0,3.0)}),
    ("higher_high_lower_low", "价格结构", higher_high_lower_low, {"lookback":(3,5,10),"stop_atr":(1.5,2.0,2.5),"reward_r":(2.0,3.0)}),
    ("candle_engulfing", "K线形态", candle_engulfing, {"stop_atr":(1.5,2.0,2.5),"reward_r":(1.5,2.0,3.0)}),
    ("pinbar", "K线形态", pinbar, {"wick_ratio":(1.5,2.0,3.0),"stop_atr":(1.5,2.0,2.5),"reward_r":(1.5,2.0,3.0)}),
    ("three_bar_momentum", "K线/动量", three_bar_momentum, {"threshold":(0.003,0.005,0.01),"stop_atr":(1.5,2.0,2.5),"reward_r":(1.5,2.0,3.0)}),
    ("inside_bar_breakout", "K线/突破", inside_bar_breakout, {"stop_atr":(1.5,2.0,2.5),"reward_r":(2.0,3.0,4.0)}),
    ("volume_breakout", "成交量/突破", volume_breakout, {"volume_window":(20,30,50),"volume_mult":(1.2,1.5,2.0),"stop_atr":(1.5,2.0,2.5),"reward_r":(2.0,3.0)}),
    ("volume_trend", "成交量/趋势", volume_trend, {"volume_window":(20,30,50),"volume_mult":(1.05,1.1,1.25),"ema_period":(20,50,80),"stop_atr":(1.5,2.0,2.5),"reward_r":(2.0,3.0)}),
    ("volatility_regime_trend", "波动率/趋势", volatility_regime_trend, {"atr_window":(50,100),"min_ratio":(1.05,1.1,1.2),"ema_period":(20,50,80),"stop_atr":(1.5,2.0,2.5),"reward_r":(2.0,3.0)}),
    ("low_volatility_breakout", "波动率/突破", low_volatility_breakout, {"atr_window":(30,50,100),"compression":(0.7,0.8,0.9),"lookback":(10,20,40),"stop_atr":(1.5,2.0,2.5),"reward_r":(2.0,3.0)}),
    ("macd_momentum", "动量/MACD", macd_momentum, {"fast":(8,12),"slow":(21,26),"signal_period":(7,9),"stop_atr":(1.5,2.0,2.5),"reward_r":(2.0,3.0)}),
    ("macd_trend", "趋势/MACD", macd_trend, {"fast":(8,12),"slow":(21,26),"signal_period":(7,9),"stop_atr":(1.5,2.0,2.5),"reward_r":(2.0,3.0)}),
    ("bollinger_squeeze_breakout", "波动率/突破", bollinger_squeeze_breakout, {"period":(20,40),"width":(1.5,2.0),"squeeze_window":(30,50),"squeeze_ratio":(0.7,0.8,0.9),"stop_atr":(1.5,2.0,2.5),"reward_r":(2.0,3.0)}),
]


def register_model_pool() -> None:
    common = ("open", "high", "low", "close", "volume")
    for name, category, fn, grid in _SPECS:
        family = category.split("/", 1)[0]
        register_model(ModelSpec(
            name, category, "经典量化/技术分析候选",
            "第一批基础候选；必须重新经过统一 TRAIN→VALIDATION→OOS。",
            common, grid, ("多种市场环境",),
            family=family,
            description=f"{family} 家族的 {name} 候选模型；仅提供因果 signal/stop/target 输出。",
            future_data_risk="none_declared",
            train_status="not_run",
            validation_status="not_run",
            oos_status="sealed",
            cost_sensitivity="unassessed",
            research_version="model-pool-v1",
            model_id=f"quantbot.{name}.v1",
            causal_timing="t_minus_1_to_t_intent",
            long_short_capable=True,
            warmup_bars=None,
        ), fn)
