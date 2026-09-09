"""Canonical future portfolio entrypoint; deny before any protected data access."""
from __future__ import annotations
from typing import Any, Mapping
from .authorization import AuthorizationEvidence, Capability
from .future_stages import validate_portfolio_protocol
from .non_oos_series import validate_external_n12_anchor

class PortfolioRunnerError(RuntimeError): pass

def authorize_portfolio_run(*, protocol: Mapping[str,Any], diagnostic: Mapping[str,Any], manifest: Mapping[str,Any],
                            n11_identity: str, candidate_count: int, correlation_sha256: str,
                            evidence: AuthorizationEvidence) -> None:
    """Metadata-only pre-data gate for the future canonical runner."""
    validate_portfolio_protocol(protocol)
    validate_external_n12_anchor(diagnostic,manifest,expected_n11_identity=n11_identity,
                                 expected_candidate_count=candidate_count,actual_correlation_sha256=correlation_sha256)
    if protocol.get('n11_identity')!=n11_identity or protocol.get('correlation_sha256')!=correlation_sha256:
        raise PortfolioRunnerError('portfolio_external_anchor_mismatch')
    if evidence.capability!=Capability.TRAIN_VALIDATION: raise PortfolioRunnerError('portfolio_capability_invalid')
    evidence.require()
