"""Single fail-closed authorization vocabulary for post-N10 engineering.

This module deliberately grants no research or trading authority by default.
It is metadata-only and never imports a loader, exchange, or evaluator.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Mapping


class AuthorizationError(PermissionError):
    pass


class Capability(str, Enum):
    SYNTHETIC = "SYNTHETIC"
    TRAIN_VALIDATION = "TRAIN_VALIDATION"
    OOS = "OOS"
    MONTE_CARLO = "MONTE_CARLO"
    PAPER_RUNTIME = "PAPER_RUNTIME"
    LIVE = "LIVE"


LOCKED_CAPABILITIES = frozenset({Capability.OOS, Capability.MONTE_CARLO, Capability.LIVE})


def _identity(value: Mapping[str, object]) -> str:
    return hashlib.sha256(json.dumps(dict(value), sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class AuthorizationEvidence:
    capability: Capability
    status: str = "NOT_AUTHORIZED"
    reason: str = "explicit_future_authorization_required"
    research_freeze_identity: str | None = None
    research_plan_identity: str | None = None
    evidence_identity: str | None = None

    def __post_init__(self) -> None:
        payload = {"capability": self.capability.value, "status": self.status, "reason": self.reason,
                   "research_freeze_identity": self.research_freeze_identity,
                   "research_plan_identity": self.research_plan_identity}
        if self.evidence_identity is None:
            object.__setattr__(self, "evidence_identity", _identity(payload))
        elif self.evidence_identity != _identity(payload):
            raise AuthorizationError("authorization_evidence_identity_mismatch")

    def require(self) -> None:
        if self.status != "AUTHORIZED":
            raise AuthorizationError(f"{self.capability.value.lower()}_not_authorized")
        if self.capability in LOCKED_CAPABILITIES:
            raise AuthorizationError(f"{self.capability.value.lower()}_locked_by_default")


def locked_evidence(capability: Capability, *, freeze_identity: str | None = None,
                    plan_identity: str | None = None) -> AuthorizationEvidence:
    return AuthorizationEvidence(capability, research_freeze_identity=freeze_identity,
                                 research_plan_identity=plan_identity)


def require_sealed_non_oos(context: Mapping[str, object]) -> None:
    if context.get("oos_status") != "SEALED" or context.get("oos_authorization") != "NOT_AUTHORIZED":
        raise AuthorizationError("oos_seal_required")


@dataclass(frozen=True)
class AuthorizationPolicy:
    """Trusted policy anchor.  It never grants a locked capability itself."""
    policy_id: str = "quantbot-post-n10-locked-policy-v1"
    allowed_capabilities: tuple[Capability, ...] = (Capability.SYNTHETIC, Capability.PAPER_RUNTIME)

    def authorize(self, evidence: AuthorizationEvidence) -> bool:
        if evidence.capability not in self.allowed_capabilities:
            raise AuthorizationError("capability_not_in_trusted_policy")
        evidence.require()
        return True
