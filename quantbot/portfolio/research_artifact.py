"""Portfolio construction/audit artifacts, deliberately reusing shared-capital."""
from __future__ import annotations
from dataclasses import asdict, dataclass
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
    if float(artifact.get("gross_exposure", 2)) > 1 + 1e-12: raise ValueError("portfolio_bankruptcy_invariant")
    return True
