from pathlib import Path
import sys,pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from quantbot.execution.paper_runtime import run_once
from quantbot.execution import RuntimeConfig
from quantbot.research.provenance import RunProvenance
from quantbot.risk import RiskSnapshot
from quantbot.signals import SignalIntent
def main():
 i=SignalIntent("BTCUSDT",pd.Timestamp("2025-01-01T00:00:00Z"),"buy","m","trend",.5,.5,98,104,"requires_risk_approval")
 p=RunProvenance("synthetic","test-v1","VALIDATION")
 s=RiskSnapshot(10_000,10_000,10_000,10_000)
 r=run_once((i,),{"BTCUSDT":100},10000,p,s)
 assert len(r.requested_order_ids)==1 and r.ledger.orders[0].status=="requested"
 try: run_once((i,),{"BTCUSDT":100},10000,p,s,runtime_config=RuntimeConfig(mode="live"))
 except PermissionError: pass
 else: raise AssertionError("runtime must reject live configuration")
 try: run_once((i,),{"BTCUSDT":100},10000,RunProvenance("locked","v1","OOS"),s)
 except PermissionError: pass
 else: raise AssertionError("runtime must reject OOS provenance")
 print("PAPER_RUNTIME_SYNTHETIC_TEST_OK")
if __name__=="__main__":main()
