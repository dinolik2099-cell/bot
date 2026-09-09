"""Identity-bound readiness decisions for the locked post-N12 path.

These gates intentionally *classify* evidence rather than grant authority.
They make it impossible to confuse a complete engineering package with
permission to open OOS, start Paper, or place a Live order.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Mapping

from .artifact_store import seal, validate_seal
from .authorization import Capability, locked_evidence


REQUIRED_PRE_OOS_EVIDENCE = (
    "n11_result", "n12_diagnostics", "portfolio", "stress",
    "walk_forward", "monte_carlo", "long_horizon",
)


class ReadinessDecision(str, Enum):
    RESEARCH_INCOMPLETE = "RESEARCH_INCOMPLETE"
    READY_BUT_NOT_AUTHORIZED = "READY_BUT_NOT_AUTHORIZED"
    PAPER_NOT_AUTHORIZED = "PAPER_NOT_AUTHORIZED"
    LIVE_NOT_AUTHORIZED = "LIVE_NOT_AUTHORIZED"


@dataclass(frozen=True)
class ReadinessEvidence:
    """The only evidence envelope accepted by future OOS/Paper/Live gates."""
    research_freeze_identity: str
    research_plan_identity: str
    n11_identity: str
    n12_identity: str
    artifacts: Mapping[str, str]
    oos_status: str = "SEALED"
    oos_authorization: str = "NOT_AUTHORIZED"

    def artifact(self) -> dict[str, object]:
        return seal({"schema_version":"quantbot-readiness-evidence-v1", **asdict(self)})


def _is_identity(value: object) -> bool:
    return isinstance(value,str) and len(value)==64 and all(char in "0123456789abcdef" for char in value)


def validate_readiness_evidence(payload: Mapping[str, object], *, expected_freeze_identity: str,
                                expected_plan_identity: str) -> bool:
    validate_seal(payload)
    if payload.get("schema_version")!="quantbot-readiness-evidence-v1": raise ValueError("readiness_schema_invalid")
    if payload.get("research_freeze_identity")!=expected_freeze_identity or payload.get("research_plan_identity")!=expected_plan_identity:
        raise ValueError("readiness_chain_identity_mismatch")
    if payload.get("oos_status")!="SEALED" or payload.get("oos_authorization")!="NOT_AUTHORIZED":
        raise ValueError("readiness_oos_seal_invalid")
    artifacts=payload.get("artifacts")
    if not isinstance(artifacts,Mapping): raise ValueError("readiness_artifacts_invalid")
    if any(not _is_identity(artifacts.get(name)) for name in REQUIRED_PRE_OOS_EVIDENCE):
        raise ValueError("readiness_evidence_incomplete")
    if not _is_identity(payload.get("n11_identity")) or not _is_identity(payload.get("n12_identity")):
        raise ValueError("readiness_upstream_identity_invalid")
    return True


def pre_oos_decision(payload: Mapping[str, object], *, expected_freeze_identity: str,
                     expected_plan_identity: str) -> ReadinessDecision:
    try:
        validate_readiness_evidence(payload,expected_freeze_identity=expected_freeze_identity,
                                    expected_plan_identity=expected_plan_identity)
    except (ValueError, RuntimeError):
        return ReadinessDecision.RESEARCH_INCOMPLETE
    # Evidence can establish review readiness, never authorization.
    return ReadinessDecision.READY_BUT_NOT_AUTHORIZED


def require_paper_or_live(payload: Mapping[str, object], *, capability: Capability,
                          expected_freeze_identity: str, expected_plan_identity: str) -> None:
    if capability not in {Capability.PAPER_RUNTIME,Capability.LIVE}: raise ValueError("readiness_capability_invalid")
    validate_readiness_evidence(payload,expected_freeze_identity=expected_freeze_identity,
                                expected_plan_identity=expected_plan_identity)
    # Paper requires a separate startup authorization and Live is globally
    # locked.  Neither can be reached merely by presenting this envelope.
    locked_evidence(capability,freeze_identity=expected_freeze_identity,
                    plan_identity=expected_plan_identity).require()
