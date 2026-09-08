"""Persistent-paper supervision metadata, extending (not replacing) paper_runtime."""
from __future__ import annotations

import json, os
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
