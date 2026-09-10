"""Canonical future portfolio entrypoint; deny before any protected data access."""
from __future__ import annotations
from typing import Any, Mapping
from .authorization import AuthorizationEvidence, Capability
from .future_stages import validate_portfolio_protocol
from .non_oos_series import validate_external_n12_anchor
from .evaluation import make_strategy_adapter
from .canonical_data_adapter import make_n8_canonical_window_loader

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

def build_canonical_signal_map(*, frame, strategy, params, model_id, symbol, task_identity,
                               risk_fraction: float=0.01, position_fraction: float=1.0):
    """Convert the canonical T-1 adapter into shared-capital signal-map rows.

    This helper is deliberately internal-facing: callers obtain ``frame`` only
    after ``authorize_portfolio_run`` and the N8 formal loader have succeeded.
    """
    if not model_id or not symbol or not task_identity: raise PortfolioRunnerError('portfolio_signal_identity_missing')
    adapter=make_strategy_adapter(strategy,full_frame=frame,params=params,risk_fraction=risk_fraction,
                                  position_fraction=position_fraction,tag=task_identity)
    signals={}
    for index in range(len(frame)):
        signal=adapter(frame.iloc[:index],index)
        if signal is not None:
            if signal.stop_price is None: raise PortfolioRunnerError('portfolio_signal_stop_required')
            signals[frame.index[index]]={'side':signal.side,'stop_price':signal.stop_price,'take_profit':signal.take_profit,'tag':signal.tag}
    return {(model_id,symbol):signals}

def make_portfolio_window_loader(*, n8_context, raw_root, protocol, diagnostic, manifest,
                                 n11_identity, candidate_count, correlation_sha256, evidence):
    """Formal constructor: authorization precedes canonical loader creation."""
    authorize_portfolio_run(protocol=protocol,diagnostic=diagnostic,manifest=manifest,n11_identity=n11_identity,
                            candidate_count=candidate_count,correlation_sha256=correlation_sha256,evidence=evidence)
    return make_n8_canonical_window_loader(n8_context,raw_root)
