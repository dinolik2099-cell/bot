from __future__ import annotations
from quantbot.execution.live_authorization import *
def denied(fn):
 try:fn()
 except PermissionError:return
 raise AssertionError("live transition accepted")
def main():
 state=LiveAuthorizationState(LiveState.DISABLED)
 denied(lambda:state.transition(LiveState.TINY_LIVE_AUTHORIZED,evidence_complete=True,reconciled=True))
 denied(lambda:LiveAuthorizationState().transition(LiveState.SMALL_LIVE_AUTHORIZED,evidence_complete=True,reconciled=True))
 denied(lambda:LiveAuthorizationState().transition(LiveState.LIVE_ELIGIBLE,evidence_complete=True,reconciled=False))
 assert state.transition(LiveState.EMERGENCY_STOPPED,evidence_complete=False,reconciled=False,emergency_stop=True).state==LiveState.EMERGENCY_STOPPED
 print("LIVE_AUTHORIZATION_ADVERSARIAL_SYNTHETIC_TEST_OK")
if __name__=="__main__":main()
