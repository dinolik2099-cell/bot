"""N13 OOS opening protocol: built for audit, permanently deny-by-default."""
from __future__ import annotations

from dataclasses import dataclass
from .authorization import AuthorizationError, Capability, locked_evidence


@dataclass(frozen=True)
class OOSOpeningProtocol:
    research_freeze_identity: str
    research_plan_identity: str
    status: str = "SEALED"
    authorization: str = "NOT_AUTHORIZED"

    def request_window(self, window: str) -> None:
        if window != "OOS":
            raise AuthorizationError("oos_protocol_only_accepts_oos_window")
        locked_evidence(Capability.OOS, freeze_identity=self.research_freeze_identity,
                        plan_identity=self.research_plan_identity).require()
