"""Synthetic end-to-end regression for the fail-closed paper decision chain."""
from pathlib import Path
import sys
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from quantbot.execution.paper_runtime import run_once
from quantbot.execution import RuntimeConfig
from quantbot.risk import PositionExposure
from quantbot.signals import SignalIntent
from quantbot.research.provenance import RunProvenance

def intent(symbol,model,family,score):
 return SignalIntent(symbol,pd.Timestamp("2025-01-01T00:00:00Z"),"buy",model,family,abs(score),score,98,104,"requires_risk_approval")

def main():
 accepted=intent("BTCUSDT","trend_a","trend",.7)
 missing_price=intent("ETHUSDT","break_a","breakout",.6)
 provenance=RunProvenance("synthetic","test-v1","VALIDATION")
 result=run_once((accepted,missing_price),{"BTCUSDT":100},10_000,provenance)
 assert len(result.requested_order_ids)==1
 assert result.ledger.orders[0].status=="requested"
 assert len(result.rejected)==1 and result.rejected[0][1]=="missing_reference_price"
 events=[e.event_type for e in result.audit.events]
 assert events==["signal_created","portfolio_selected","risk_approved","paper_requested","signal_created","portfolio_selected","risk_rejected"]
 assert result.audit.events[0].payload["provenance"]["source_window"]=="VALIDATION"
 blocked=run_once((accepted,),{"BTCUSDT":100},10_000,provenance,positions=(PositionExposure("BTCUSDT","buy",50,1000),))
 assert blocked.rejected[0][1]=="symbol_already_exposed"
 try: run_once((accepted,),{"BTCUSDT":100},10_000,provenance,runtime_config=RuntimeConfig(live_enabled=True))
 except PermissionError: pass
 else: raise AssertionError("live mode escaped fail-closed protection")
 print("SAFE_EXECUTION_CHAIN_SYNTHETIC_TEST_OK")
if __name__=="__main__":main()
