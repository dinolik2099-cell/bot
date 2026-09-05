"""Strictly causal market-regime labels for downstream research metadata."""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class RegimeConfig:
    fast_span: int = 20
    slow_span: int = 80
    volatility_window: int = 20
    high_volatility_multiple: float = 1.25


def classify_regimes(frame: pd.DataFrame, config: RegimeConfig = RegimeConfig()) -> pd.DataFrame:
    """Return metadata labels using data available no later than each bar."""
    required = {"high", "low", "close"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"regime frame missing columns: {sorted(missing)}")
    if config.fast_span < 1 or config.slow_span <= config.fast_span or config.volatility_window < 2:
        raise ValueError("invalid causal regime configuration")
    close = frame["close"].astype(float)
    fast = close.ewm(span=config.fast_span, adjust=False).mean()
    slow = close.ewm(span=config.slow_span, adjust=False).mean()
    trend_strength = (fast / slow - 1.0).abs()
    volatility = close.pct_change().rolling(config.volatility_window, min_periods=config.volatility_window).std(ddof=0)
    volatility_baseline = volatility.expanding(min_periods=config.volatility_window).median()
    high_volatility = volatility > volatility_baseline * config.high_volatility_multiple
    label = pd.Series("unclassified", index=frame.index, dtype="object")
    ready = volatility.notna() & slow.notna()
    label.loc[ready & high_volatility & (fast > slow)] = "high_volatility_uptrend"
    label.loc[ready & high_volatility & (fast < slow)] = "high_volatility_downtrend"
    label.loc[ready & ~high_volatility & (fast > slow)] = "low_volatility_uptrend"
    label.loc[ready & ~high_volatility & (fast < slow)] = "low_volatility_downtrend"
    return pd.DataFrame({"regime": label, "trend_strength": trend_strength, "realized_volatility": volatility}, index=frame.index)
