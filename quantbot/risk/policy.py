"""Highest-priority, non-executable risk approval contracts."""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable

from quantbot.portfolio import PortfolioCandidate


@dataclass(frozen=True)
class RiskPolicy:
    risk_per_entry: float = 0.01
    max_total_risk: float = 0.04
    max_same_direction_risk: float = 0.03
    max_positions: int = 4
    max_position_fraction: float = 0.25
    max_total_capital_fraction: float = 0.80


@dataclass(frozen=True)
class PositionExposure:
    symbol: str
    side: str
    risk_amount: float
    notional: float


@dataclass(frozen=True)
class RiskDecision:
    accepted: bool
    reason: str
    quantity: float = 0.0
    risk_amount: float = 0.0
    notional: float = 0.0


def approve_candidate(candidate: PortfolioCandidate, *, reference_price: float, equity: float, positions: Iterable[PositionExposure], policy: RiskPolicy = RiskPolicy()) -> RiskDecision:
    """Approve or reject one proposal without creating an order or position."""
    if not math.isfinite(reference_price) or reference_price <= 0 or not math.isfinite(equity) or equity <= 0:
        return RiskDecision(False, "invalid_price_or_equity")
    open_positions = tuple(positions)
    intent = candidate.intent
    if len(open_positions) >= policy.max_positions:
        return RiskDecision(False, "max_positions")
    if any(position.symbol == intent.symbol for position in open_positions):
        return RiskDecision(False, "symbol_already_exposed")
    risk_per_unit = abs(reference_price - intent.stop)
    if not math.isfinite(risk_per_unit) or risk_per_unit <= 0:
        return RiskDecision(False, "invalid_stop_distance")
    proposed_risk = equity * policy.risk_per_entry
    used_risk = sum(position.risk_amount for position in open_positions)
    direction_risk = sum(position.risk_amount for position in open_positions if position.side == intent.side)
    if used_risk + proposed_risk > equity * policy.max_total_risk + 1e-12:
        return RiskDecision(False, "max_total_risk")
    if direction_risk + proposed_risk > equity * policy.max_same_direction_risk + 1e-12:
        return RiskDecision(False, "max_same_direction_risk")
    quantity = min(proposed_risk / risk_per_unit, equity * policy.max_position_fraction / reference_price)
    notional = quantity * reference_price
    used_notional = sum(position.notional for position in open_positions)
    if used_notional + notional > equity * policy.max_total_capital_fraction + 1e-12:
        return RiskDecision(False, "max_total_capital")
    return RiskDecision(True, "approved", quantity=quantity, risk_amount=risk_per_unit * quantity, notional=notional)
