from __future__ import annotations
import numpy as np
import pandas as pd


def ema(s, n): return s.ewm(span=n, adjust=False).mean()

def atr(df, n=14):
    prev = df.close.shift(1)
    tr = pd.concat([(df.high-df.low), (df.high-prev).abs(), (df.low-prev).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1/n, adjust=False).mean()

def rolling_z(s, n):
    m = s.rolling(n).mean(); sd = s.rolling(n).std(ddof=0)
    return (s-m)/sd.replace(0, np.nan)
