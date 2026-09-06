"""Deterministic, metadata-only candidate-universe freeze manifests.

This module accepts an already-loaded boundary-lock mapping.  It does not import
research runners, load candles, or inspect OOS result files.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from .candidate_universe import CandidateUniverseProtocolScope, candidate_universe_hash

SCHEMA_VERSION = "quantbot-candidate-freeze-v1"


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def protocol_scope_dict(scope: CandidateUniverseProtocolScope) -> dict[str, Any]:
    return {"scope_id": scope.scope_id, "symbols": list(scope.symbols), "timeframe": scope.timeframe,
            "engine_identity": scope.engine_identity, "cost_model_identity": scope.cost_model_identity,
            "causal_execution_policy": scope.causal_execution_policy}


def boundary_identity(lock: Mapping[str, Any]) -> dict[str, Any]:
    """Only boundary/protocol metadata; no price data, gaps rows, or results."""
    splits = {item["name"]: {"start": item["start"], "end": item["end"]} for item in lock["splits"]}
    policies = lock["policies"]
    return {"dataset_id": lock["dataset_id"], "market": lock["market"], "interval": lock["interval"],
            "requested_end": lock["requested_end"], "actual_end": lock["actual_end"],
            "train_boundary": splits["TRAIN"], "validation_boundary": splits["VALIDATION"],
            "oos_boundary": splits["OOS"], "gap_policy": policies["gap_policy"],
            "synthetic_candles": policies["synthetic_candles"], "lookahead_policy": policies["lookahead_policy"],
            "oos_status": "SEALED", "lock_status": lock["status"]}


def build_freeze_manifest(entries, scope: CandidateUniverseProtocolScope, boundary_lock: Mapping[str, Any], source_git_commit: str,
                          created_at: str | None = None) -> dict[str, Any]:
    universe = tuple(entries)
    scope_data = protocol_scope_dict(scope)
    boundary = boundary_identity(boundary_lock)
    candidate_hash = candidate_universe_hash(universe)
    protocol_hash = _hash(scope_data)
    boundary_hash = _hash(boundary)
    research_identity = _hash({"candidate_universe_hash": candidate_hash, "protocol_scope_hash": protocol_hash,
                               "boundary_identity_hash": boundary_hash})
    models = [{"model_id": e.model_id, "version": e.version, "family": e.family,
               "secondary_traits": list(e.secondary_traits), "parameter_grid_hash": e.parameter_grid_hash,
               "strategy_function_hash": e.strategy_function_hash, "implementation_module_hash": e.implementation_module_hash,
               "warmup_bars": e.warmup_bars, "causal_timing": e.causal_timing,
               "long_short_capable": e.long_short_capable, "research_eligible": e.research_eligible,
               "eligibility_state": e.eligibility_state, "required_features": list(e.required_features)}
              for e in sorted(universe, key=lambda item: item.model_id)]
    manifest = {"schema_version": SCHEMA_VERSION, "source_git_commit": source_git_commit,
                "freeze_status": {"candidate_universe": "FROZEN", "protocol_scope": "FROZEN", "parameter_grids": "FROZEN",
                                  "oos_status": "SEALED", "oos_authorization": "NOT_AUTHORIZED", "formal_research_results_embedded": False},
                "candidate_universe_hash": candidate_hash, "protocol_scope": scope_data, "protocol_scope_hash": protocol_hash,
                "research_boundary": boundary, "boundary_identity_hash": boundary_hash,
                "research_freeze_identity": research_identity, "models": models}
    if created_at is not None:
        manifest["non_identity_metadata"] = {"created_at": created_at}
    return manifest
