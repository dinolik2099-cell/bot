"""In-memory paper order ledger with idempotency and explicit lifecycle rules."""
from __future__ import annotations
from dataclasses import dataclass
from .paper import PaperOrderRequest


@dataclass(frozen=True)
class PaperOrderState:
    request: PaperOrderRequest
    status: str = "requested"
    fill_price: float | None = None
    rejection_reason: str | None = None


class PaperLedger:
    """Ephemeral ledger only; persistence and exchange adapters are out of scope."""
    def __init__(self) -> None:
        self._orders: dict[str, PaperOrderState] = {}

    @property
    def orders(self) -> tuple[PaperOrderState, ...]:
        return tuple(self._orders.values())

    def request(self, order: PaperOrderRequest) -> PaperOrderState:
        existing = self._orders.get(order.client_order_id)
        if existing is not None:
            if existing.request != order:
                raise ValueError("idempotency key collision with different paper order")
            return existing
        state = PaperOrderState(order)
        self._orders[order.client_order_id] = state
        return state

    def fill(self, client_order_id: str, fill_price: float) -> PaperOrderState:
        state = self._require_requested(client_order_id)
        if fill_price <= 0:
            raise ValueError("fill price must be positive")
        updated = PaperOrderState(state.request, "filled", float(fill_price))
        self._orders[client_order_id] = updated
        return updated

    def reject(self, client_order_id: str, reason: str) -> PaperOrderState:
        state = self._require_requested(client_order_id)
        if not reason:
            raise ValueError("rejection reason is required")
        updated = PaperOrderState(state.request, "rejected", rejection_reason=reason)
        self._orders[client_order_id] = updated
        return updated

    def _require_requested(self, client_order_id: str) -> PaperOrderState:
        try:
            state = self._orders[client_order_id]
        except KeyError as exc:
            raise KeyError("unknown paper order") from exc
        if state.status != "requested":
            raise ValueError(f"paper order is already terminal: {state.status}")
        return state
