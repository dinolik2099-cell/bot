"""N11 immutable package for an already validated N10/N7 result snapshot."""
from __future__ import annotations

from typing import Any, Mapping

from .artifact_store import ArtifactError, read_verified_json, seal, validate_seal, write_new_json
from .authorization import require_sealed_non_oos

SCHEMA_VERSION = "quantbot-research-result-package-n11-v1"


def build_result_package(*, run_id: str, execution_binding: Mapping[str, Any],
                         task_artifacts: list[Mapping[str, Any]], recovery_state: Mapping[str, Any],
                         source_git_commit: str) -> dict[str, Any]:
    """Build evidence only; this function does not execute or inspect market data."""
    require_sealed_non_oos(execution_binding)
    tasks = sorted(task_artifacts, key=lambda row: row.get("task_identity", ""))
    expected = execution_binding.get("counts", {}).get("model_symbol_cells")
    task_ids = [row.get("task_identity") for row in tasks]
    if not isinstance(expected, int) or len(tasks) != expected or len(set(task_ids)) != expected:
        raise ArtifactError("result_package_task_universe_invalid")
    if any(row.get("status") != "COMPLETED" for row in tasks):
        raise ArtifactError("partial_run_cannot_package")
    identity_fields = ("research_freeze_identity", "research_plan_identity", "candidate_universe_hash")
    for key in identity_fields:
        if not execution_binding.get(key):
            raise ArtifactError("result_package_binding_missing")
    payload = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "source_git_commit": source_git_commit,
        "research_freeze_identity": execution_binding["research_freeze_identity"],
        "research_plan_identity": execution_binding["research_plan_identity"],
        "candidate_universe_hash": execution_binding["candidate_universe_hash"],
        "dataset_id": execution_binding.get("dataset_id"),
        "boundary_identity_hash": execution_binding.get("boundary_identity_hash"),
        "execution_binding": dict(execution_binding),
        "recovery_state": dict(recovery_state),
        "tasks": tasks,
        "counts": {"tasks": expected,
                   "train": sum(row.get("actual_train_evaluations", 0) for row in tasks),
                   "validation": sum(row.get("actual_validation_evaluations", 0) for row in tasks)},
        "oos_status": "SEALED", "oos_authorization": "NOT_AUTHORIZED",
    }
    return seal(payload)


def validate_result_package(package: Mapping[str, Any], *, binding: Mapping[str, Any] | None = None) -> bool:
    if package.get("schema_version") != SCHEMA_VERSION:
        raise ArtifactError("result_package_schema_invalid")
    validate_seal(package)
    require_sealed_non_oos(package)
    tasks = package.get("tasks")
    if not isinstance(tasks, list) or package.get("counts", {}).get("tasks") != len(tasks):
        raise ArtifactError("result_package_task_count_mismatch")
    if len({row.get("task_identity") for row in tasks}) != len(tasks) or any(row.get("status") != "COMPLETED" for row in tasks):
        raise ArtifactError("result_package_tasks_invalid")
    if binding is not None:
        for key in ("research_freeze_identity", "research_plan_identity", "candidate_universe_hash", "dataset_id", "boundary_identity_hash"):
            if package.get(key) != binding.get(key):
                raise ArtifactError("result_package_binding_mismatch")
    return True


def write_result_package(root: str, package: Mapping[str, Any]):
    validate_result_package(package)
    return write_new_json(root, "N11_RESEARCH_RESULT_PACKAGE", package)


def read_result_package(path: str):
    package = read_verified_json(path)
    validate_result_package(package)
    return package
