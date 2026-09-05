"""Pure, non-executable signal contracts.

Signals are intentionally separated from portfolio, risk, and execution.
Creating a signal never places an order or changes portfolio state.
"""

from .contracts import SignalIntent, normalize_strategy_output

__all__ = ["SignalIntent", "normalize_strategy_output"]
