"""Synthetic-only tests for candidate selection and non-executable risk approval."""
from pathlib import Path
import sys
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from quantbot.portfolio import select_candidates
from quantbot.risk import PositionExposure, approve_candidate
from quantbot.signals import SignalIntent


def intent(symbol, model, family, score, side="buy"):
    return SignalIntent(symbol, pd.Timestamp("2025-01-01T00:00:00Z"), side, model, family, abs(score), score, 98.0 if side == "buy" else 102.0, 104.0 if side == "buy" else 96.0, "requires_risk_approval")


def main() -> None:
    candidates = select_candidates((intent("BTCUSDT", "a", "trend", .5), intent("BTCUSDT", "b", "breakout", .7), intent("ETHUSDT", "c", "trend", .6)), max_candidates=3)
    assert [item.intent.model for item in candidates] == ["b", "c"]
    approved = approve_candidate(candidates[0], reference_price=100.0, equity=10_000.0, positions=())
    assert approved.accepted and approved.quantity > 0 and approved.risk_amount <= 100.0 + 1e-9
    blocked = approve_candidate(candidates[0], reference_price=100.0, equity=10_000.0, positions=(PositionExposure("BTCUSDT", "buy", 50.0, 1000.0),))
    assert not blocked.accepted and blocked.reason == "symbol_already_exposed"
    print("PORTFOLIO_AND_RISK_CONTRACTS_SYNTHETIC_TEST_OK")


if __name__ == "__main__":
    main()
