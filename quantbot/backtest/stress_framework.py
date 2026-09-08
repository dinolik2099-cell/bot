"""P1/P2 declarative CostModel stress specifications; no market-data access."""
from __future__ import annotations

from dataclasses import dataclass
from quantbot.backtest.costs import CostModel


@dataclass(frozen=True)
class CostStressScenario:
    name: str
    fee_multiplier: float = 1.0
    slippage_multiplier: float = 1.0
    funding_multiplier: float = 1.0

    def stressed_cost_model(self, base: CostModel) -> CostModel:
        if min(self.fee_multiplier, self.slippage_multiplier, self.funding_multiplier) < 1:
            raise ValueError("stress_must_not_reduce_costs")
        return CostModel(fee_rate=base.fee_rate * self.fee_multiplier,
                         slippage_bps=base.slippage_bps * self.slippage_multiplier,
                         funding_rate_per_8h=base.funding_rate_per_8h * self.funding_multiplier)


DEFAULT_STRESS_SCENARIOS = (CostStressScenario("BASE"), CostStressScenario("HIGH_COST", 1.5, 2.0, 1.5),
                            CostStressScenario("SEVERE_COST", 2.0, 3.0, 2.0))
