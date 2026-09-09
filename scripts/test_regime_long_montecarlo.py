from __future__ import annotations
import pandas as pd
from quantbot.research.regime_framework import classify_point_in_time
from quantbot.research.long_horizon import LongHorizonCheckpoint, LongHorizonState, LongHorizonProtocol
from quantbot.research.monte_carlo_protocol import MonteCarloProtocol, SimulationRequest, DeterministicSyntheticResampler, run_tiny_synthetic
def main():
    index=pd.date_range("2025-01-01",periods=120,freq="h",tz="UTC"); frame=pd.DataFrame({"high":range(101,221),"low":range(99,219),"close":range(100,220),"volume":[100]*120},index=index)
    left=classify_point_in_time(frame); changed=frame.copy(); changed.iloc[-1,changed.columns.get_loc("close")]=999999; right=classify_point_in_time(changed)
    assert left.iloc[:-1].equals(right.iloc[:-1])
    checkpoint=LongHorizonCheckpoint(180,1,LongHorizonState.RUNNING).advance(10); assert checkpoint.progress_days==10 and LongHorizonProtocol().validate()
    for bad in (lambda:LongHorizonCheckpoint(181,1,LongHorizonState.RUNNING),lambda:LongHorizonCheckpoint(180,0,LongHorizonState.RUNNING),lambda:LongHorizonCheckpoint(180,1,LongHorizonState.COMPLETED,10),lambda:LongHorizonCheckpoint(180,1,LongHorizonState.RUNNING,error="x")):
        try:bad()
        except ValueError:pass
        else:raise AssertionError("long_horizon_checkpoint_bypass")
    request=SimulationRequest(MonteCarloProtocol(2),3,"synthetic"); assert run_tiny_synthetic(request,(1.,2.),DeterministicSyntheticResampler()).synthetic
    try: run_tiny_synthetic(SimulationRequest(MonteCarloProtocol(2,status="OPEN"),3,"synthetic"),(1.,2.),DeterministicSyntheticResampler())
    except ValueError: pass
    else: raise AssertionError("mc_state_bypass")
    try: MonteCarloProtocol(9).execute()
    except PermissionError: pass
    else: raise AssertionError("real mc opened")
    print("REGIME_LONG_MONTE_CARLO_SYNTHETIC_TEST_OK")
if __name__=="__main__": main()
