"""Synthetic taxonomy/metadata contracts; deliberately no market-data access."""
from dataclasses import replace
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from quantbot.research.candidate_universe import candidate_entry
from quantbot.research.family_taxonomy import CANONICAL_FAMILIES, validate_taxonomy
from quantbot.research.model_registry import (
    ModelSpec, RegisteredModel, list_models, register_existing_models, validate_registry,
)
from quantbot.strategies.model_pool import register_model_pool


def strategy(df, period=2):
    return df


def model(**changes):
    values = dict(name="synthetic", category="synthetic", source="test", rationale="test",
                  required_columns=("close",), parameter_grid={"period": (2,)}, market_regimes=("test",),
                  family="trend", future_data_risk="none_declared", research_version="v1",
                  model_id="quantbot.synthetic.v1", causal_timing="t_minus_1_to_t_intent",
                  long_short_capable=True, warmup_bars=2)
    values.update(changes)
    return RegisteredModel(ModelSpec(**values), strategy)


def must_fail(fn):
    try:
        fn()
    except ValueError:
        return
    raise AssertionError("expected metadata validation failure")


def main():
    register_existing_models(); register_model_pool(); validate_registry()
    models = list_models()
    assert len(models) == 36
    assert {item.spec.family for item in models} <= CANONICAL_FAMILIES
    assert len({item.spec.model_id for item in models}) == 36
    assert all(item.spec.warmup_bars is not None for item in models)
    assert all(candidate_entry(item).research_eligible for item in models)
    must_fail(lambda: validate_taxonomy("趋势", ()))
    must_fail(lambda: validate_taxonomy("trend", ("not_a_trait",)))
    assert candidate_entry(model(warmup_bars=None)).eligibility_state == "review_required"
    assert candidate_entry(model(warmup_bars=-1)).eligibility_state == "ineligible"
    must_fail(lambda: validate_registry_with_bad_warmup())
    print("MODEL_TAXONOMY_METADATA_SYNTHETIC_TEST_OK")


def validate_registry_with_bad_warmup():
    # Unit-level validation is exercised without adding unsafe metadata to the global registry.
    from quantbot.research.model_registry import _REGISTRY
    original = dict(_REGISTRY)
    try:
        _REGISTRY.clear(); _REGISTRY["synthetic"] = model(warmup_bars=-1)
        validate_registry()
    finally:
        _REGISTRY.clear(); _REGISTRY.update(original)


if __name__ == "__main__":
    main()
