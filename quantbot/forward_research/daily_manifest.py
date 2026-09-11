"""Create-only daily evidence seals for the append-only Forward plane."""
from __future__ import annotations

import json
from pathlib import Path

from .core import AppendOnlyStore, ForwardResearchError, assert_shadow_only, identity


def seal_daily_manifest(*, root: str | Path, date: str, git_commit: str,
                        config_identity: str, research_plan_identity: str,
                        declaration_manifest_identity: str) -> dict:
    """Write one immutable day seal, or fail instead of overwriting it."""
    assert_shadow_only()
    if not all(isinstance(value, str) and value for value in (date, git_commit, config_identity, research_plan_identity, declaration_manifest_identity)):
        raise ForwardResearchError("forward_daily_manifest_input_invalid")
    store = AppendOnlyStore(root)
    base = store.manifest(date, git_commit, config_identity)
    payload = {**base, "schema_version": "quantbot-forward-research-day-v2",
               "research_plan_identity": research_plan_identity,
               "declaration_manifest_identity": declaration_manifest_identity,
               "forward_research_only": True, "oos_allowed": False,
               "order_placement_allowed": False}
    payload["daily_manifest_identity"] = identity({key: value for key, value in payload.items() if key != "daily_manifest_identity"})
    target = Path(root) / "manifests" / f"{date}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        raise ForwardResearchError("forward_daily_manifest_already_sealed")
    try:
        with target.open("x", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            handle.write("\n")
    except FileExistsError as exc:
        raise ForwardResearchError("forward_daily_manifest_already_sealed") from exc
    return payload


def verify_daily_manifest(path: str | Path) -> dict:
    assert_shadow_only()
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("schema_version") != "quantbot-forward-research-day-v2":
        raise ForwardResearchError("forward_daily_manifest_schema_invalid")
    if payload.get("forward_research_only") is not True or payload.get("oos_allowed") is not False or payload.get("order_placement_allowed") is not False:
        raise ForwardResearchError("forward_daily_manifest_safety_invalid")
    seen = payload.get("daily_manifest_identity")
    expected = identity({key: value for key, value in payload.items() if key != "daily_manifest_identity"})
    if seen != expected:
        raise ForwardResearchError("forward_daily_manifest_identity_mismatch")
    return payload
