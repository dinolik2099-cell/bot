from __future__ import annotations
import tempfile
from pathlib import Path
from quantbot.execution.paper import PaperOrderRequest
from quantbot.execution.paper_ledger import PaperLedger
from quantbot.execution.persistent_paper_runtime import *
def main():
 ledger=PaperLedger();order=PaperOrderRequest("id","BTC","buy",1,100,90,None,"tag","family");ledger.request(order); state=snapshot_state("s","r",1,ledger)
 with tempfile.TemporaryDirectory() as d:
  path=save_new_state(Path(d)/"paper.json",state); loaded=load_state(path); restored=ledger_from_state(loaded); assert startup_reconcile(loaded,restored.orders)
  assert restored.request(order).request==order
  try: restored.request(PaperOrderRequest("id","BTC","sell",1,100,90,None,"tag","family"))
  except ValueError:pass
  else:raise AssertionError("restart duplicate bypass")
 print("PERSISTENT_PAPER_RUNTIME_SYNTHETIC_TEST_OK")
if __name__=="__main__":main()
