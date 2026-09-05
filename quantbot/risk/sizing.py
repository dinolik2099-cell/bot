"""Turn approved risk decisions into explicit, non-executable position plans."""
from __future__ import annotations

from dataclasses import dataclass
import math

from quantbot.backtest import CostModel
from quantbot.portfolio import PortfolioCandidate
from .policy import RiskDecision


@dataclass(frozen=True)
class PositionPlan:
    symbol: str
    side: str
    model: str
    model_family: str
    decision_timestamp: str
    reference_price: float
    expected_execution_price: float
    quantity: float
    notional: float
    risk_amount: float
    estimated_entry_fee: float
    stop: float
    take_profit: float | None
    tag: str


def size_approved_candidate(candidate: PortfolioCandidate, decision: RiskDecision, *, reference_price: float, cost_model: CostModel) -> PositionPlan:
    """Create a plan only after Risk approval; never send an order."""
    if not decision.accepted:
        raise ValueError(f"cannot size rejected candidate: {decision.reason}")
    if decision.quantity <= 0 or decision.notional <= 0 or not math.isfinite(reference_price):
        raise ValueError("approved decision has invalid sizing")
    intent = candidate.intent
    expected = cost_model.execution_price(reference_price, intent.side)
    notional = decision.quantity * expected
    return PositionPlan(
        symbol=intent.symbol, side=intent.side, model=intent.model, model_family=intent.model_family,
        decision_timestamp=intent.timestamp.isoformat(), reference_price=float(reference_price),
        expected_execution_price=expected, quantity=decision.quantity, notional=notional,
        risk_amount=decision.risk_amount, estimated_entry_fee=cost_model.trading_cost(notional),
        stop=intent.stop, take_profit=intent.take_profit,
        tag=f"{intent.model}:{intent.symbol}:{intent.timestamp.isoformat()}",
    )
