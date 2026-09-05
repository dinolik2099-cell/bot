"""Synthetic end-to-end regression for the fail-closed paper decision chain."""
from pathlib import Path
import sys
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from quantbot.execution.paper_runtime import run_once
from quantbot.execution import RuntimeConfig
from quantbot.risk import PositionExposure, RiskPolicy, RiskSnapshot
from quantbot.signals import SignalIntent
from quantbot.research.provenance import RunProvenance

def intent(symbol,model,family,score):
 return SignalIntent(symbol,pd.Timestamp("2025-01-01T00:00:00Z"),"buy",model,family,abs(score),score,98,104,"requires_risk_approval")

def main():
 accepted=intent("BTCUSDT","trend_a","trend",.7)
 missing_price=intent("ETHUSDT","break_a","breakout",.6)
 provenance=RunProvenance("synthetic","test-v1","VALIDATION")
 snapshot=RiskSnapshot(10_000,10_000,10_000,10_000)
 result=run_once((accepted,missing_price),{"BTCUSDT":100},10_000,provenance,snapshot)
 assert len(result.requested_order_ids)==1
 assert result.ledger.orders[0].status=="requested"
 second=run_once((accepted,),{"BTCUSDT":100},10_000,provenance,snapshot,positions=result.new_exposures)
 assert second.rejected[0][1]=="symbol_already_exposed"
 assert len(result.rejected)==1 and result.rejected[0][1]=="missing_reference_price"
 events=[e.event_type for e in result.audit.events]
 assert events==["signal_created","portfolio_selected","risk_approved","paper_requested","signal_created","portfolio_selected","risk_rejected"]
 assert result.audit.events[0].payload["provenance"]["source_window"]=="VALIDATION"
 blocked=run_once((accepted,),{"BTCUSDT":100},10_000,provenance,snapshot,positions=(PositionExposure("BTCUSDT","buy",50,1000),))
 assert blocked.rejected[0][1]=="symbol_already_exposed"
 # Regression: approvals in one run must consume risk capacity immediately.
 same_run_a=intent("BTCUSDT","trend_same_run","trend",.8)
 same_run_b=intent("ETHUSDT","break_same_run","breakout",.7)
 tight_policy=RiskPolicy(
     risk_per_entry=.01,
     max_total_risk=.015,
     max_same_direction_risk=1.0,
     max_same_family_risk=1.0,
     max_positions=4,
     max_position_fraction=1.0,
     max_total_capital_fraction=1.0,
 )
 accumulated=run_once(
     (same_run_a,same_run_b),
     {"BTCUSDT":100,"ETHUSDT":100},
     10_000,
     provenance,
     snapshot,
     policy=tight_policy,
 )
 assert len(accumulated.requested_order_ids)==1
 assert len(accumulated.new_exposures)==1
 assert len(accumulated.rejected)==1
 assert accumulated.rejected[0][1]=="max_total_risk"

 halted=run_once((accepted,),{"BTCUSDT":100},10_000,provenance,RiskSnapshot(9_600,10_000,10_000,10_000))
 assert not halted.requested_order_ids and not halted.ledger.orders
 assert halted.rejected[0][1]=="max_daily_loss"
 assert halted.audit.events[-1].payload["emergency_stop"] is True
 try: run_once((accepted,),{"BTCUSDT":100},10_000,provenance,snapshot,runtime_config=RuntimeConfig(live_enabled=True))
 except PermissionError: pass
 else: raise AssertionError("live mode escaped fail-closed protection")
 print("SAFE_EXECUTION_CHAIN_SYNTHETIC_TEST_OK")
if __name__=="__main__":main()
