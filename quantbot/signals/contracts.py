"""Causal signal normalization shared by research, paper, and future live paths."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

import math
import pandas as pd


@dataclass(frozen=True)
class SignalIntent:
    """A validated opportunity, not an order.

    ``timestamp`` is the first timestamp at which the intent may be considered.
    With the default lag of one bar, strategy row T-1 becomes an intent at T.
    """

    symbol: str
    timestamp: pd.Timestamp
    side: str
    model: str
    model_family: str
    confidence: float
    score: float
    stop: float
    take_profit: float | None
    risk_intent: str
    regime: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


def _utc_timestamp(value: Any) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    return ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")


def normalize_strategy_output(
    *,
    symbol: str,
    model: str,
    model_family: str,
    frame: pd.DataFrame,
    strategy_output: pd.DataFrame,
    execution_lag: int = 1,
    regime: str | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> tuple[SignalIntent, ...]:
    """Convert a model's causal dataframe output into non-executable intents.

    The function deliberately does not rank, size, accept, reject, or execute
    signals. Those responsibilities belong to later Portfolio and Risk layers.
    """
    if execution_lag < 1:
        raise ValueError("execution_lag must be at least one bar")
    if not symbol or not model or not model_family:
        raise ValueError("symbol, model, and model_family are required")
    if not frame.index.equals(strategy_output.index):
        raise ValueError("strategy output index must exactly match the input frame")
    required = {"signal", "stop", "target"}
    missing = required - set(strategy_output.columns)
    if missing:
        raise ValueError(f"strategy output missing columns: {sorted(missing)}")

    intents: list[SignalIntent] = []
    common_metadata = dict(metadata or {})
    for output_pos in range(0, len(strategy_output) - execution_lag):
        row = strategy_output.iloc[output_pos]
        raw_side = int(row["signal"])
        if raw_side == 0:
            continue
        if raw_side not in {-1, 1}:
            raise ValueError(f"invalid strategy signal: {raw_side}")
        stop = float(row["stop"])
        if not math.isfinite(stop):
            continue
        reference = float(frame.iloc[output_pos]["close"])
        if not math.isfinite(reference):
            continue
        side = "buy" if raw_side == 1 else "sell"
        if (side == "buy" and stop >= reference) or (side == "sell" and stop <= reference):
            continue
        target_value = row["target"]
        target = None if pd.isna(target_value) else float(target_value)
        if target is not None and (not math.isfinite(target) or (side == "buy" and target <= reference) or (side == "sell" and target >= reference)):
            continue
        distance = abs(reference - stop)
        confidence = min(1.0, distance / max(abs(reference), 1e-12))
        intents.append(SignalIntent(
            symbol=symbol,
            timestamp=_utc_timestamp(frame.index[output_pos + execution_lag]),
            side=side,
            model=model,
            model_family=model_family,
            confidence=confidence,
            score=float(raw_side) * confidence,
            stop=stop,
            take_profit=target,
            risk_intent="requires_risk_approval",
            regime=regime,
            metadata={**common_metadata, "source_row_timestamp": _utc_timestamp(frame.index[output_pos]).isoformat()},
        ))
    return tuple(intents)
