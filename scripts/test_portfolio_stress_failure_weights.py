from __future__ import annotations
from quantbot.portfolio.weight_engine import WeightCandidate, WeightPolicy, compute_weights
from quantbot.backtest.stress_framework import ADVANCED_STRESS_SCENARIOS, build_stress_artifact
from quantbot.backtest.costs import CostModel
from quantbot.risk.failure_supervisor import *
def reject(fn):
 try: fn()
 except ValueError: return
 raise AssertionError("invalid accepted")
def main():
    rows=(WeightCandidate("a","f1","BTC",2),WeightCandidate("b","f2","ETH",1))
    assert abs(sum(compute_weights(rows,WeightPolicy(method="risk",maximum_weight=.8,family_cap=.8,symbol_cap=.8)).values())-1)<1e-12
    reject(lambda:compute_weights((rows[0],rows[0])))
    reject(lambda:compute_weights(rows,WeightPolicy(method="fixed"),fixed={"a":2,"b":1}))
    assert build_stress_artifact(ADVANCED_STRESS_SCENARIOS[-1],CostModel(),input_identity="x")["oos_read"] is False
    assert decide(FailureEvent("e",FailureCategory.LEDGER,Severity.RETRYABLE,"x",1)).terminal
    print("PORTFOLIO_STRESS_FAILURE_WEIGHT_SYNTHETIC_TEST_OK")
if __name__=="__main__": main()
