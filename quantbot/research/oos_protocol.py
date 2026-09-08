"""N13 OOS opening protocol: built for audit, permanently deny-by-default."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Mapping
from .authorization import AuthorizationError, Capability, locked_evidence


@dataclass(frozen=True)
class OOSState(str, Enum):
    SEALED = "SEALED"
    PRECHECK_FAILED = "PRECHECK_FAILED"
    ELIGIBLE_BUT_NOT_AUTHORIZED = "ELIGIBLE_BUT_NOT_AUTHORIZED"
    AUTHORIZED = "AUTHORIZED"
    OPENED = "OPENED"


@dataclass(frozen=True)
class PreOOSChecklist:
    candidate_freeze_identity: str
    plan_identity: str
    manifest_identity: str
    dataset_id: str
    oos_boundary_identity: str
    source_git_commit: str
    clean_tracked_tree: bool
    complete_evidence: bool
    complete_diagnostics: bool
    no_post_validation_mutation: bool
    explicit_authorization: bool = False

    def passed(self) -> bool:
        return all((self.candidate_freeze_identity, self.plan_identity, self.manifest_identity, self.dataset_id,
                    self.oos_boundary_identity, self.source_git_commit, self.clean_tracked_tree,
                    self.complete_evidence, self.complete_diagnostics, self.no_post_validation_mutation))

    def identity(self) -> str:
        body = json.dumps(self.__dict__, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(body.encode()).hexdigest()


@dataclass(frozen=True)
class OOSOpeningProtocol:
    research_freeze_identity: str
    research_plan_identity: str
    status: OOSState = OOSState.SEALED
    authorization: str = "NOT_AUTHORIZED"

    def precheck(self, checklist: PreOOSChecklist) -> OOSState:
        if checklist.candidate_freeze_identity != self.research_freeze_identity or checklist.plan_identity != self.research_plan_identity or not checklist.passed():
            return OOSState.PRECHECK_FAILED
        return OOSState.ELIGIBLE_BUT_NOT_AUTHORIZED

    def request_window(self, window: str, checklist: PreOOSChecklist | None = None) -> None:
        if window != "OOS":
            raise AuthorizationError("oos_protocol_only_accepts_oos_window")
        if checklist is None or self.precheck(checklist) != OOSState.ELIGIBLE_BUT_NOT_AUTHORIZED:
            raise AuthorizationError("oos_precheck_failed")
        # Even explicit data carried by a caller is not an authority: opening is
        # reserved for a future separately reviewed implementation.
        locked_evidence(Capability.OOS, freeze_identity=self.research_freeze_identity,
                        plan_identity=self.research_plan_identity).require()
