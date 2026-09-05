"""Explicit emergency-stop state for blocking new risk without side effects."""
from __future__ import annotations
from dataclasses import dataclass
from .circuit_breaker import CircuitBreakerDecision, RiskSnapshot

@dataclass(frozen=True)
class EmergencyStop:
    active: bool
    reason: str
    equity: float

def emergency_stop_from_breaker(decision: CircuitBreakerDecision, snapshot: RiskSnapshot) -> EmergencyStop:
    return EmergencyStop(not decision.allowed, decision.reason, snapshot.equity)
