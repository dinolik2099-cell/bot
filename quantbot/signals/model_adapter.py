"""Registry-to-Signal adapter; models remain unable to execute orders."""
from __future__ import annotations
from typing import Any, Mapping
import pandas as pd
from quantbot.research.model_registry import get_model
from .contracts import SignalIntent, normalize_strategy_output

def generate_model_intents(symbol: str, model_name: str, frame: pd.DataFrame, params: Mapping[str, Any], *, execution_lag: int = 1, regime: str | None = None, metadata: Mapping[str, Any] | None = None) -> tuple[SignalIntent, ...]:
    registered=get_model(model_name)
    if registered.spec.status in {"retired", "deferred"}:
        raise PermissionError(f"model is not eligible to emit signals: {model_name}")
    if registered.spec.oos_status != "sealed":
        raise PermissionError(f"model has invalid OOS lifecycle state: {model_name}")
    output=registered.strategy(frame.copy(), **dict(params))
    return normalize_strategy_output(
        symbol=symbol, model=model_name, model_family=registered.spec.family,
        frame=frame, strategy_output=output, execution_lag=execution_lag,
        regime=regime, metadata=metadata,
    )
