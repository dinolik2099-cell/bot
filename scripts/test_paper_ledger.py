"""Synthetic-only tests for the ephemeral paper ledger."""
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from quantbot.execution import PaperLedger, PaperOrderRequest

def main():
    order=PaperOrderRequest("paper-test","BTCUSDT","buy",1.0,100.0,98.0,104.0,"synthetic")
    ledger=PaperLedger(); assert ledger.request(order).status=="requested"
    assert ledger.request(order).status=="requested" and len(ledger.orders)==1
    assert ledger.fill("paper-test",100.2).status=="filled"
    try: ledger.reject("paper-test","late")
    except ValueError: pass
    else: raise AssertionError("terminal state must not transition")
    print("PAPER_LEDGER_SYNTHETIC_TEST_OK")
if __name__=="__main__":main()
