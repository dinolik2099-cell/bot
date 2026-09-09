from __future__ import annotations
from quantbot.research.authorization import Capability
from quantbot.research.readiness_gates import *

def blocked(fn):
    try: fn()
    except (ValueError, PermissionError): return
    raise AssertionError("fail_open")

def main():
    freeze="a"*64; plan="b"*64
    evidence=ReadinessEvidence(freeze,plan,"c"*64,"d"*64,{name:"e"*64 for name in REQUIRED_PRE_OOS_EVIDENCE}).artifact()
    assert validate_readiness_evidence(evidence,expected_freeze_identity=freeze,expected_plan_identity=plan)
    assert pre_oos_decision(evidence,expected_freeze_identity=freeze,expected_plan_identity=plan)==ReadinessDecision.READY_BUT_NOT_AUTHORIZED
    missing=seal({**{key:value for key,value in evidence.items() if key!='artifact_identity'},"artifacts":{}})
    assert pre_oos_decision(missing,expected_freeze_identity=freeze,expected_plan_identity=plan)==ReadinessDecision.RESEARCH_INCOMPLETE
    tampered=seal({**{key:value for key,value in evidence.items() if key!='artifact_identity'},"oos_authorization":"AUTHORIZED"})
    assert pre_oos_decision(tampered,expected_freeze_identity=freeze,expected_plan_identity=plan)==ReadinessDecision.RESEARCH_INCOMPLETE
    blocked(lambda:require_paper_or_live(evidence,capability=Capability.PAPER_RUNTIME,expected_freeze_identity=freeze,expected_plan_identity=plan))
    blocked(lambda:require_paper_or_live(evidence,capability=Capability.LIVE,expected_freeze_identity=freeze,expected_plan_identity=plan))
    print("READINESS_GATES_SYNTHETIC_TEST_OK")
    print("OOS_READS=0")
    print("PAPER_STARTS=0")
    print("LIVE_ORDERS=0")

if __name__=="__main__": main()
