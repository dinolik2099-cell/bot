"""Point-in-time deterministic regime composition without future leakage."""
from __future__ import annotations
from dataclasses import dataclass
import pandas as pd
from .regimes import RegimeConfig, classify_regimes

@dataclass(frozen=True)
class RegimePolicy:
    liquidity_window: int = 20
    drawdown_stress: float = 0.08

def classify_point_in_time(frame: pd.DataFrame, policy: RegimePolicy = RegimePolicy()) -> pd.DataFrame:
    required = {"high", "low", "close", "volume"}
    if not isinstance(frame.index, pd.DatetimeIndex) or not frame.index.is_monotonic_increasing or not required.issubset(frame.columns): raise ValueError("regime_frame_invalid")
    base = classify_regimes(frame, RegimeConfig())
    volume = frame["volume"].astype(float); liquidity = volume.rolling(policy.liquidity_window, min_periods=policy.liquidity_window).median()
    liquidity_state = pd.Series("unknown", index=frame.index, dtype="object"); liquidity_state.loc[liquidity.notna() & (volume >= liquidity)] = "normal"; liquidity_state.loc[liquidity.notna() & (volume < liquidity)] = "thin"
    peak = frame["close"].astype(float).cummax(); drawdown = 1 - frame["close"].astype(float) / peak
    stress = pd.Series("normal", index=frame.index, dtype="object"); stress.loc[drawdown >= policy.drawdown_stress] = "drawdown_stress"
    out = base.copy(); out["liquidity"] = liquidity_state; out["stress"] = stress; out["composite"] = out["regime"].astype(str) + "|" + liquidity_state + "|" + stress
    return out
