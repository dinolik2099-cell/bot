from __future__ import annotations
import tempfile
from quantbot.execution.runtime_supervisor import *
def main():
 with tempfile.TemporaryDirectory() as root:
  with single_writer(root):
   try:
    with single_writer(root):pass
   except RuntimeError:pass
   else:raise AssertionError("second writer accepted")
  lifecycle=RuntimeLifecycle(RuntimeSupervisorState("s")).startup(reconciled=True).beat();assert lifecycle.state.heartbeat==1;assert lifecycle.emergency_stop().emergency_stopped
  try:RuntimeLifecycle(RuntimeSupervisorState("s")).startup(reconciled=False)
  except RuntimeError:pass
  else:raise AssertionError("bad reconciliation accepted")
 print("RUNTIME_SUPERVISOR_SYNTHETIC_TEST_OK")
if __name__=="__main__":main()
