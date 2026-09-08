"""P3 exchange boundary.  Paper adapter is the only constructible adapter."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping
from quantbot.research.authorization import Capability, locked_evidence


@dataclass(frozen=True)
class ExchangeOrder:
    symbol: str
    side: str
    quantity: float
    client_order_id: str = ""

class OrderStatus(str, Enum): REQUESTED="REQUESTED"; ACCEPTED="ACCEPTED"; PARTIAL="PARTIAL"; FILLED="FILLED"; CANCELLED="CANCELLED"; REJECTED="REJECTED"
@dataclass(frozen=True)
class Fill:
    order_id: str; quantity: float; price: float
class ExchangeAdapter:
    def market_event(self, symbol: str, price: float) -> None: raise NotImplementedError
    def submit(self, order: ExchangeOrder) -> Mapping[str, object]: raise NotImplementedError
    def cancel(self, order_id: str) -> Mapping[str, object]: raise NotImplementedError
    def reconcile(self) -> Mapping[str, object]: raise NotImplementedError


class PaperExchangeAdapter(ExchangeAdapter):
    mode = "PAPER"
    def __init__(self) -> None: self._orders: dict[str, dict[str, object]] = {}; self._prices: dict[str, float] = {}
    def market_event(self, symbol: str, price: float) -> None:
        if price <= 0: raise ValueError("market_price_invalid")
        self._prices[symbol] = float(price)
    def submit(self, order: ExchangeOrder) -> dict[str, object]:
        if order.quantity <= 0:
            raise ValueError("quantity_must_be_positive")
        order_id = order.client_order_id or f"paper-{len(self._orders)+1}"
        if order_id in self._orders: raise ValueError("duplicate_order_identity")
        state = {"order_id": order_id, "status": OrderStatus.ACCEPTED.value, "symbol": order.symbol, "side": order.side, "quantity": order.quantity, "filled": 0.0}
        self._orders[order_id] = state; return {**state, "status": "PAPER_ACCEPTED"}
    def fill(self, order_id: str, quantity: float, price: float) -> Fill:
        state = self._orders.get(order_id)
        if state is None or state["status"] in {OrderStatus.CANCELLED.value, OrderStatus.FILLED.value}: raise ValueError("order_not_fillable")
        if quantity <= 0 or price <= 0 or state["filled"] + quantity > state["quantity"] + 1e-12: raise ValueError("fill_invalid")
        state["filled"] += quantity; state["status"] = OrderStatus.FILLED.value if state["filled"] == state["quantity"] else OrderStatus.PARTIAL.value
        return Fill(order_id, quantity, price)
    def cancel(self, order_id: str) -> dict[str, object]:
        state = self._orders.get(order_id)
        if state is None: raise ValueError("order_unknown")
        state["status"] = OrderStatus.CANCELLED.value; return dict(state)
    def reconcile(self) -> Mapping[str, object]: return {"mode": self.mode, "orders": tuple(dict(self._orders[key]) for key in sorted(self._orders))}

class FakeExchangeAdapter(PaperExchangeAdapter):
    mode = "FAKE"


class LiveExchangeAdapter:
    def __init__(self) -> None:
        locked_evidence(Capability.LIVE).require()
