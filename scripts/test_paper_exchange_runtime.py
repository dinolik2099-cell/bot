from __future__ import annotations
import tempfile
from pathlib import Path
from quantbot.execution.exchange_abstraction import PaperExchangeAdapter, ExchangeOrder, LiveExchangeAdapter
from quantbot.execution.runtime_supervisor import RuntimeSupervisorState, write_checkpoint_new, load_checkpoint
def main():
    exchange=PaperExchangeAdapter(); exchange.market_event("BTCUSDT",100); response=exchange.submit(ExchangeOrder("BTCUSDT","buy",2,"o1")); exchange.fill("o1",1,100); assert exchange.reconcile()["orders"][0]["status"]=="PARTIAL"
    try: exchange.submit(ExchangeOrder("BTCUSDT","buy",1,"o1"))
    except ValueError: pass
    else: raise AssertionError("duplicate accepted")
    try: LiveExchangeAdapter()
    except PermissionError: pass
    else: raise AssertionError("live opened")
    with tempfile.TemporaryDirectory() as d:
      path=write_checkpoint_new(Path(d)/"state.json",RuntimeSupervisorState("s",1,2),provenance={"run":"x"}); assert load_checkpoint(path)["heartbeat"]==2
      try: write_checkpoint_new(path,RuntimeSupervisorState("s",1),provenance={})
      except ValueError: pass
      else: raise AssertionError("checkpoint overwritten")
    print("PAPER_EXCHANGE_RUNTIME_SYNTHETIC_TEST_OK")
if __name__=="__main__": main()
