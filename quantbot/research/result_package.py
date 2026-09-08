"""N11 immutable package for an already validated N10/N7 result snapshot."""
from __future__ import annotations

from typing import Any, Mapping

from .artifact_store import ArtifactError, read_verified_json, seal, validate_seal, write_new_json
from .authorization import require_sealed_non_oos

SCHEMA_VERSION = "quantbot-research-result-package-n11-v1"
EVIDENCE_SCHEMA_VERSION = "quantbot-research-result-package-n11-v2"


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


def build_evidence_package(*, run_state: Mapping[str, Any], execution_binding: Mapping[str, Any],
                           task_artifacts: list[Mapping[str, Any]], authority_manifest: Mapping[str, Any],
                           source_git_commit: str, environment: Mapping[str, Any], created_at: str) -> dict[str, Any]:
    """N11 v2 authoritative package builder.

    ``run_state`` and task artifacts are expected to have passed N10 validation
    before entry.  This builder independently binds their identities so they
    cannot be substituted across runs after packaging.
    """
    from .recoverable_execution import validate_task_artifact
    require_sealed_non_oos(execution_binding)
    if run_state.get("run_id") != execution_binding.get("run_id", run_state.get("run_id")):
        raise ArtifactError("n10_run_binding_mismatch")
    if authority_manifest.get("manifest_identity") != execution_binding.get("manifest_identity"):
        raise ArtifactError("n9_authority_stale_or_mismatched")
    tasks_by_id = run_state.get("tasks")
    if not isinstance(tasks_by_id, Mapping) or not isinstance(task_artifacts, list):
        raise ArtifactError("n10_state_or_tasks_missing")
    expected = set(tasks_by_id)
    actual = {row.get("task_identity") for row in task_artifacts}
    if not expected or actual != expected or len(actual) != len(task_artifacts):
        raise ArtifactError("cross_run_or_truncated_tasks")
    completed = []
    for row in task_artifacts:
        if row.get("run_id") != run_state.get("run_id") or row.get("status") != "COMPLETED":
            raise ArtifactError("task_not_completed_for_package")
        if row.get("manifest_identity") != authority_manifest.get("manifest_identity"):
            raise ArtifactError("task_authority_binding_mismatch")
        if not isinstance(row.get("result_hash"), str) or len(row["result_hash"]) != 64:
            raise ArtifactError("task_result_checksum_missing")
        completed.append(dict(row))
    payload = {"schema_version": EVIDENCE_SCHEMA_VERSION, "run_id": run_state["run_id"],
               "n10_execution_identity": run_state["run_id"], "n9_manifest_identity": authority_manifest["manifest_identity"],
               "source_git_commit": source_git_commit, "created_at": created_at, "environment": dict(environment),
               "research_freeze_identity": execution_binding["research_freeze_identity"],
               "research_plan_identity": execution_binding["research_plan_identity"],
               "candidate_universe_hash": execution_binding["candidate_universe_hash"],
               "dataset_id": execution_binding.get("dataset_id"), "boundary_identity_hash": execution_binding.get("boundary_identity_hash"),
               "execution_binding": dict(execution_binding), "authority": {key: authority_manifest.get(key) for key in ("manifest_identity", "source_git_commit", "train_window", "validation_window")},
               "recovery": {"revision": run_state.get("revision"), "accounting": run_state.get("accounting"), "task_attempts": {key: value.get("attempts", []) for key, value in tasks_by_id.items()}},
               "tasks": sorted(completed, key=lambda row: row["task_identity"]),
               "checksums": {row["task_identity"]: row["result_hash"] for row in sorted(completed, key=lambda row: row["task_identity"])},
               "counts": {"tasks": len(completed), "train": sum(row.get("actual_train_evaluations", 0) for row in completed), "validation": sum(row.get("actual_validation_evaluations", 0) for row in completed)},
               "oos_status": "SEALED", "oos_authorization": "NOT_AUTHORIZED"}
    return seal(payload)


def validate_evidence_package(package: Mapping[str, Any], *, expected_run_id: str | None = None,
                              expected_manifest_identity: str | None = None) -> bool:
    if package.get("schema_version") != EVIDENCE_SCHEMA_VERSION:
        raise ArtifactError("evidence_package_schema_invalid")
    validate_seal(package); require_sealed_non_oos(package)
    if expected_run_id is not None and package.get("run_id") != expected_run_id: raise ArtifactError("evidence_run_substitution")
    if expected_manifest_identity is not None and package.get("n9_manifest_identity") != expected_manifest_identity: raise ArtifactError("evidence_authority_substitution")
    tasks = package.get("tasks", []); checksums = package.get("checksums", {})
    if not isinstance(tasks, list) or not isinstance(checksums, Mapping) or len(tasks) != package.get("counts", {}).get("tasks"):
        raise ArtifactError("evidence_package_truncated")
    identities = [row.get("task_identity") for row in tasks]
    if len(identities) != len(set(identities)) or set(identities) != set(checksums): raise ArtifactError("evidence_task_set_invalid")
    for row in tasks:
        if row.get("status") != "COMPLETED" or checksums.get(row.get("task_identity")) != row.get("result_hash"):
            raise ArtifactError("evidence_task_checksum_mismatch")
        if row.get("run_id") != package.get("run_id") or row.get("manifest_identity") != package.get("n9_manifest_identity"):
            raise ArtifactError("evidence_cross_run_substitution")
    return True
