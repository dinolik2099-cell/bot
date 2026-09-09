"""Portfolio construction/audit artifacts, deliberately reusing shared-capital."""
from __future__ import annotations
from dataclasses import asdict, dataclass
import math
from typing import Mapping, Sequence
from quantbot.research.artifact_store import seal, validate_seal
from .weight_engine import WeightCandidate, WeightPolicy, compute_weights

@dataclass(frozen=True)
class PortfolioCandidate:
    candidate: WeightCandidate
    candidate_identity: str
    correlation_row: Mapping[str, float]

def build_portfolio_artifact(candidates: Sequence[PortfolioCandidate], policy: WeightPolicy, *, input_identity: str) -> dict[str, object]:
    ids = [item.candidate.candidate_id for item in candidates]
    if len(ids) != len(set(ids)) or not candidates: raise ValueError("portfolio_candidate_set_invalid")
    if policy.method == "fixed": raise ValueError("fixed_portfolio_artifact_requires_explicit_frozen_weights")
    weights = compute_weights(tuple(item.candidate for item in candidates), policy)
    correlations = {item.candidate.candidate_id: {key: float(value) for key, value in sorted(item.correlation_row.items())} for item in candidates}
    if any(abs(value) > 1 for row in correlations.values() for value in row.values()): raise ValueError("correlation_contract_invalid")
    gross = sum(weights.values())
    payload = {"schema_version": "quantbot-portfolio-artifact-v1", "input_identity": input_identity,
               "shared_capital_component": "quantbot.portfolio.shared_capital.shared_backtest", "policy": asdict(policy),
               "candidates": [{"candidate": asdict(item.candidate), "candidate_identity": item.candidate_identity} for item in candidates],
               "weights": weights, "gross_exposure": gross, "net_exposure": gross,
               "correlations": correlations, "diversification": {"candidate_count": len(candidates), "effective_count": 1 / sum(value * value for value in weights.values())},
               "rebalance_identity_input": input_identity, "oos_read": False}
    return seal(payload)

def validate_portfolio_artifact(artifact: Mapping[str, object]) -> bool:
    validate_seal(artifact)
    if artifact.get("schema_version") != "quantbot-portfolio-artifact-v1" or artifact.get("oos_read") is not False: raise ValueError("portfolio_artifact_invalid")
    if artifact.get("shared_capital_component") != "quantbot.portfolio.shared_capital.shared_backtest" or artifact.get("rebalance_identity_input") != artifact.get("input_identity") or not isinstance(artifact.get("input_identity"),str) or not artifact["input_identity"]: raise ValueError("portfolio_binding_invalid")
    raw_candidates=artifact.get("candidates"); raw_policy=artifact.get("policy")
    if not isinstance(raw_candidates,list) or not raw_candidates or not isinstance(raw_policy,Mapping): raise ValueError("portfolio_contents_invalid")
    try:
        policy=WeightPolicy(**dict(raw_policy))
        if policy.method == "fixed": raise ValueError("fixed_portfolio_artifact_requires_explicit_frozen_weights")
        candidates=tuple(WeightCandidate(**dict(row["candidate"])) for row in raw_candidates)
    except (TypeError,KeyError,ValueError) as exc: raise ValueError("portfolio_candidate_or_policy_invalid") from exc
    ids=[item.candidate_id for item in candidates]
    identities=[row.get("candidate_identity") for row in raw_candidates]
    if len(ids)!=len(set(ids)) or any(not isinstance(value,str) or not value for value in identities) or len(identities)!=len(set(identities)): raise ValueError("portfolio_candidate_identity_invalid")
    expected=compute_weights(candidates,policy); actual=artifact.get("weights")
    if not isinstance(actual,Mapping) or set(actual)!=set(expected) or any(not isinstance(value,(int,float)) or not math.isclose(float(value),expected[key],rel_tol=0,abs_tol=1e-12) for key,value in actual.items()): raise ValueError("portfolio_weights_invalid")
    gross=sum(expected.values()); diversification=artifact.get("diversification")
    if not math.isclose(float(artifact.get("gross_exposure",-1)),gross,rel_tol=0,abs_tol=1e-12) or not math.isclose(float(artifact.get("net_exposure",-1)),gross,rel_tol=0,abs_tol=1e-12) or gross > 1+1e-12: raise ValueError("portfolio_bankruptcy_invariant")
    if not isinstance(diversification,Mapping) or diversification.get("candidate_count")!=len(candidates) or not math.isclose(float(diversification.get("effective_count",0)),1/sum(value*value for value in expected.values()),rel_tol=0,abs_tol=1e-12): raise ValueError("portfolio_diversification_invalid")
    correlations=artifact.get("correlations")
    if not isinstance(correlations,Mapping) or set(correlations)!=set(ids): raise ValueError("portfolio_correlations_invalid")
    for candidate_id,row in correlations.items():
        if not isinstance(row,Mapping) or any(key not in ids or not isinstance(value,(int,float)) or not math.isfinite(float(value)) or abs(float(value))>1 for key,value in row.items()): raise ValueError("portfolio_correlations_invalid")
    return True
