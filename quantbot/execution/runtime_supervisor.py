"""Persistent-paper supervision metadata, extending (not replacing) paper_runtime."""
from __future__ import annotations

import json, os
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from quantbot.research.artifact_store import artifact_identity


@dataclass(frozen=True)
class PaperRuntimeCheckpoint:
    ledger_identity: str
    sequence: int
    status: str = "PAPER_ONLY"


def checkpoint_payload(checkpoint: PaperRuntimeCheckpoint, *, provenance: Mapping[str, object]) -> dict[str, object]:
    if checkpoint.sequence < 0 or checkpoint.status != "PAPER_ONLY":
        raise ValueError("paper_checkpoint_invalid")
    payload = {"schema_version": "quantbot-paper-runtime-checkpoint-p2-v1",
               "ledger_identity": checkpoint.ledger_identity, "sequence": checkpoint.sequence,
               "status": checkpoint.status, "provenance": dict(provenance)}
    return payload | {"checkpoint_identity": artifact_identity(payload, identity_key="checkpoint_identity")}

@dataclass(frozen=True)
class RuntimeSupervisorState:
    session_identity: str; sequence: int = 0; heartbeat: int = 0; status: str = "PAPER_ONLY"

def write_checkpoint_new(path: str | Path, state: RuntimeSupervisorState, *, provenance: Mapping[str, object]) -> Path:
    target = Path(path)
    payload = checkpoint_payload(PaperRuntimeCheckpoint(state.session_identity, state.sequence), provenance=provenance) | {"heartbeat": state.heartbeat}
    if target.exists(): raise ValueError("checkpoint_overwrite_forbidden")
    target.parent.mkdir(parents=True, exist_ok=True); temporary = target.with_suffix(target.suffix + ".tmp")
    try:
        temporary.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8"); os.replace(temporary, target)
    except Exception:
        temporary.unlink(missing_ok=True); raise
    return target

def load_checkpoint(path: str | Path) -> dict[str, object]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("status") != "PAPER_ONLY" or not payload.get("checkpoint_identity"): raise ValueError("checkpoint_invalid")
    return payload

@contextmanager
def single_writer(root: str | Path):
    """Portable process lock for the synthetic/Paper supervisor lifecycle."""
    lock=Path(root)/".paper-runtime.lock"; lock.parent.mkdir(parents=True,exist_ok=True)
    handle=lock.open("a+b")
    try:
        if os.name=="nt":
            import msvcrt
            handle.write(b"0");handle.flush();handle.seek(0);msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
    except OSError as exc:
        handle.close();raise RuntimeError("runtime_single_writer_held") from exc
    try: yield
    finally:
        try:
            if os.name=="nt":
                import msvcrt
                handle.seek(0);msvcrt.locking(handle.fileno(),msvcrt.LK_UNLCK,1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(),fcntl.LOCK_UN)
        finally: handle.close()

@dataclass(frozen=True)
class RuntimeLifecycle:
    state: RuntimeSupervisorState
    reconciled: bool = False
    emergency_stopped: bool = False
    def startup(self, *, reconciled: bool) -> "RuntimeLifecycle":
        if not reconciled: raise RuntimeError("runtime_reconciliation_required")
        return RuntimeLifecycle(self.state,reconciled=True)
    def beat(self) -> "RuntimeLifecycle":
        if not self.reconciled or self.emergency_stopped: raise RuntimeError("runtime_not_operational")
        return RuntimeLifecycle(RuntimeSupervisorState(self.state.session_identity,self.state.sequence,self.state.heartbeat+1,self.state.status),True)
    def emergency_stop(self) -> "RuntimeLifecycle":
        return RuntimeLifecycle(self.state,self.reconciled,True)
