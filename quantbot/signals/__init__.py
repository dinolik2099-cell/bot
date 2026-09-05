"""Pure, non-executable signal contracts.

Signals are intentionally separated from portfolio, risk, and execution.
Creating a signal never places an order or changes portfolio state.
"""

from .contracts import SignalIntent, normalize_strategy_output
from .model_adapter import generate_model_intents

__all__ = ["SignalIntent", "generate_model_intents", "normalize_strategy_output"]
