"""P1/P2 declarative CostModel stress specifications; no market-data access."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, asdict
from typing import Mapping
from quantbot.backtest.costs import CostModel
from quantbot.research.artifact_store import seal, validate_seal


@dataclass(frozen=True)
class CostStressScenario:
    name: str
    fee_multiplier: float = 1.0
    slippage_multiplier: float = 1.0
    funding_multiplier: float = 1.0
    spread_multiplier: float = 1.0
    liquidity_haircut: float = 0.0
    turnover_multiplier: float = 1.0
    execution_delay_bars: int = 0

    def stressed_cost_model(self, base: CostModel) -> CostModel:
        if min(self.fee_multiplier, self.slippage_multiplier, self.funding_multiplier, self.spread_multiplier, self.turnover_multiplier) < 1 or not 0 <= self.liquidity_haircut < 1 or self.execution_delay_bars < 0:
            raise ValueError("stress_must_not_reduce_costs")
        return CostModel(fee_rate=base.fee_rate * self.fee_multiplier,
                         slippage_bps=base.slippage_bps * self.slippage_multiplier,
                         funding_rate_per_8h=base.funding_rate_per_8h * self.funding_multiplier)


DEFAULT_STRESS_SCENARIOS = (CostStressScenario("BASE"), CostStressScenario("HIGH_COST", 1.5, 2.0, 1.5),
                            CostStressScenario("SEVERE_COST", 2.0, 3.0, 2.0))

ADVANCED_STRESS_SCENARIOS = DEFAULT_STRESS_SCENARIOS + (
    CostStressScenario("FEE_UP", fee_multiplier=2), CostStressScenario("SLIPPAGE_UP", slippage_multiplier=3),
    CostStressScenario("FEE_AND_SLIPPAGE", fee_multiplier=2, slippage_multiplier=3),
    CostStressScenario("SPREAD_WIDENING", spread_multiplier=2), CostStressScenario("LIQUIDITY_HAIRCUT", liquidity_haircut=.5),
    CostStressScenario("TURNOVER_AMPLIFICATION", turnover_multiplier=2), CostStressScenario("ADVERSE_EXECUTION", slippage_multiplier=4, execution_delay_bars=1))

def scenario_identity(scenario: CostStressScenario) -> str:
    return hashlib.sha256(json.dumps(asdict(scenario), sort_keys=True, separators=(",", ":")).encode()).hexdigest()

def build_stress_artifact(scenario: CostStressScenario, base: CostModel, *, input_identity: str, synthetic: bool = True) -> dict[str, object]:
    stressed = scenario.stressed_cost_model(base)
    payload = {"schema_version": "quantbot-cost-stress-v1", "scenario": asdict(scenario), "scenario_identity": scenario_identity(scenario),
               "input_identity": input_identity, "base_cost_model": asdict(base), "cost_model": asdict(stressed), "synthetic": synthetic, "oos_read": False}
    return seal(payload)

def validate_stress_artifact(artifact: Mapping[str, object]) -> bool:
    """Recompute the declared adverse CostModel rather than trusting JSON."""
    validate_seal(artifact)
    if artifact.get("schema_version")!="quantbot-cost-stress-v1" or artifact.get("oos_read") is not False or not isinstance(artifact.get("synthetic"),bool) or not isinstance(artifact.get("input_identity"),str) or not artifact["input_identity"]:
        raise ValueError("stress_artifact_invalid")
    try:
        scenario=CostStressScenario(**dict(artifact["scenario"]))
        base=CostModel(**dict(artifact["base_cost_model"]))
    except (KeyError,TypeError,ValueError) as exc: raise ValueError("stress_artifact_inputs_invalid") from exc
    if artifact.get("scenario_identity")!=scenario_identity(scenario) or artifact.get("cost_model")!=asdict(scenario.stressed_cost_model(base)):
        raise ValueError("stress_artifact_derivation_mismatch")
    return True
