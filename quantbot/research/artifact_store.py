"""Canonical immutable JSON artifact primitives.

Every future research artifact carries a deterministic identity.  The writer
uses create-only file semantics and a temporary sibling, so an accepted file
cannot be silently replaced or left as a torn JSON document.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping


class ArtifactError(RuntimeError):
    pass


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def artifact_identity(payload: Mapping[str, Any], *, identity_key: str = "artifact_identity") -> str:
    body = dict(payload)
    body.pop(identity_key, None)
    return hashlib.sha256(canonical_json(body).encode("utf-8")).hexdigest()


def seal(payload: Mapping[str, Any], *, identity_key: str = "artifact_identity") -> dict[str, Any]:
    body = dict(payload)
    body[identity_key] = artifact_identity(body, identity_key=identity_key)
    return body


def validate_seal(payload: Mapping[str, Any], *, identity_key: str = "artifact_identity") -> bool:
    claimed = payload.get(identity_key)
    if not isinstance(claimed, str) or claimed != artifact_identity(payload, identity_key=identity_key):
        raise ArtifactError("artifact_identity_mismatch")
    return True


def write_new_json(root: str | Path, prefix: str, payload: Mapping[str, Any]) -> Path:
    validate_seal(payload)
    directory = Path(root).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{prefix}_{payload['artifact_identity']}.json"
    if path.exists():
        raise ArtifactError("immutable_artifact_exists")
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("x", encoding="utf-8") as handle:
            handle.write(canonical_json(payload) + "\n")
        os.replace(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return path


def resolve_artifact_path(root: str | Path, relative_name: str) -> Path:
    """Resolve only one safe relative artifact name inside ``root``."""
    base = Path(root).resolve()
    requested = Path(relative_name)
    if requested.is_absolute() or ".." in requested.parts or requested.name != relative_name:
        raise ArtifactError("artifact_path_traversal")
    target = (base / requested).resolve()
    if target.parent != base:
        raise ArtifactError("artifact_path_outside_root")
    return target


def write_named_new_json(root: str | Path, relative_name: str, payload: Mapping[str, Any]) -> Path:
    validate_seal(payload)
    target = resolve_artifact_path(root, relative_name)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists(): raise ArtifactError("immutable_artifact_exists")
    temporary = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("x", encoding="utf-8") as handle: handle.write(canonical_json(payload) + "\n")
        os.replace(temporary, target)
    except Exception:
        temporary.unlink(missing_ok=True); raise
    return target


def read_verified_json(path: str | Path) -> dict[str, Any]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception as exc:
        raise ArtifactError("artifact_unreadable") from exc
    if not isinstance(payload, dict):
        raise ArtifactError("artifact_object_required")
    validate_seal(payload)
    return payload
