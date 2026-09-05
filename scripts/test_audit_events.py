"""Synthetic-only tests for the decision audit state machine."""
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from quantbot.analytics import DecisionAuditTrail, correlation_id

def main():
    trail=DecisionAuditTrail(); key=correlation_id("BTCUSDT","2025-01-01T00:00:00Z")
    source_payload={"provenance":{"source_window":"VALIDATION"},"tags":["paper","safe"]}
    first=trail.append("signal_created",key,source_payload)
    trail.append("portfolio_selected",key)
    trail.append("risk_approved",key)
    trail.append("paper_requested",key)
    assert [x.event_type for x in trail.events] == ["signal_created","portfolio_selected","risk_approved","paper_requested"]

    try:
        first.payload["provenance"]={"source_window":"OOS"}
    except TypeError:
        pass
    else:
        raise AssertionError("audit payload must be immutable")

    try:
        first.payload["provenance"]["source_window"]="OOS"
    except TypeError:
        pass
    else:
        raise AssertionError("nested audit payload must be immutable")

    source_payload["provenance"]["source_window"]="OOS"
    source_payload["tags"].append("mutated")
    assert first.payload["provenance"]["source_window"]=="VALIDATION"
    assert first.payload["tags"]==("paper","safe")
    try: trail.append("paper_requested",correlation_id("bad"))
    except ValueError: pass
    else: raise AssertionError("paper request must not bypass risk")
    print("AUDIT_EVENTS_SYNTHETIC_TEST_OK")
if __name__ == "__main__": main()
