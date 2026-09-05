"""Pure capital-protection circuit breaker; no portfolio mutation or execution."""
from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class RiskSnapshot:
    equity: float
    day_start_equity: float
    rolling_start_equity: float
    peak_equity: float
    consecutive_losses: int = 0

@dataclass(frozen=True)
class CircuitBreakerPolicy:
    max_daily_loss: float = .03
    max_rolling_loss: float = .06
    max_drawdown: float = .12
    max_consecutive_losses: int = 5

@dataclass(frozen=True)
class CircuitBreakerDecision:
    allowed: bool
    reason: str

def evaluate_circuit_breaker(snapshot: RiskSnapshot, policy: CircuitBreakerPolicy = CircuitBreakerPolicy()) -> CircuitBreakerDecision:
    if min(snapshot.equity,snapshot.day_start_equity,snapshot.rolling_start_equity,snapshot.peak_equity) <= 0:
        return CircuitBreakerDecision(False,"invalid_equity_snapshot")
    if snapshot.equity / snapshot.day_start_equity - 1 <= -policy.max_daily_loss:
        return CircuitBreakerDecision(False,"max_daily_loss")
    if snapshot.equity / snapshot.rolling_start_equity - 1 <= -policy.max_rolling_loss:
        return CircuitBreakerDecision(False,"max_rolling_loss")
    if snapshot.equity / snapshot.peak_equity - 1 <= -policy.max_drawdown:
        return CircuitBreakerDecision(False,"max_drawdown")
    if snapshot.consecutive_losses >= policy.max_consecutive_losses:
        return CircuitBreakerDecision(False,"max_consecutive_losses")
    return CircuitBreakerDecision(True,"allowed")
