"""Synthetic-only protocol tests. No research data is read."""
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from quantbot.research.walk_forward import FreezeRecord,OOSAuthorization,OOSSealedError,Window,build_protocol

def main():
    train=Window("TRAIN","2021-01-01","2024-12-31"); valid=Window("VALIDATION","2025-01-01","2025-12-31"); oos=Window("OOS","2026-01-01","2026-07-31")
    freeze=FreezeRecord("d1",True,True)
    try: build_protocol(train=train,validation=valid,next_period=oos,freeze=freeze)
    except OOSSealedError: pass
    else: raise AssertionError("sealed OOS must reject")
    assert len(build_protocol(train=train,validation=valid,next_period=oos,freeze=freeze,oos_authorization=OOSAuthorization("explicit-token",True)))==3
    print("WALK_FORWARD_PROTOCOL_SYNTHETIC_TEST_OK")
if __name__=="__main__": main()
