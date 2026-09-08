#!/usr/bin/env python3
"""Synthetic-only contracts for P0-P3 closed doors.

No loader, evaluator, real result, OOS window, MC execution, or exchange
connection is imported or called by this test.
"""
from __future__ import annotations

import copy
import tempfile

from quantbot.backtest.costs import CostModel
from quantbot.backtest.stress_framework import DEFAULT_STRESS_SCENARIOS
from quantbot.execution.exchange_abstraction import ExchangeOrder, LiveExchangeAdapter, PaperExchangeAdapter
from quantbot.execution.live_authorization import LiveAuthorizationState
from quantbot.execution.runtime_supervisor import PaperRuntimeCheckpoint, checkpoint_payload
from quantbot.portfolio.research_controls import PortfolioResearchRequest, fixed_weight_vector, validate_portfolio_request
from quantbot.research.artifact_store import ArtifactError, read_verified_json
from quantbot.research.diagnostics import summarize_stability
from quantbot.research.long_horizon import LongHorizonProtocol
from quantbot.research.monte_carlo_protocol import MonteCarloProtocol
from quantbot.research.oos_protocol import OOSOpeningProtocol
from quantbot.research.result_package import build_result_package, validate_result_package, write_result_package
from quantbot.risk.failure_supervisor import supervise_failures


def expect_blocked(fn, marker):
    try:
        fn()
    except (PermissionError, ValueError, ArtifactError):
        return
    raise AssertionError(marker)


def main():
    binding = {"research_freeze_identity": "f" * 64, "research_plan_identity": "p" * 64,
               "candidate_universe_hash": "c" * 64, "dataset_id": "synthetic", "boundary_identity_hash": "b" * 64,
               "counts": {"model_symbol_cells": 2}, "oos_status": "SEALED", "oos_authorization": "NOT_AUTHORIZED"}
    tasks = [{"task_identity": "0" * 63 + str(index), "status": "COMPLETED", "actual_train_evaluations": 2,
              "actual_validation_evaluations": 1, "model_id": f"m{index}"} for index in range(2)]
    package = build_result_package(run_id="r" * 64, execution_binding=binding, task_artifacts=tasks,
                                   recovery_state={"revision": 1}, source_git_commit="a" * 40)
    assert validate_result_package(package, binding=binding)
    tampered = copy.deepcopy(package); tampered["tasks"].pop();
    expect_blocked(lambda: validate_result_package(tampered, binding=binding), "truncation accepted")
    with tempfile.TemporaryDirectory() as directory:
        path = write_result_package(directory, package)
        assert read_verified_json(path)["artifact_identity"] == package["artifact_identity"]
        expect_blocked(lambda: write_result_package(directory, package), "immutable replacement accepted")

    summary = summarize_stability(tasks)
    assert summary["oos_read"] is False
    assert DEFAULT_STRESS_SCENARIOS[1].stressed_cost_model(CostModel()).slippage_bps > CostModel().slippage_bps
    assert validate_portfolio_request(PortfolioResearchRequest(("recipe",)), ("recipe",))
    assert fixed_weight_vector({"a": 1, "b": 1}) == {"a": 0.35, "b": 0.35}
    assert supervise_failures(("FAILED", "FAILED", "FAILED")).allowed is False

    expect_blocked(lambda: OOSOpeningProtocol("f", "p").request_window("OOS"), "oos opened")
    expect_blocked(lambda: MonteCarloProtocol(100).execute(), "mc opened")
    expect_blocked(lambda: LongHorizonProtocol().require_authorization(), "long horizon opened")
    assert LongHorizonProtocol().validate()
    assert PaperExchangeAdapter().submit(ExchangeOrder("BTCUSDT", "buy", 1))["status"] == "PAPER_ACCEPTED"
    expect_blocked(LiveExchangeAdapter, "live adapter opened")
    expect_blocked(lambda: LiveAuthorizationState().require_live(), "live authorization opened")
    checkpoint = checkpoint_payload(PaperRuntimeCheckpoint("ledger", 1), provenance={"oos_authorized": False})
    assert checkpoint["status"] == "PAPER_ONLY" and checkpoint["checkpoint_identity"]
    print("BACKHALF_LOCKED_CONTRACTS_SYNTHETIC_TEST_OK")


if __name__ == "__main__":
    main()
