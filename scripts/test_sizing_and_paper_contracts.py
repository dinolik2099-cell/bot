"""Synthetic-only test for the Risk -> sizing -> paper-request path."""
from pathlib import Path
import sys
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from quantbot.backtest import CostModel
from quantbot.execution import build_paper_order
from quantbot.portfolio import select_candidates
from quantbot.risk import approve_candidate, exposure_from_plan, size_approved_candidate
from quantbot.signals import SignalIntent


def main() -> None:
    intent = SignalIntent("BTCUSDT", pd.Timestamp("2025-01-01T00:00:00Z"), "buy", "m1", "trend", .5, .5, 98.0, 104.0, "requires_risk_approval")
    candidate = select_candidates((intent,), max_candidates=1)[0]
    decision = approve_candidate(candidate, reference_price=100.0, equity=10_000.0, positions=())
    plan = size_approved_candidate(candidate, decision, reference_price=100.0, cost_model=CostModel(fee_rate=.0004, slippage_bps=2.0))
    order = build_paper_order(plan)
    assert order.mode == "paper_only" and order.client_order_id.startswith("paper-") and order.model_family == "trend"
    assert plan.expected_execution_price > plan.reference_price and plan.estimated_entry_fee > 0
    assert plan.notional <= decision.notional + 1e-9
    assert plan.quantity <= decision.quantity + 1e-12
    assert plan.risk_amount <= decision.risk_amount + 1e-9
    assert plan.quantity < decision.quantity
    exposure=exposure_from_plan(plan)
    assert exposure.model_family == "trend" and exposure.risk_amount == plan.risk_amount
    assert exposure.notional == plan.notional
    try:
        size_approved_candidate(candidate, decision.__class__(False, "blocked"), reference_price=100.0, cost_model=CostModel())
    except ValueError:
        pass
    else:
        raise AssertionError("rejected risk decision must not be sizable")
    print("SIZING_AND_PAPER_CONTRACTS_SYNTHETIC_TEST_OK")


if __name__ == "__main__":
    main()
