"""In-memory, append-only audit events for the non-executable decision chain."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Mapping
from types import MappingProxyType
import hashlib


_ALLOWED = {
    "signal_created": {"portfolio_selected"},
    "portfolio_selected": {"risk_approved", "risk_rejected"},
    "risk_approved": {"paper_requested"},
    "risk_rejected": set(),
    "paper_requested": set(),
}


def _freeze_payload(value: Any) -> Any:
    """Return an immutable recursive copy suitable for audit evidence."""
    if isinstance(value, Mapping):
        return MappingProxyType({
            key: _freeze_payload(item)
            for key, item in value.items()
        })
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_payload(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return frozenset(_freeze_payload(item) for item in value)
    return value


@dataclass(frozen=True)
class AuditEvent:
    sequence: int
    event_type: str
    correlation_id: str
    payload: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "payload", _freeze_payload(self.payload))


class DecisionAuditTrail:
    """Append-only state machine; persistence is deliberately outside this layer."""
    def __init__(self) -> None:
        self._events: list[AuditEvent] = []

    @property
    def events(self) -> tuple[AuditEvent, ...]:
        return tuple(self._events)

    def append(self, event_type: str, correlation_id: str, payload: Mapping[str, Any] | None = None) -> AuditEvent:
        if event_type not in _ALLOWED or not correlation_id:
            raise ValueError("invalid audit event")
        prior = [item for item in self._events if item.correlation_id == correlation_id]
        if prior and event_type not in _ALLOWED[prior[-1].event_type]:
            raise ValueError(f"invalid transition: {prior[-1].event_type} -> {event_type}")
        if not prior and event_type != "signal_created":
            raise ValueError("audit trail must start with signal_created")
        event = AuditEvent(len(self._events) + 1, event_type, correlation_id, dict(payload or {}))
        self._events.append(event)
        return event


def correlation_id(*parts: str) -> str:
    return "audit-" + hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:24]
