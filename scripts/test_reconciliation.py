from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from quantbot.execution import PaperLedger,PaperOrderRequest,reconcile
def main():
 a=PaperLedger();b=PaperLedger();o=PaperOrderRequest("paper-a","BTCUSDT","buy",1,100,98,104,"x")
 a.request(o);b.request(o);assert reconcile(a.orders,b.orders).clean
 b.fill("paper-a",100.1);r=reconcile(a.orders,b.orders);assert r.status_mismatches==("paper-a",)
 print("RECONCILIATION_SYNTHETIC_TEST_OK")
if __name__=="__main__":main()
