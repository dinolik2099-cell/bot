from pathlib import Path
import sys,pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from quantbot.execution.paper_runtime import run_once
from quantbot.signals import SignalIntent
def main():
 i=SignalIntent("BTCUSDT",pd.Timestamp("2025-01-01T00:00:00Z"),"buy","m","trend",.5,.5,98,104,"requires_risk_approval")
 r=run_once((i,),{"BTCUSDT":100},10000)
 assert len(r.requested_order_ids)==1 and r.ledger.orders[0].status=="requested"
 print("PAPER_RUNTIME_SYNTHETIC_TEST_OK")
if __name__=="__main__":main()
