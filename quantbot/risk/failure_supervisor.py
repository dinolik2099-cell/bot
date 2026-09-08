"""Deterministic failure supervisor with no authority to place orders."""
from __future__ import annotations

from dataclasses import dataclass, asdict
from enum import Enum
import hashlib, json
from typing import Iterable


@dataclass(frozen=True)
class FailureSupervisorDecision:
    allowed: bool
    reason: str
    consecutive_failures: int

class FailureCategory(str, Enum):
    DATA="DATA"; STALE_DATA="STALE_DATA"; MISSING_BAR="MISSING_BAR"; MODEL="MODEL"; SIGNAL="SIGNAL"; PORTFOLIO="PORTFOLIO"; RISK="RISK"; ORDER="ORDER"; LEDGER="LEDGER"; RECONCILIATION="RECONCILIATION"; ARTIFACT="ARTIFACT"; AUTHORITY="AUTHORITY"; RUNTIME="RUNTIME"
class Severity(str, Enum): INFO="INFO"; RETRYABLE="RETRYABLE"; TERMINAL="TERMINAL"; CRITICAL="CRITICAL"
@dataclass(frozen=True)
class FailureEvent:
    event_id: str; category: FailureCategory; severity: Severity; message: str; sequence: int
@dataclass(frozen=True)
class RecoveryPolicy:
    max_retries: int = 2
@dataclass(frozen=True)
class SupervisorState:
    events: tuple[FailureEvent, ...] = ()
    retries: int = 0
@dataclass(frozen=True)
class SupervisorDecision:
    action: str; retry_allowed: bool; terminal: bool; state_identity: str


def supervise_failures(events: Iterable[str], *, max_consecutive_failures: int = 3) -> FailureSupervisorDecision:
    if max_consecutive_failures < 1:
        raise ValueError("invalid_failure_threshold")
    streak = 0
    for event in events:
        streak = streak + 1 if event == "FAILED" else 0
    return FailureSupervisorDecision(streak < max_consecutive_failures,
                                     "ok" if streak < max_consecutive_failures else "failure_circuit_open", streak)

def decide(event: FailureEvent, state: SupervisorState = SupervisorState(), policy: RecoveryPolicy = RecoveryPolicy()) -> SupervisorDecision:
    fail_closed = {FailureCategory.DATA, FailureCategory.STALE_DATA, FailureCategory.MISSING_BAR, FailureCategory.LEDGER, FailureCategory.RECONCILIATION, FailureCategory.ARTIFACT, FailureCategory.AUTHORITY, FailureCategory.RISK}
    events = state.events + (event,); body = {"events": [asdict(item) for item in events], "retries": state.retries}
    identity = hashlib.sha256(json.dumps(body, sort_keys=True, default=str, separators=(",", ":")).encode()).hexdigest()
    terminal = event.severity in {Severity.TERMINAL, Severity.CRITICAL} or event.category in fail_closed
    retry = event.severity == Severity.RETRYABLE and not terminal and state.retries < policy.max_retries
    return SupervisorDecision("STOP" if terminal else ("RETRY" if retry else "REJECT"), retry, terminal, identity)
