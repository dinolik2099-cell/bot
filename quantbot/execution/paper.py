"""Paper-only order request contract. No exchange client is present in this module."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib

from quantbot.risk import PositionPlan


@dataclass(frozen=True)
class PaperOrderRequest:
    client_order_id: str
    symbol: str
    side: str
    quantity: float
    expected_execution_price: float
    stop: float
    take_profit: float | None
    source_tag: str
    model_family: str
    mode: str = "paper_only"


def build_paper_order(plan: PositionPlan) -> PaperOrderRequest:
    """Encode a plan for a future paper ledger; it cannot submit anything."""
    raw = f"{plan.tag}|{plan.side}|{plan.quantity:.12f}|{plan.expected_execution_price:.12f}"
    order_id = "paper-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
    return PaperOrderRequest(order_id, plan.symbol, plan.side, plan.quantity, plan.expected_execution_price, plan.stop, plan.take_profit, plan.tag, plan.model_family)
