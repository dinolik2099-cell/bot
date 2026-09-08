"""P3 live-authority state machine. No transition can currently grant LIVE."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from quantbot.research.authorization import Capability, locked_evidence


@dataclass(frozen=True)
class LiveState(str, Enum):
    DISABLED="DISABLED"; PAPER_ONLY="PAPER_ONLY"; LIVE_ELIGIBLE="LIVE_ELIGIBLE"; TINY_LIVE_AUTHORIZED="TINY_LIVE_AUTHORIZED"; SMALL_LIVE_AUTHORIZED="SMALL_LIVE_AUTHORIZED"; EMERGENCY_STOPPED="EMERGENCY_STOPPED"
@dataclass(frozen=True)
class LiveLimits:
    max_notional: float = 0.0; max_positions: int = 0; max_order: float = 0.0; max_daily_loss: float = 0.0; max_drawdown: float = 0.0; stale_data_timeout_seconds: int = 0
@dataclass(frozen=True)
class LiveAuthorizationState:
    state: LiveState = LiveState.PAPER_ONLY
    reason: str = "future_explicit_authorization_required"
    limits: LiveLimits = LiveLimits()

    def require_live(self) -> None:
        locked_evidence(Capability.LIVE).require()

    def transition(self, target: LiveState, *, evidence_complete: bool, reconciled: bool, emergency_stop: bool = False) -> "LiveAuthorizationState":
        if emergency_stop: return LiveAuthorizationState(LiveState.EMERGENCY_STOPPED, "emergency_stop", self.limits)
        if target in {LiveState.TINY_LIVE_AUTHORIZED, LiveState.SMALL_LIVE_AUTHORIZED}:
            if not evidence_complete or not reconciled: raise PermissionError("live_transition_evidence_missing")
            self.require_live()
        if target == LiveState.LIVE_ELIGIBLE and not (evidence_complete and reconciled): raise PermissionError("live_eligibility_evidence_missing")
        return LiveAuthorizationState(target, "state_transition", self.limits)
