from __future__ import annotations
from quantbot.research.walk_forward_execution import *
def main():
 fold=WalkForwardFold("f1","a","b","c","d","e","f"); request=FrozenOOSExecutionRequest("freeze","plan","task","model","BTC","grid",fold)
 assert len(fold.identity())==64 and WalkForwardState("r",status="INTERRUPTED").resume().status=="RUNNING"
 try: request.authorize()
 except PermissionError:pass
 else:raise AssertionError("oos fold authorized")
 print("WALK_FORWARD_LOCKED_SYNTHETIC_TEST_OK")
if __name__=="__main__":main()
