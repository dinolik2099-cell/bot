"""Deterministic portfolio weights; no performance optimization or OOS input."""
from __future__ import annotations
import math
from dataclasses import dataclass
from typing import Mapping, Sequence

@dataclass(frozen=True)
class WeightPolicy:
    method: str = "equal"
    maximum_weight: float = 0.35
    minimum_weight: float = 0.0
    family_cap: float = 0.60
    symbol_cap: float = 0.50

@dataclass(frozen=True)
class WeightCandidate:
    candidate_id: str
    family: str
    symbol: str
    risk: float = 1.0

def _finite(value: float) -> float:
    value = float(value)
    if not math.isfinite(value) or value < 0: raise ValueError("invalid_weight_value")
    return value

def compute_weights(candidates: Sequence[WeightCandidate], policy: WeightPolicy = WeightPolicy(), *, fixed: Mapping[str, float] | None = None) -> dict[str, float]:
    if not candidates or len({item.candidate_id for item in candidates}) != len(candidates): raise ValueError("candidate_universe_invalid")
    if not 0 <= policy.minimum_weight <= policy.maximum_weight <= 1 or not 0 < policy.family_cap <= 1 or not 0 < policy.symbol_cap <= 1: raise ValueError("weight_policy_invalid")
    ids = [item.candidate_id for item in candidates]
    if policy.method == "equal": raw = {key: 1 / len(ids) for key in ids}
    elif policy.method == "fixed":
        if fixed is None or set(fixed) != set(ids): raise ValueError("fixed_weight_set_invalid")
        raw = {key: _finite(fixed[key]) for key in ids}
    elif policy.method == "risk":
        risks = {item.candidate_id: _finite(item.risk) for item in candidates}
        if any(value == 0 for value in risks.values()): raise ValueError("risk_weight_zero_risk_invalid")
        inverse = {key: 1 / value for key, value in risks.items()}; total = sum(inverse.values()); raw = {key: value / total for key, value in inverse.items()}
    else: raise ValueError("weight_method_invalid")
    total = sum(raw.values())
    if not math.isfinite(total) or total <= 0 or total > 1 + 1e-12: raise ValueError("weight_total_invalid")
    normalized = {key: value / total for key, value in raw.items()}
    if any(value < policy.minimum_weight - 1e-12 or value > policy.maximum_weight + 1e-12 for value in normalized.values()): raise ValueError("individual_weight_cap_violation")
    families: dict[str, float] = {}; symbols: dict[str, float] = {}
    for item in candidates:
        families[item.family] = families.get(item.family, 0.0) + normalized[item.candidate_id]; symbols[item.symbol] = symbols.get(item.symbol, 0.0) + normalized[item.candidate_id]
    if any(value > policy.family_cap + 1e-12 for value in families.values()): raise ValueError("family_cap_violation")
    if any(value > policy.symbol_cap + 1e-12 for value in symbols.values()): raise ValueError("symbol_cap_violation")
    return {key: normalized[key] for key in sorted(normalized)}
