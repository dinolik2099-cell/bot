"""Retired legacy backtest entry point.

QuantBot's only supported backtest implementation is
``quantbot.backtest.engine_v2.BacktestEngine``. This module deliberately does
not retain the former independent PnL/fee/position implementation: using it
would create an un-audited second execution path.
"""

from __future__ import annotations


_MESSAGE = (
    "quantbot.backtest.engine is retired. Use "
    "quantbot.backtest.engine_v2.BacktestEngine together with "
    "quantbot.research.evaluation.make_strategy_adapter."
)


def backtest(*_args, **_kwargs):
    """Reject the retired single-frame backtest API."""
    raise RuntimeError(_MESSAGE)


def metrics(*_args, **_kwargs):
    """Reject metrics derived from the retired execution path."""
    raise RuntimeError(_MESSAGE)
