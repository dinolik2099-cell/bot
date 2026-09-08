"""P3 exchange boundary.  Paper adapter is the only constructible adapter."""
from __future__ import annotations

from dataclasses import dataclass
from quantbot.research.authorization import Capability, locked_evidence


@dataclass(frozen=True)
class ExchangeOrder:
    symbol: str
    side: str
    quantity: float


class PaperExchangeAdapter:
    mode = "PAPER"
    def submit(self, order: ExchangeOrder) -> dict[str, object]:
        if order.quantity <= 0:
            raise ValueError("quantity_must_be_positive")
        return {"status": "PAPER_ACCEPTED", "symbol": order.symbol, "side": order.side, "quantity": order.quantity}


class LiveExchangeAdapter:
    def __init__(self) -> None:
        locked_evidence(Capability.LIVE).require()
