"""Declarative cost/stress scenarios; no backtest runner is included."""
from __future__ import annotations
from dataclasses import dataclass
from .costs import CostModel

@dataclass(frozen=True)
class StressScenario:
    name: str
    cost_model: CostModel
    latency_bars: int = 0
    liquidity_multiplier: float = 1.0
    volatility_multiplier: float = 1.0

def standard_scenarios(baseline: CostModel = CostModel()) -> tuple[StressScenario, ...]:
    """Return immutable scenario metadata. Formal execution remains separately gated."""
    return (
        StressScenario("baseline", baseline),
        StressScenario("elevated_cost", CostModel(baseline.fee_rate * 1.5, baseline.slippage_bps * 2, baseline.funding_rate_per_8h)),
        StressScenario("latency_liquidity", CostModel(baseline.fee_rate, baseline.slippage_bps * 3, baseline.funding_rate_per_8h), latency_bars=1, liquidity_multiplier=.5, volatility_multiplier=1.25),
    )
