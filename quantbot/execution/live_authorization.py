"""P3 live-authority state machine. No transition can currently grant LIVE."""
from __future__ import annotations

from dataclasses import dataclass
from quantbot.research.authorization import Capability, locked_evidence


@dataclass(frozen=True)
class LiveAuthorizationState:
    state: str = "LOCKED"
    reason: str = "future_explicit_authorization_required"

    def require_live(self) -> None:
        locked_evidence(Capability.LIVE).require()
