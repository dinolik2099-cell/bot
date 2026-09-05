"""Explicit, fail-closed provenance contracts for non-OOS runtime inputs."""
from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class RunProvenance:
    dataset_id: str
    research_version: str
    source_window: str
    engine_version: str = "engine_v2"
    oos_read: bool = False

def validate_non_oos_provenance(provenance: RunProvenance) -> None:
    if not provenance.dataset_id or not provenance.research_version:
        raise ValueError("dataset_id and research_version are required")
    if provenance.oos_read or provenance.source_window.upper() == "OOS":
        raise PermissionError("OOS provenance is sealed and cannot enter paper runtime")
    if provenance.engine_version != "engine_v2":
        raise ValueError("paper runtime requires canonical engine_v2 provenance")
