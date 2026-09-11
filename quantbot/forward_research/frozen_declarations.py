"""Read-only binding of Forward Shadow models to the accepted N5 metadata.

N5 deliberately freezes model identities and grids, but does not choose a
winning parameter set.  Forward therefore accepts an explicit declaration
from an external, versioned decision artifact; it never derives one from a
grid or observes a result in order to choose one.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping, Sequence

from .core import ForwardResearchError, identity, assert_shadow_only

DECLARATION_SCHEMA = "quantbot-forward-frozen-declarations-v1"
INPUT_BOUNDARY = "COMPLETED_CANDLE_T_MINUS_1"


def load_n5_plan(path: str | Path) -> dict:
    """Load metadata only; this function never loads candles or research output."""
    assert_shadow_only()
    plan = json.loads(Path(path).read_text(encoding="utf-8"))
    if plan.get("oos_status") != "SEALED" or plan.get("oos_authorization") != "NOT_AUTHORIZED":
        raise ForwardResearchError("forward_n5_oos_state_invalid")
    if not plan.get("research_plan_identity") or not plan.get("research_freeze_identity"):
        raise ForwardResearchError("forward_n5_identity_missing")
    return plan


def _model_rows(plan: Mapping) -> dict[str, Mapping]:
    rows = {row.get("model_id"): row for row in plan.get("models", ())}
    if not rows or None in rows or len(rows) != len(plan.get("models", ())):
        raise ForwardResearchError("forward_n5_model_rows_invalid")
    return rows


def declaration_identity(row: Mapping) -> str:
    """Identity deliberately includes every frozen provenance input."""
    payload = {key: row[key] for key in (
        "schema_version", "research_freeze_identity", "research_plan_identity",
        "model_id", "model_name", "params", "params_identity",
        "parameter_grid_hash", "strategy_function_hash", "implementation_module_hash",
        "input_boundary",
    )}
    return identity(payload)


def validate_forward_declarations(plan: Mapping, declarations: Sequence[Mapping]) -> tuple[dict, ...]:
    """Fail closed on any N5/model/provenance drift.

    This validates the declaration artifact, not its investment merit.  It
    never enumerates grids, ranks models, or authorizes formal/OOS research.
    """
    assert_shadow_only()
    models = _model_rows(plan)
    seen: set[str] = set()
    validated: list[dict] = []
    for raw in declarations:
        row = dict(raw)
        model_id = row.get("model_id")
        if model_id in seen or model_id not in models:
            raise ForwardResearchError("forward_declaration_model_invalid")
        seen.add(model_id)
        frozen = models[model_id]
        if row.get("schema_version") != DECLARATION_SCHEMA:
            raise ForwardResearchError("forward_declaration_schema_invalid")
        if row.get("research_freeze_identity") != plan.get("research_freeze_identity") or row.get("research_plan_identity") != plan.get("research_plan_identity"):
            raise ForwardResearchError("forward_declaration_plan_chain_mismatch")
        if not isinstance(row.get("model_name"), str) or not row["model_name"]:
            raise ForwardResearchError("forward_declaration_model_name_invalid")
        if not isinstance(row.get("params"), Mapping):
            raise ForwardResearchError("forward_declaration_params_invalid")
        if row.get("params_identity") != identity(dict(row["params"])):
            raise ForwardResearchError("forward_declaration_params_identity_mismatch")
        for key in ("parameter_grid_hash", "strategy_function_hash", "implementation_module_hash"):
            if row.get(key) != frozen.get(key):
                raise ForwardResearchError("forward_declaration_model_metadata_mismatch")
        if row.get("input_boundary") != INPUT_BOUNDARY:
            raise ForwardResearchError("forward_declaration_input_boundary_invalid")
        if row.get("declaration_identity") != declaration_identity(row):
            raise ForwardResearchError("forward_declaration_identity_mismatch")
        validated.append(row)
    return tuple(sorted(validated, key=lambda item: item["model_id"]))
