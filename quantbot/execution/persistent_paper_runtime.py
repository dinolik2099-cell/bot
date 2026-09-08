"""Durable wrapper around the existing in-memory PaperLedger.

It never polls an exchange or places a live order.  Recovery reconstructs the
same ledger snapshot and rejects duplicate order identities across restarts.
"""
from __future__ import annotations
import json, os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Mapping
from quantbot.execution.paper import PaperOrderRequest
from quantbot.execution.paper_ledger import PaperLedger, PaperOrderState
from quantbot.execution.reconciliation import reconcile
from quantbot.research.artifact_store import artifact_identity
from quantbot.risk import RiskSnapshot, evaluate_circuit_breaker, emergency_stop_from_breaker
from quantbot.risk.failure_supervisor import FailureEvent, SupervisorState, decide

@dataclass(frozen=True)
class PersistentPaperState:
    session_identity: str
    run_identity: str
    sequence: int
    orders: tuple[Mapping[str, object], ...]
    exposures: tuple[Mapping[str, object], ...] = ()
    failure_events: tuple[Mapping[str, object], ...] = ()
    status: str = "PAPER_ONLY"

def _serialize(state: PersistentPaperState) -> dict[str, object]:
    body={"schema_version":"quantbot-persistent-paper-v1", **asdict(state)}
    return body | {"state_identity":artifact_identity(body,identity_key="state_identity")}

def save_new_state(path: str | Path, state: PersistentPaperState) -> Path:
    target=Path(path); payload=_serialize(state)
    if target.exists(): raise ValueError("persistent_state_overwrite_forbidden")
    target.parent.mkdir(parents=True,exist_ok=True); temporary=target.with_name("."+target.name+".tmp")
    try:
        with temporary.open("x",encoding="utf-8") as handle: json.dump(payload,handle,sort_keys=True);handle.write("\n")
        os.replace(temporary,target)
    except Exception: temporary.unlink(missing_ok=True);raise
    return target

def load_state(path: str | Path) -> PersistentPaperState:
    payload=json.loads(Path(path).read_text(encoding="utf-8")); claimed=payload.pop("state_identity",None)
    if payload.get("schema_version")!="quantbot-persistent-paper-v1" or claimed!=artifact_identity(payload,identity_key="state_identity") or payload.get("status")!="PAPER_ONLY": raise ValueError("persistent_state_invalid")
    payload.pop("schema_version"); return PersistentPaperState(**payload)

def ledger_from_state(state: PersistentPaperState) -> PaperLedger:
    ledger=PaperLedger()
    for raw in state.orders:
        request=PaperOrderRequest(**raw["request"]); order=ledger.request(request)
        if raw.get("status")=="filled": ledger.fill(request.client_order_id,float(raw["fill_price"]))
        elif raw.get("status")=="rejected": ledger.reject(request.client_order_id,str(raw["rejection_reason"]))
        elif raw.get("status")!="requested": raise ValueError("persistent_order_status_invalid")
    return ledger

def snapshot_state(session_identity: str, run_identity: str, sequence: int, ledger: PaperLedger, *, exposures: Iterable[Mapping[str, object]]=(), failures: Iterable[Mapping[str, object]]=()) -> PersistentPaperState:
    rows=tuple({"request":asdict(row.request),"status":row.status,"fill_price":row.fill_price,"rejection_reason":row.rejection_reason} for row in ledger.orders)
    return PersistentPaperState(session_identity,run_identity,sequence,rows,tuple(exposures),tuple(failures))

def startup_reconcile(state: PersistentPaperState, observed: Iterable[PaperOrderState]) -> bool:
    report=reconcile(ledger_from_state(state).orders,observed)
    if not report.clean: raise RuntimeError("paper_startup_reconciliation_failed")
    return True

def supervise_paper_failure(event: FailureEvent, snapshot: RiskSnapshot) -> str:
    breaker=evaluate_circuit_breaker(snapshot); stop=emergency_stop_from_breaker(breaker,snapshot)
    decision=decide(event,SupervisorState())
    if stop.active or decision.terminal: return "STOP"
    return decision.action
