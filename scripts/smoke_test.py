"""Minimal synthetic smoke test for the Canonical Backtest Engine only."""

from pathlib import Path
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from quantbot.backtest.costs import CostModel
from quantbot.backtest.engine_v2 import BacktestEngine
from quantbot.research.evaluation import make_strategy_adapter
from quantbot.strategies.models import trend_breakout


def main() -> None:
    idx = pd.date_range("2024-01-01", periods=1000, freq="h", tz="UTC")
    rng = np.random.default_rng(1)
    close = 100 * np.exp(np.cumsum(rng.normal(0.0001, 0.01, len(idx))))
    frame = pd.DataFrame(
        {
            "open": close * (1 + rng.normal(0, 0.001, len(idx))),
            "high": close * 1.005,
            "low": close * 0.995,
            "close": close,
            "volume": rng.uniform(1, 10, len(idx)),
        },
        index=idx,
    )

    adapter = make_strategy_adapter(
        trend_breakout,
        full_frame=frame,
        params={"lookback": 40, "stop_atr": 2.0, "reward_r": 3.0},
        risk_fraction=0.005,
        position_fraction=0.30,
        tag="canonical-smoke",
    )
    result = BacktestEngine(
        initial_equity=10_000.0,
        cost_model=CostModel(fee_rate=0.0004, slippage_bps=2.0),
        max_position_fraction=0.30,
        max_risk_fraction=0.005,
    ).run({"SMOKEUSDT": frame}, {"SMOKEUSDT": adapter})

    assert result.initial_equity == 10_000.0
    assert result.final_equity > 0
    assert result.equity_curve.index.is_monotonic_increasing
    print(result.metrics())
    print("CANONICAL_SMOKE_OK")


if __name__ == "__main__":
    main()
