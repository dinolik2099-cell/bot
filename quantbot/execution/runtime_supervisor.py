"""Persistent-paper supervision metadata, extending (not replacing) paper_runtime."""
from __future__ import annotations

from dataclasses import dataclass
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
