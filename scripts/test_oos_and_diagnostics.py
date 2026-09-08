from __future__ import annotations
from quantbot.research.oos_protocol import OOSOpeningProtocol, PreOOSChecklist, OOSState
from quantbot.research.diagnostics import DiagnosticsPolicy
def main():
    checklist=PreOOSChecklist("f","p","m","d","b","g",True,True,True,True)
    protocol=OOSOpeningProtocol("f","p")
    assert protocol.precheck(checklist)==OOSState.ELIGIBLE_BUT_NOT_AUTHORIZED
    try: protocol.request_window("OOS",checklist)
    except PermissionError: pass
    else: raise AssertionError("oos opened")
    for bad in (DiagnosticsPolicy(0),DiagnosticsPolicy(maximum_family_concentration=2)):
        try: bad.validate()
        except ValueError: pass
        else: raise AssertionError("bad diagnostics policy accepted")
    print("OOS_AND_DIAGNOSTICS_LOCKED_SYNTHETIC_TEST_OK")
if __name__=="__main__": main()
