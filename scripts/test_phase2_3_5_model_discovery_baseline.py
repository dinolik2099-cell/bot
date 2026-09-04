from __future__ import annotations

import inspect
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from quantbot.backtest.costs import CostModel
from quantbot.backtest.engine_v2 import BacktestEngine
from quantbot.research.evaluation import evaluate_strategy
from quantbot.research.model_registry import list_models, register_existing_models, validate_registry
from quantbot.strategies.model_pool import register_model_pool
from scripts.run_phase2_3_5_model_discovery_baseline import _default_params, _fast_backtest


def make_frame(n=1600):
    idx = pd.date_range("2025-01-01", periods=n, freq="1h", tz="UTC")
    t = np.arange(n, dtype=float)
    close = 100 + 0.02 * t + 2 * np.sin(t / 13) + 0.8 * np.sin(t / 37)
    open_ = close + 0.2 * np.sin(t / 5)
    high = np.maximum(open_, close) + 0.7 + 0.1 * np.sin(t / 17) ** 2
    low = np.minimum(open_, close) - 0.7 - 0.1 * np.cos(t / 19) ** 2
    volume = 1000 + 100 * np.sin(t / 11) + (t % 17) * 5
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "volume": volume}, index=idx)


def main():
    register_existing_models(); register_model_pool(); validate_registry()
    models = list_models()
    assert len(models) == 36
    names = [m.spec.name for m in models]
    assert len(names) == len(set(names))

    frame = make_frame()
    for item in models:
        params = _default_params(item.strategy)
        out = item.strategy(frame, **params)
        assert len(out) == len(frame)
        assert out.index.equals(frame.index)
        assert {"signal", "stop", "target"}.issubset(out.columns)
        vals = pd.Series(out["signal"]).dropna().astype(int).unique()
        assert set(vals).issubset({-1, 0, 1})

    # Numerical equivalence against the canonical BacktestEngine on a real strategy frame.
    item = next(x for x in models if x.spec.name == "trend_breakout")
    params = _default_params(item.strategy)
    canonical = evaluate_strategy(
        symbol="BTCUSDT", window="TEST", frame=frame,
        strategy=item.strategy,
        engine=BacktestEngine(
            10_000.0,
            CostModel(fee_rate=0.0004, slippage_bps=2.0, funding_rate_per_8h=0.0),
            max_position_fraction=1.0, max_risk_fraction=0.01, max_positions=1,
        ),
        params=params, risk_fraction=0.01, position_fraction=1.0, tag="equivalence",
    )
    fast_metrics, _ = _fast_backtest(frame, item.strategy, params, "BTCUSDT", None, "TEST", "equivalence")
    cm = canonical.backtest.metrics()
    for key in ("final_equity", "total_return", "max_drawdown", "trades", "win_rate", "profit_factor", "rejected_signals"):
        a, b = float(cm[key]), float(fast_metrics[key])
        if np.isinf(a) or np.isinf(b):
            assert np.isinf(a) and np.isinf(b) and (a > 0) == (b > 0), (key, a, b)
        else:
            assert abs(a - b) < 1e-10, (key, a, b)

    print("36个模型注册与输出契约：通过")
    print("快速回测与BacktestEngine数值等价性：通过")
    print("PHASE2_3_5_MODEL_DISCOVERY_BASELINE_TEST_OK")


if __name__ == "__main__":
    main()
