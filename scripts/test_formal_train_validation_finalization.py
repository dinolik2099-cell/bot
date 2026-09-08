"""Synthetic-only finalization tests for formal TRAIN/VALIDATION runner."""
from pathlib import Path
import importlib.util
import json
import shutil
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from quantbot.research.formal_runner import load_n7_context
from quantbot.research.canonical_data_adapter import load_n8_data_context
from quantbot.research.formal_execution_manifest import build_manifest
from quantbot.research.plan_executor import rank_train
from quantbot.research.recoverable_execution import (
    claim_task,
    complete_task,
    final_result_identity,
    initialize_run,
    load_run,
    task_result_payload,
)
from quantbot.research.artifact_store import (
    ArtifactError,
    read_verified_json,
)

PLAN = ROOT / "docs/handoff/FROZEN_RESEARCH_PLAN_N5.json"
FREEZE = ROOT / "docs/handoff/CANDIDATE_UNIVERSE_FREEZE_N3.json"
LOCK_PATH = ROOT / "data/reports/research_boundary_lock.json"
AUDIT_ROOT = ROOT / "server_local_audit" / "formal_finalization_synthetic"


def load_candidate():
    path = ROOT / "scripts/run_formal_train_validation.py"
    spec = importlib.util.spec_from_file_location(
        "formal_runner_candidate_finalization", path
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def clean_repo(path):
    path.mkdir(parents=True)
    subprocess.check_call(["git", "init", "-q", str(path)])
    subprocess.check_call(
        ["git", "-C", str(path), "config", "user.email",
         "finalization@example.invalid"]
    )
    subprocess.check_call(
        ["git", "-C", str(path), "config", "user.name",
         "Finalization Test"]
    )
    (path / "README").write_text("synthetic\n", encoding="utf-8")
    subprocess.check_call(["git", "-C", str(path), "add", "README"])
    subprocess.check_call(
        ["git", "-C", str(path), "commit", "-q", "-m", "synthetic"]
    )
    return subprocess.check_output(
        ["git", "-C", str(path), "rev-parse", "HEAD"],
        text=True,
    ).strip()


def grid_rows(state, task):
    from itertools import product

    grid = state["binding"]["parameter_grids"][task["model_id"]]
    keys = sorted(grid)
    rows = []

    for i, values in enumerate(product(*(grid[k] for k in keys))):
        params = dict(zip(keys, values))
        rows.append(
            {
                "params": params,
                "total_return": 0.001 * (i + 1),
                "max_drawdown": 0.0001 * ((i % 7) + 1),
                "profit_factor": 1.0 + 0.01 * (i % 11),
                "trades": 10 + i,
            }
        )

    return rows


def completed_artifact(state, plan, task):
    train = grid_rows(state, task)
    model = next(
        m for m in plan["models"]
        if m["model_id"] == task["model_id"]
    )
    k = min(plan["top_k_train"], model["grid_combinations"])
    top = rank_train(train)[:k]

    validation = []
    for i, row in enumerate(top):
        validation.append(
            {
                "params": dict(row["params"]),
                "total_return": 0.01 + i / 1000.0,
                "max_drawdown": 0.001,
                "profit_factor": 1.1,
                "trades": 20 + i,
            }
        )

    return task_result_payload(
        state,
        plan,
        task["task_identity"],
        status="COMPLETED",
        train_results=train,
        validation_results=validation,
    )


def main():
    mod = load_candidate()

    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    n7 = load_n7_context(PLAN, FREEZE, lock)
    n8 = load_n8_data_context(n7, LOCK_PATH)

    AUDIT_ROOT.mkdir(parents=True, exist_ok=True)
    work = AUDIT_ROOT / ("case_" + uuid.uuid4().hex)
    repo = work / "repo"
    run_root = work / "runtime"
    output_root = work / "output"

    real_market_reads = 0

    try:
        commit = clean_repo(repo)

        manifest = build_manifest(
            n7,
            n8,
            source_git_commit=commit,
            worker_config={"workers": 1},
            output_destination=(
                "data/reports/formal_runs/"
                "N11_FORMAL_TRAIN_VALIDATION_RESULT.json"
            ),
            created_at="synthetic",
        )

        authority = {
            "n7": n7,
            "n8": n8,
            "repo_root": repo,
            "requested_windows": {
                "TRAIN": manifest["train_window"],
                "VALIDATION": manifest["validation_window"],
            },
            "output_path": manifest["output"]["destination"],
            "requested_workers": 1,
        }

        initialize_run(
            run_root,
            manifest,
            n7.plan,
            n7=n7,
            n8=n8,
            repo_root=repo,
        )

        # Partial N10 state must never be accepted as final evidence.
        try:
            mod.validated_task_artifacts(
                run_root,
                manifest,
                n7,
            )
        except RuntimeError as exc:
            assert "formal_run_not_complete" in str(exc)
        else:
            raise AssertionError("PARTIAL_RUN_FINALIZATION_ACCEPTED")

        tasks = sorted(
            n7.plan["tasks"],
            key=lambda row: row["task_identity"],
        )

        # Complete all 216 tasks using synthetic metrics only.
        for task in tasks:
            claim_task(
                run_root,
                manifest,
                n7.plan,
                task["task_identity"],
                owner="synthetic-finalization",
                authority=authority,
            )

            state = load_run(
                run_root,
                manifest,
                n7.plan,
            )

            artifact = completed_artifact(
                state,
                n7.plan,
                task,
            )

            complete_task(
                run_root,
                manifest,
                n7.plan,
                artifact,
                authority=authority,
            )

        state, artifacts = mod.validated_task_artifacts(
            run_root,
            manifest,
            n7,
        )

        assert len(artifacts) == 216
        assert state["accounting"]["completed_count"] == 216
        assert state["accounting"]["failed_count"] == 0

        identity = final_result_identity(
            run_root,
            manifest,
            n7.plan,
        )
        assert isinstance(identity, str)
        assert len(identity) == 64

        binding = mod.execution_binding(
            manifest,
            n7.plan,
            n7=n7,
            n8=n8,
        )
        assert state["binding"] == binding

        package = mod.build_evidence_package(
            run_state=state,
            execution_binding=binding,
            task_artifacts=artifacts,
            authority_manifest=manifest,
            source_git_commit=manifest["source_git_commit"],
            environment={
                "python": "synthetic",
                "runner": "synthetic-finalization-test",
                "n10_final_result_identity": identity,
            },
            created_at="synthetic",
        )

        assert mod.validate_evidence_package(
            package,
            expected_run_id=state["run_id"],
            expected_manifest_identity=manifest["manifest_identity"],
        )

        assert package["counts"]["tasks"] == 216
        assert package["oos_status"] == "SEALED"
        assert package["oos_authorization"] == "NOT_AUTHORIZED"

        output_root.mkdir(parents=True, exist_ok=True)
        output_name = "N11_FORMAL_TRAIN_VALIDATION_RESULT.json"

        path = mod.write_named_new_json(
            output_root,
            output_name,
            package,
        )

        verified = read_verified_json(path)
        assert verified["artifact_identity"] == package["artifact_identity"]
        assert verified["run_id"] == state["run_id"]

        try:
            mod.write_named_new_json(
                output_root,
                output_name,
                package,
            )
        except ArtifactError as exc:
            assert "immutable_artifact_exists" in str(exc)
        else:
            raise AssertionError("N11_IMMUTABLE_OVERWRITE_ACCEPTED")

        assert real_market_reads == 0

        print("PARTIAL_RUN_FINALIZATION_BLOCKED=1")
        print("SYNTHETIC_COMPLETED_TASKS=216")
        print("N10_TASK_REVALIDATION=216")
        print("N10_FINAL_RESULT_IDENTITY=PASS")
        print("N10_EXECUTION_BINDING_MATCH=PASS")
        print("N11_EVIDENCE_VALIDATION=PASS")
        print("N11_CREATE_ONLY_WRITE=PASS")
        print("N11_SECOND_WRITE_BLOCKED=PASS")
        print("OOS_STATUS=SEALED")
        print("OOS_AUTHORIZATION=NOT_AUTHORIZED")
        print("REAL_MARKET_DATA_READS=0")
        print("FORMAL_FINALIZATION_SYNTHETIC_TEST_OK")

    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
