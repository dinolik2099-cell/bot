from __future__ import annotations
from dataclasses import asdict
from quantbot.research.walk_forward_execution import *
from quantbot.research.artifact_store import seal
def main():
 fold=WalkForwardFold("f1","a","b","c","d","e","f"); request=FrozenOOSExecutionRequest("freeze","plan","task","model","BTC","grid",fold)
 assert len(fold.identity())==64 and WalkForwardState("r",status="INTERRUPTED").resume().status=="RUNNING"
 try: request.authorize()
 except PermissionError:pass
 else:raise AssertionError("oos fold authorized")
 artifact=seal({"schema_version":"quantbot-walk-forward-fold-v1","request":asdict(request),"result":{"synthetic":True}})
 assert validate_fold_result(artifact,request=request)
 tampered=seal({"schema_version":"quantbot-walk-forward-fold-v1","request":{**asdict(request),"symbol":"ETH"},"result":{"synthetic":True}})
 try:validate_fold_result(tampered,request=request)
 except ValueError:pass
 else:raise AssertionError("forged_fold_request_accepted")
 print("WALK_FORWARD_LOCKED_SYNTHETIC_TEST_OK")
if __name__=="__main__":main()
