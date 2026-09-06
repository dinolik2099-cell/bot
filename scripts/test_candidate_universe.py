"""Synthetic/metadata-only candidate-universe contract tests; no research data."""
from dataclasses import replace
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from quantbot.research.candidate_universe import (
    CURRENT_PROTOCOL_SCOPE, build_candidate_universe, candidate_entry, candidate_universe_hash,
)
from quantbot.research.model_registry import ModelSpec, RegisteredModel, register_existing_models
from quantbot.strategies.model_pool import register_model_pool


def synthetic_strategy(df, period=2):
    return df


def synthetic_model(**overrides):
    fields = {
        "name": "synthetic", "category": "synthetic", "source": "test", "rationale": "metadata contract",
        "required_columns": ("close",), "parameter_grid": {"period": (2, 3)}, "market_regimes": ("test",),
        "family": "synthetic", "future_data_risk": "none_declared", "research_version": "v1",
        "model_id": "quantbot.synthetic.v1", "causal_timing": "t_minus_1_to_t_intent",
        "long_short_capable": True, "warmup_bars": 3,
    }
    fields.update(overrides)
    spec = ModelSpec(**fields)
    return RegisteredModel(spec=spec, strategy=synthetic_strategy)


def main():
    register_existing_models(); register_model_pool()
    universe = build_candidate_universe(); again = build_candidate_universe()
    assert len(universe) == 36
    assert candidate_universe_hash(universe) == candidate_universe_hash(again)
    assert len({x.model_id for x in universe}) == len(universe)
    assert all(x.eligibility_state == "eligible" and x.research_eligible for x in universe)
    assert all(isinstance(x.warmup_bars, int) and x.warmup_bars >= 0 for x in universe)
    assert all(len(x.parameter_grid_hash) == len(x.strategy_function_hash) == len(x.implementation_module_hash) == 64 for x in universe)
    assert CURRENT_PROTOCOL_SCOPE.timeframe == "1h" and len(CURRENT_PROTOCOL_SCOPE.symbols) == 6

    base = synthetic_model()
    entry = candidate_entry(base)
    assert entry.research_eligible and entry.eligibility_state == "eligible"
    assert entry.strategy_function_hash and entry.implementation_module_hash
    assert "strategy_function_hash" in entry.canonical_dict()
    assert "implementation_module_hash" in entry.canonical_dict()
    mutated = candidate_entry(replace(base, spec=replace(base.spec, parameter_grid={"period": (2, 4)})))
    assert candidate_universe_hash((entry,)) != candidate_universe_hash((mutated,))

    unsafe = candidate_entry(synthetic_model(future_data_risk="blocked"))
    unknown = candidate_entry(synthetic_model(future_data_risk="unknown", warmup_bars=None))
    assert not unsafe.research_eligible and unsafe.eligibility_state == "ineligible"
    assert not unknown.research_eligible and unknown.eligibility_state == "review_required"
    try:
        build_candidate_universe((base, replace(base, spec=replace(base.spec, name="duplicate"))))
    except ValueError as exc:
        assert "model_id collision" in str(exc)
    else:
        raise AssertionError("duplicate model_id must fail")
    print("CANDIDATE_UNIVERSE_SYNTHETIC_TEST_OK")


if __name__ == "__main__":
    main()
