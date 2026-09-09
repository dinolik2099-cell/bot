from __future__ import annotations
from quantbot.portfolio.weight_engine import WeightCandidate, WeightPolicy, compute_weights
from quantbot.backtest.stress_framework import ADVANCED_STRESS_SCENARIOS, build_stress_artifact, validate_stress_artifact
from quantbot.backtest.costs import CostModel
from quantbot.risk.failure_supervisor import *
from quantbot.portfolio.research_artifact import PortfolioCandidate, build_portfolio_artifact, validate_portfolio_artifact
from quantbot.research.artifact_store import seal
def reject(fn):
 try: fn()
 except ValueError: return
 raise AssertionError("invalid accepted")
def main():
    rows=(WeightCandidate("a","f1","BTC",2),WeightCandidate("b","f2","ETH",1))
    assert abs(sum(compute_weights(rows,WeightPolicy(method="risk",maximum_weight=.8,family_cap=.8,symbol_cap=.8)).values())-1)<1e-12
    reject(lambda:compute_weights((rows[0],rows[0])))
    reject(lambda:compute_weights(rows,WeightPolicy(method="fixed"),fixed={"a":2,"b":1}))
    stress=build_stress_artifact(ADVANCED_STRESS_SCENARIOS[-1],CostModel(),input_identity="x");assert stress["oos_read"] is False and validate_stress_artifact(stress)
    altered={key:value for key,value in stress.items() if key!="artifact_identity"};altered["cost_model"]=dict(altered["cost_model"]);altered["cost_model"]["fee_rate"]=0;reject(lambda:validate_stress_artifact(seal(altered)))
    artifact=build_portfolio_artifact((PortfolioCandidate(rows[0],"a",{"b":.1}),PortfolioCandidate(rows[1],"b",{"a":.1})),WeightPolicy(maximum_weight=.8,family_cap=.8,symbol_cap=.8),input_identity="frozen")
    assert validate_portfolio_artifact(artifact)
    altered={key:value for key,value in artifact.items() if key!="artifact_identity"};altered["weights"]=dict(altered["weights"]);altered["weights"]["a"]=.9;reject(lambda:validate_portfolio_artifact(seal(altered)))
    altered={key:value for key,value in artifact.items() if key!="artifact_identity"};altered["candidates"]=[dict(row) for row in altered["candidates"]];altered["candidates"][1]["candidate"]=dict(altered["candidates"][1]["candidate"]);altered["candidates"][1]["candidate"]["family"]="f1";reject(lambda:validate_portfolio_artifact(seal(altered)))
    altered={key:value for key,value in artifact.items() if key!="artifact_identity"};altered["correlations"]={key:dict(value) for key,value in altered["correlations"].items()};altered["correlations"]["a"]={"unknown":.1};reject(lambda:validate_portfolio_artifact(seal(altered)))
    assert decide(FailureEvent("e",FailureCategory.LEDGER,Severity.RETRYABLE,"x",1)).terminal
    print("PORTFOLIO_STRESS_FAILURE_WEIGHT_SYNTHETIC_TEST_OK")
if __name__=="__main__": main()
