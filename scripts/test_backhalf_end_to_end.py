"""Synthetic-only closed-door integration from evidence through paper runtime."""
from __future__ import annotations
from quantbot.research.result_package import build_result_package
from quantbot.research.diagnostics import build_diagnostics, validate_diagnostics
from quantbot.research.oos_protocol import OOSOpeningProtocol, PreOOSChecklist
from quantbot.research.monte_carlo_protocol import MonteCarloProtocol
from quantbot.portfolio.weight_engine import WeightCandidate, WeightPolicy, compute_weights
from quantbot.backtest.stress_framework import build_stress_artifact, DEFAULT_STRESS_SCENARIOS
from quantbot.backtest.costs import CostModel
from quantbot.execution.exchange_abstraction import FakeExchangeAdapter, ExchangeOrder
from quantbot.execution.runtime_supervisor import PaperRuntimeCheckpoint, checkpoint_payload

def main():
    binding={"research_freeze_identity":"f"*64,"research_plan_identity":"p"*64,"candidate_universe_hash":"c"*64,"dataset_id":"synthetic","boundary_identity_hash":"b"*64,"counts":{"model_symbol_cells":2},"oos_status":"SEALED","oos_authorization":"NOT_AUTHORIZED"}
    tasks=[{"task_identity":"1"*64,"status":"COMPLETED","actual_train_evaluations":2,"actual_validation_evaluations":1,"model_id":"m1","symbol":"BTC","family":"trend","train":[{"params":{"x":1}}],"validation":[{"total_return":.1,"profit_factor":1.2,"max_drawdown":.02,"trades":12,"params":{"x":1}}]},
           {"task_identity":"2"*64,"status":"COMPLETED","actual_train_evaluations":2,"actual_validation_evaluations":1,"model_id":"m2","symbol":"ETH","family":"mean","train":[{"params":{"x":1}},{"params":{"x":2}}],"validation":[{"total_return":-.01,"profit_factor":.9,"max_drawdown":.03,"trades":11,"params":{"x":1}}]}]
    package=build_result_package(run_id="r"*64,execution_binding=binding,task_artifacts=tasks,recovery_state={"revision":1},source_git_commit="g"*40)
    diagnostics=build_diagnostics(package); assert validate_diagnostics(diagnostics,package)
    checklist=PreOOSChecklist("f"*64,"p"*64,"m","synthetic","b","g",True,True,True,True)
    try: OOSOpeningProtocol("f"*64,"p"*64).request_window("OOS",checklist)
    except PermissionError: pass
    else: raise AssertionError("real oos allowed")
    try: MonteCarloProtocol(100).execute()
    except PermissionError: pass
    else: raise AssertionError("real mc allowed")
    weights=compute_weights((WeightCandidate("m1","trend","BTC"),WeightCandidate("m2","mean","ETH")),WeightPolicy(maximum_weight=.6,family_cap=.6,symbol_cap=.6)); assert sum(weights.values())==1
    stress=build_stress_artifact(DEFAULT_STRESS_SCENARIOS[1],CostModel(),input_identity=package["artifact_identity"]); assert stress["synthetic"]
    exchange=FakeExchangeAdapter(); assert exchange.submit(ExchangeOrder("BTC","buy",1,"synthetic-order"))["status"]=="PAPER_ACCEPTED"; assert checkpoint_payload(PaperRuntimeCheckpoint("ledger",1),provenance={"package":package["artifact_identity"]})
    print("BACKHALF_END_TO_END_SYNTHETIC_TEST_OK")
if __name__=="__main__": main()
