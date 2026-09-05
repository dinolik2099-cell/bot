from __future__ import annotations

import inspect
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from quantbot.research.model_registry import (
    list_models,
    register_existing_models,
    validate_registry,
)
from quantbot.strategies.model_pool import register_model_pool


def make_frame(n=320):
    idx = pd.date_range("2025-01-01", periods=n, freq="1h", tz="UTC")
    t = np.arange(n, dtype=float)
    close = 100 + 0.04*t + 2*np.sin(t/7) + 0.8*np.sin(t/19)
    open_ = close - 0.2*np.sin(t/3)
    high = np.maximum(open_, close) + 0.8
    low = np.minimum(open_, close) - 0.8
    volume = 1000 + 100*np.sin(t/11) + (t % 17)*5
    return pd.DataFrame({"open":open_,"high":high,"low":low,"close":close,"volume":volume}, index=idx)


def setup():
    register_existing_models()
    register_model_pool()
    validate_registry()
    assert all(item.spec.family != "unclassified" for item in list_models())
    assert all(item.spec.oos_status == "sealed" for item in list_models())


def test_count_and_unique_names():
    models = list_models()
    assert len(models) == 36, len(models)
    names = [m.spec.name for m in models]
    assert len(names) == len(set(names))


def test_metadata_contract():
    allowed = {"candidate", "testing", "validated", "oos_retained", "deferred", "retired"}
    for item in list_models():
        s = item.spec
        assert s.name and s.category and s.source and s.rationale
        assert s.lookahead_policy == "strictly_causal"
        assert "open" in s.required_columns and "close" in s.required_columns
        assert s.parameter_grid
        assert s.status in allowed


def test_parameter_grid_matches_strategy_signature():
    for item in list_models():
        sig = inspect.signature(item.strategy)
        params = sig.parameters
        assert "df" in params, item.spec.name
        assert not any(
            p.kind == inspect.Parameter.VAR_POSITIONAL
            for p in params.values()
        ), item.spec.name
        if not any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values()):
            unknown = set(item.spec.parameter_grid) - set(params)
            assert not unknown, (item.spec.name, sorted(unknown))
        for key, values in item.spec.parameter_grid.items():
            assert values, (item.spec.name, key)


def test_all_models_return_contract():
    frame = make_frame()
    for item in list_models():
        first_params = {k: values[0] for k, values in item.spec.parameter_grid.items()}
        out = item.strategy(frame, **first_params)
        assert isinstance(out, pd.DataFrame), item.spec.name
        assert out.index.equals(frame.index), item.spec.name
        assert {"signal", "stop", "target"}.issubset(out.columns), item.spec.name
        assert out.index.is_monotonic_increasing and not out.index.has_duplicates
        signals = pd.Series(out["signal"]).dropna().astype(int).unique()
        assert set(signals).issubset({-1,0,1}), item.spec.name


def test_no_future_sensitivity():
    frame = make_frame()
    cutoff = 210
    changed = frame.copy()
    for col in ("open", "high", "low", "close"):
        changed.iloc[cutoff:, changed.columns.get_loc(col)] *= 7
    changed.iloc[cutoff:, changed.columns.get_loc("volume")] *= 9

    for item in list_models():
        params = {k: values[0] for k, values in item.spec.parameter_grid.items()}
        a = item.strategy(frame, **params)
        b = item.strategy(changed, **params)
        for col in ("signal", "stop", "target"):
            left = a[col].iloc[:cutoff]
            right = b[col].iloc[:cutoff]
            pd.testing.assert_series_equal(
                left, right, check_names=False,
                obj=item.spec.name + ":" + col,
            )


def main():
    setup()
    test_count_and_unique_names()
    test_metadata_contract()
    test_parameter_grid_matches_strategy_signature()
    test_all_models_return_contract()
    test_no_future_sensitivity()
    print("PHASE2_3_5_MODEL_POOL_V1_1_TEST_OK")


if __name__ == "__main__":
    main()
