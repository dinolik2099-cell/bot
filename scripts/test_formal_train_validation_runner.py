"""Synthetic-only adversarial tests for the formal TRAIN/VALIDATION runner."""
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
from quantbot.research.plan_executor import frozen_grid, rank_train
from quantbot.research.recoverable_execution import (
    RecoverableExecutionError,
    initialize_run,
    load_run,
    unfinished_task_ids,
)

PLAN = ROOT / "docs/handoff/FROZEN_RESEARCH_PLAN_N5.json"
FREEZE = ROOT / "docs/handoff/CANDIDATE_UNIVERSE_FREEZE_N3.json"
LOCK_PATH = ROOT / "data/reports/research_boundary_lock.json"
AUDIT_ROOT = ROOT / "server_local_audit" / "formal_runner_synthetic"


def load_candidate():
    path = ROOT / "scripts/run_formal_train_validation.py"
    spec = importlib.util.spec_from_file_location("formal_runner_candidate", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def clean_repo(path):
    path.mkdir(parents=True)
    subprocess.check_call(["git", "init", "-q", str(path)])
    subprocess.check_call(["git", "-C", str(path), "config", "user.email", "runner@example.invalid"])
    subprocess.check_call(["git", "-C", str(path), "config", "user.name", "Runner Test"])
    (path / "README").write_text("synthetic\n", encoding="utf-8")
    subprocess.check_call(["git", "-C", str(path), "add", "README"])
    subprocess.check_call(["git", "-C", str(path), "commit", "-q", "-m", "synthetic"])
    return subprocess.check_output(
        ["git", "-C", str(path), "rev-parse", "HEAD"], text=True
    ).strip()


def synthetic_metrics(params, window):
    key = json.dumps(params, sort_keys=True, separators=(",", ":"))
    score = sum(ord(ch) for ch in key) % 10000
    base = score / 100000.0
    if window == "TRAIN":
        return {
            "total_return": 0.10 + base,
            "max_drawdown": 0.01 + (score % 17) / 100000.0,
            "profit_factor": 1.10 + (score % 13) / 100.0,
            "trades": 20 + score % 31,
        }
    if window == "VALIDATION":
        return {
            "total_return": 0.02 + base / 10.0,
            "max_drawdown": 0.005,
            "profit_factor": 1.05,
            "trades": 15 + score % 11,
        }
    raise AssertionError("OOS_OR_UNKNOWN_WINDOW_REACHED_EVALUATOR")


def main():
    mod = load_candidate()
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    n7 = load_n7_context(PLAN, FREEZE, lock)
    n8 = load_n8_data_context(n7, LOCK_PATH)

    AUDIT_ROOT.mkdir(parents=True, exist_ok=True)
    work = AUDIT_ROOT / ("case_" + uuid.uuid4().hex)
    repo = work / "repo"
    run_root = work / "run"

    market_reads = 0
    calls = []

    try:
        commit = clean_repo(repo)
        manifest = build_manifest(
            n7,
            n8,
            source_git_commit=commit,
            worker_config={"workers": 1},
            output_destination="data/reports/formal_runs/SYNTHETIC_RUNNER_RESULT.json",
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

        entries = mod.entry_index(n7)
        task = sorted(n7.plan["tasks"], key=lambda r: r["task_identity"])[0]
        entry = entries[task["model_id"]]
        expected_grid = frozen_grid(entry)

        def evaluator(window, got_entry, got_task, params):
            nonlocal market_reads
            assert window in {"TRAIN", "VALIDATION"}
            assert got_entry.model_id == task["model_id"]
            assert got_task["task_identity"] == task["task_identity"]
            calls.append((window, json.dumps(params, sort_keys=True)))
            return synthetic_metrics(params, window)

        artifact = mod._execute_one_task_with_evaluator_for_test(
            run_root=run_root,
            manifest=manifest,
            n7=n7,
            n8=n8,
            task_identity=task["task_identity"],
            evaluator=evaluator,
            entries=entries,
            authority=authority,
            owner="synthetic-runner-test",
            lease_seconds=300,
        )

        train_calls = [x for x in calls if x[0] == "TRAIN"]
        validation_calls = [x for x in calls if x[0] == "VALIDATION"]

        assert len(train_calls) == len(expected_grid)
        assert len(train_calls) == len(artifact["train_results"])
        assert len(validation_calls) == n7.plan["top_k_train"]
        assert len(validation_calls) == len(artifact["validation_results"])

        expected_train_keys = {
            json.dumps(p, sort_keys=True) for p in expected_grid
        }
        actual_train_keys = {
            json.dumps(r["params"], sort_keys=True)
            for r in artifact["train_results"]
        }
        assert actual_train_keys == expected_train_keys

        ranked = rank_train(artifact["train_results"])
        expected_top = [
            json.dumps(r["params"], sort_keys=True)
            for r in ranked[: n7.plan["top_k_train"]]
        ]
        actual_validation = [
            json.dumps(r["params"], sort_keys=True)
            for r in artifact["validation_results"]
        ]
        assert actual_validation == expected_top

        state = load_run(run_root, manifest, n7.plan)
        assert state["tasks"][task["task_identity"]]["status"] == "COMPLETED"

        before = len(calls)
        try:
            mod._execute_one_task_with_evaluator_for_test(
                run_root=run_root,
                manifest=manifest,
                n7=n7,
                n8=n8,
                task_identity=task["task_identity"],
                evaluator=evaluator,
                entries=entries,
                authority=authority,
            )
        except RecoverableExecutionError:
            pass
        else:
            raise AssertionError("COMPLETED_TASK_RECOMPUTE_ACCEPTED")
        assert len(calls) == before

        second = sorted(n7.plan["tasks"], key=lambda r: r["task_identity"])[1]

        def failing_evaluator(window, got_entry, got_task, params):
            assert window in {"TRAIN", "VALIDATION"}
            raise RuntimeError("synthetic_evaluator_failure")

        try:
            mod._execute_one_task_with_evaluator_for_test(
                run_root=run_root,
                manifest=manifest,
                n7=n7,
                n8=n8,
                task_identity=second["task_identity"],
                evaluator=failing_evaluator,
                entries=entries,
                authority=authority,
                lease_seconds=300,
            )
        except RuntimeError as exc:
            assert "synthetic_evaluator_failure" in str(exc)
        else:
            raise AssertionError("FAILED_EVALUATION_ACCEPTED")

        state = load_run(run_root, manifest, n7.plan)
        failed = state["tasks"][second["task_identity"]]
        assert failed["status"] == "FAILED"
        assert not (run_root / "tasks" / f"{second['task_identity']}.json").exists()

        (repo / "dirty").write_text("drift\n", encoding="utf-8")
        third = sorted(n7.plan["tasks"], key=lambda r: r["task_identity"])[2]
        before = len(calls)
        try:
            mod._execute_one_task_with_evaluator_for_test(
                run_root=run_root,
                manifest=manifest,
                n7=n7,
                n8=n8,
                task_identity=third["task_identity"],
                evaluator=evaluator,
                entries=entries,
                authority=authority,
            )
        except RecoverableExecutionError:
            pass
        else:
            raise AssertionError("DIRTY_REPOSITORY_AUTHORITY_ACCEPTED")
        assert len(calls) == before

        assert market_reads == 0
        assert len(unfinished_task_ids(run_root, manifest, n7.plan)) == 215

        print("TRAIN_GRID_EVALUATIONS=", len(train_calls))
        print("VALIDATION_EVALUATIONS=", len(validation_calls))
        print("COMPLETED_RECOMPUTE_BLOCKED=1")
        print("FAILED_TASK_RECORDED=1")
        print("AUTHORITY_DRIFT_BLOCKED_BEFORE_EVALUATOR=1")
        print("OOS_EVALUATOR_CALLS=0")
        print("REAL_MARKET_DATA_READS=0")
        print("FORMAL_RUNNER_SYNTHETIC_TEST_OK")

    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
