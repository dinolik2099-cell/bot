"""Machine-readable candidate metadata; it never reads research/OOS data."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import importlib
import inspect
import json
from typing import Any, Iterable

from .model_registry import RegisteredModel, list_models


@dataclass(frozen=True)
class CandidateUniverseProtocolScope:
    """Universe assumptions, deliberately separate from model-declared facts."""
    scope_id: str
    symbols: tuple[str, ...]
    timeframe: str
    engine_identity: str
    cost_model_identity: str
    causal_execution_policy: str


CURRENT_PROTOCOL_SCOPE = CandidateUniverseProtocolScope(
    scope_id="quantbot-six-symbol-1h-v1",
    symbols=("BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT"),
    timeframe="1h",
    engine_identity="quantbot.backtest.engine_v2.BacktestEngine",
    cost_model_identity="quantbot.backtest.costs.CostModel",
    causal_execution_policy="intent at T-1 may be considered no earlier than T",
)


@dataclass(frozen=True)
class CandidateUniverseEntry:
    model_id: str
    name: str
    family: str
    secondary_traits: tuple[str, ...]
    version: str
    implementation_module: str
    lifecycle_status: str
    causal_timing: str
    required_features: tuple[str, ...]
    parameter_grid: dict[str, tuple[Any, ...]]
    long_short_capable: bool | None
    warmup_bars: int | None
    research_eligible: bool
    eligibility_state: str
    eligibility_reasons: tuple[str, ...]
    provenance: str
    rationale: str
    known_limitations: str
    parameter_grid_hash: str
    strategy_function_hash: str
    implementation_module_hash: str

    def canonical_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["required_features"] = list(self.required_features)
        data["secondary_traits"] = list(self.secondary_traits)
        data["eligibility_reasons"] = list(self.eligibility_reasons)
        data["parameter_grid"] = {key: list(value) for key, value in sorted(self.parameter_grid.items())}
        return data


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _grid_hash(model: RegisteredModel) -> str:
    value = {key: list(values) for key, values in sorted(model.spec.parameter_grid.items())}
    return _digest(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def _strategy_function_hash(model: RegisteredModel) -> str:
    """Function source identity only, intentionally narrower than module identity."""
    return _digest(inspect.getsource(model.strategy).encode("utf-8"))


def _implementation_module_hash(model: RegisteredModel) -> str:
    """Full strategy module source identity, intentionally broader than one function."""
    return _digest(inspect.getsource(importlib.import_module(model.strategy.__module__)).encode("utf-8"))


def _eligibility(model: RegisteredModel) -> tuple[bool, str, tuple[str, ...]]:
    """Fail closed: unsafe or unverified metadata is never research-eligible."""
    spec = model.spec
    blocked, review = [], []
    if spec.status in {"retired", "deferred"}:
        blocked.append(f"lifecycle_status={spec.status}")
    if spec.lookahead_policy != "strictly_causal":
        blocked.append("lookahead_policy_not_strictly_causal")
    if spec.future_data_risk == "blocked":
        blocked.append("future_data_risk_blocked")
    elif spec.future_data_risk != "none_declared":
        review.append(f"future_data_risk={spec.future_data_risk}")
    if not spec.model_id:
        review.append("missing_model_id")
    if spec.causal_timing == "unverified":
        review.append("causal_timing_unverified")
    if spec.long_short_capable is None:
        review.append("long_short_capability_unverified")
    if spec.warmup_bars is None:
        review.append("warmup_bars_unverified")
    elif not isinstance(spec.warmup_bars, int) or isinstance(spec.warmup_bars, bool) or spec.warmup_bars < 0:
        blocked.append("warmup_bars_invalid")
    if blocked:
        return False, "ineligible", tuple(blocked + review)
    if review:
        return False, "review_required", tuple(review)
    return True, "eligible", ()


def candidate_entry(model: RegisteredModel) -> CandidateUniverseEntry:
    spec = model.spec
    eligible, state, reasons = _eligibility(model)
    limitations = "Candidate only; no OOS result is consumed by this specification."
    if spec.warmup_bars is None:
        limitations += " Warmup is unverified and requires explicit model metadata."
    return CandidateUniverseEntry(
        model_id=spec.model_id, name=spec.name, family=spec.family, secondary_traits=spec.secondary_traits, version=spec.research_version,
        implementation_module=model.strategy.__module__, lifecycle_status=spec.status,
        causal_timing=spec.causal_timing, required_features=spec.required_columns,
        parameter_grid={key: tuple(value) for key, value in spec.parameter_grid.items()},
        long_short_capable=spec.long_short_capable, warmup_bars=spec.warmup_bars,
        research_eligible=eligible, eligibility_state=state, eligibility_reasons=reasons,
        provenance=spec.source, rationale=spec.rationale, known_limitations=limitations,
        parameter_grid_hash=_grid_hash(model), strategy_function_hash=_strategy_function_hash(model),
        implementation_module_hash=_implementation_module_hash(model),
    )


def build_candidate_universe(models: Iterable[RegisteredModel] | None = None) -> tuple[CandidateUniverseEntry, ...]:
    source = list_models() if models is None else tuple(models)
    entries = tuple(sorted((candidate_entry(model) for model in source), key=lambda entry: entry.model_id))
    ids = [entry.model_id for entry in entries]
    if len(ids) != len(set(ids)):
        raise ValueError("candidate universe model_id collision")
    return entries


def candidate_universe_hash(entries: tuple[CandidateUniverseEntry, ...]) -> str:
    payload = [entry.canonical_dict() for entry in entries]
    return _digest(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"))
