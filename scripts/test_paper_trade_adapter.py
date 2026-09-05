from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from quantbot.analytics import record_paper_trade
from quantbot.execution import PaperOrderRequest
def main():
 o=PaperOrderRequest("p","BTCUSDT","buy",1,100,98,104,"trend_breakout:BTC","趋势")
 r=record_paper_trade(o,entry_time="a",exit_time="b",exit_price=104,exit_reason="take_profit",gross_pnl=4,net_pnl=3.9,fees=.1,slippage_cost=.02,holding_seconds=3600,r_multiple=2,provenance={"source_window":"VALIDATION"})
 assert r.model_family=="趋势" and r.metadata["paper_only"] and r.metadata["source_window"]=="VALIDATION"
 print("PAPER_TRADE_ADAPTER_SYNTHETIC_TEST_OK")
if __name__=="__main__":main()
