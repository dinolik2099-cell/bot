"""Formal recoverable TRAIN/VALIDATION runner.

N8 canonical market-data access + N9 continuous authorization +
N10 recoverable task execution + N11 immutable evidence packaging.

OOS is not an accepted execution window.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import multiprocessing
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quantbot.backtest.costs import CostModel
from quantbot.backtest.engine_v2 import BacktestEngine
from quantbot.research.canonical_data_adapter import (
    load_n8_data_context,
    make_n8_canonical_window_loader,
)
from quantbot.research.formal_execution_manifest import (
    build_manifest,
    preflight_authorize,
    repository_state,
)
from quantbot.research.formal_runner import (
    load_n7_context,
    make_n7_canonical_evaluator,
)
from quantbot.research.model_registry import (
    list_models,
    register_existing_models,
    validate_registry,
)
from quantbot.research.plan_executor import frozen_grid, rank_train, validate_metrics
from quantbot.research.recoverable_execution import (
    claim_task,
    complete_task,
    execution_binding,
    fail_task,
    final_result_identity,
    initialize_run,
    load_run,
    task_result_payload,
    unfinished_task_ids,
    validate_task_artifact,
)
from quantbot.research.result_package import (
    build_evidence_package,
    validate_evidence_package,
)
from quantbot.research.formal_parallel import (
    apply_worker_thread_limits,
    execute_formal_task_payload,
    frozen_worker_config,
    resolve_workers,
)

PLAN = ROOT / "docs/handoff/FROZEN_RESEARCH_PLAN_N5.json"
FREEZE = ROOT / "docs/handoff/CANDIDATE_UNIVERSE_FREEZE_N3.json"
LOCK = ROOT / "data/reports/research_boundary_lock.json"
RAW_ROOT = ROOT / "data/raw"


def canonical_model_map():
    from quantbot.research.model_registry import _REGISTRY
    from quantbot.strategies.model_pool import register_model_pool

    snapshot = dict(_REGISTRY)
    try:
        _REGISTRY.clear()
        register_existing_models()
        register_model_pool()
        validate_registry()
        rows = list_models()
        by_id = {row.spec.model_id: row for row in rows}
        if len(by_id) != len(rows):
            raise RuntimeError("duplicate_model_id")
        return by_id
    finally:
        _REGISTRY.clear()
        _REGISTRY.update(snapshot)


def make_strategy_resolver(expected_model_ids):
    by_id = canonical_model_map()
    expected = set(expected_model_ids)
    if set(by_id) != expected:
        raise RuntimeError("formal_model_universe_mismatch")

    def resolve(model_id):
        if model_id not in expected:
            raise RuntimeError("formal_model_not_frozen")
        return by_id[model_id].strategy

    return resolve


def engine_factory():
    return BacktestEngine(
        initial_equity=10_000.0,
        cost_model=CostModel(),
    )


def entry_index(n7):
    rows = {entry.model_id: entry for entry in n7.entries}
    frozen = {row["model_id"] for row in n7.plan["models"]}
    if set(rows) != frozen:
        raise RuntimeError("formal_entry_universe_mismatch")
    return rows


def _execute_one_task_with_evaluator_for_test(
    *,
    run_root,
    manifest,
    n7,
    n8,
    task_identity,
    evaluator,
    entries,
    authority,
    owner="formal-local",
    lease_seconds=3600,
):
    plan = n7.plan
    tasks = {row["task_identity"]: row for row in plan["tasks"]}
    task = tasks.get(task_identity)
    if task is None:
        raise RuntimeError("formal_unknown_task")

    entry = entries.get(task["model_id"])
    if entry is None:
        raise RuntimeError("formal_task_model_missing")

    claim_task(
        run_root,
        manifest,
        plan,
        task_identity,
        owner=owner,
        lease_seconds=lease_seconds,
        authority=authority,
    )

    try:
        train_results = []
        for params in frozen_grid(entry):
            metrics = validate_metrics(
                evaluator("TRAIN", entry, task, params)
            )
            train_results.append({"params": params, **metrics})

        ranked = rank_train(train_results)
        top = ranked[: plan["top_k_train"]]

        validation_results = []
        for row in top:
            params = row["params"]
            metrics = validate_metrics(
                evaluator("VALIDATION", entry, task, params)
            )
            retained = (
                metrics["total_return"] > 0
                and metrics["profit_factor"] >= 1.0
            )
            validation_results.append(
                {
                    "params": params,
                    **metrics,
                    "research_state": (
                        "RETAINED_FOR_FUTURE_REVIEW"
                        if retained
                        else "HOLD"
                    ),
                    "oos_authorized": False,
                }
            )

        state = load_run(run_root, manifest, plan)
        artifact = task_result_payload(
            state,
            plan,
            task_identity,
            status="COMPLETED",
            train_results=train_results,
            validation_results=validation_results,
        )

        validate_task_artifact(artifact, state, task)

        complete_task(
            run_root,
            manifest,
            plan,
            artifact,
            authority=authority,
        )

        return artifact

    except Exception as exc:
        try:
            fail_task(
                run_root,
                manifest,
                plan,
                task_identity,
                type(exc).__name__,
                str(exc),
                authority=authority,
            )
        except Exception as fail_exc:
            raise RuntimeError(
                "formal_task_failed_and_failure_recording_failed"
            ) from fail_exc
        raise



def execute_one_task(
    *,
    run_root,
    manifest,
    n7,
    n8,
    task_identity,
    authority,
    owner="formal-local",
    lease_seconds=3600,
):
    """Production task entrypoint.

    The caller cannot inject an evaluator, strategy resolver, frame loader,
    raw-data root, or model-entry mapping.  Those components are constructed
    here from the frozen N7/N8 research context and canonical runtime only.
    """
    expected_model_ids = [
        row["model_id"]
        for row in n7.plan["models"]
    ]

    entries = entry_index(n7)

    strategy_resolver = make_strategy_resolver(
        expected_model_ids
    )

    window_loader = make_n8_canonical_window_loader(
        n8,
        RAW_ROOT,
    )

    evaluator = make_n7_canonical_evaluator(
        n7,
        window_loader,
        strategy_resolver,
        engine_factory,
    )

    return _execute_one_task_with_evaluator_for_test(
        run_root=run_root,
        manifest=manifest,
        n7=n7,
        n8=n8,
        task_identity=task_identity,
        evaluator=evaluator,
        entries=entries,
        authority=authority,
        owner=owner,
        lease_seconds=lease_seconds,
    )



# ---------------------------------------------------------------------------
# Formal orchestration / finalization
# ---------------------------------------------------------------------------

import argparse
import platform
import sys
from datetime import datetime, timezone

from quantbot.research.canonical_data_adapter import (
    make_n8_canonical_window_loader,
)
from quantbot.research.artifact_store import read_verified_json, seal, write_named_new_json


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def formal_output_destination():
    return "data/reports/formal_runs/N11_FORMAL_TRAIN_VALIDATION_RESULT.json"


def formal_launch_destination():
    return "data/reports/formal_runs/N11_FORMAL_TRAIN_VALIDATION_LAUNCH.json"


def formal_launch_path():
    return ROOT / formal_launch_destination()


def load_or_create_launch_manifest(n7, n8, requested_workers=None):
    launch_path = formal_launch_path()

    if launch_path.exists():
        descriptor = read_verified_json(launch_path)
        if descriptor.get("schema_version") != "quantbot-formal-launch-v1":
            raise RuntimeError("formal_launch_schema_invalid")

        manifest = descriptor.get("manifest")
        if not isinstance(manifest, dict):
            raise RuntimeError("formal_launch_manifest_invalid")

        frozen_workers = manifest.get("worker_config", {}).get("workers")
        if type(frozen_workers) is not int or frozen_workers < 1:
            raise RuntimeError("formal_launch_worker_config_invalid")

        if requested_workers is not None and requested_workers != frozen_workers:
            raise RuntimeError("formal_frozen_worker_request_mismatch")

        authority = authorize_manifest(manifest, n7, n8)
        return manifest, authority

    resolution = resolve_workers(requested_cap=requested_workers)
    worker_config = frozen_worker_config(resolution)
    manifest = build_current_manifest(n7, n8, worker_config)
    authority = authorize_manifest(manifest, n7, n8)

    descriptor = seal(
        {
            "schema_version": "quantbot-formal-launch-v1",
            "manifest": manifest,
        }
    )

    relative = Path(formal_launch_destination())
    write_named_new_json(
        ROOT / relative.parent,
        relative.name,
        descriptor,
    )
    return manifest, authority


def build_authority(manifest, n7, n8):
    return {
        "n7": n7,
        "n8": n8,
        "repo_root": ROOT,
        "requested_windows": {
            "TRAIN": manifest["train_window"],
            "VALIDATION": manifest["validation_window"],
        },
        "output_path": manifest["output"]["destination"],
        "requested_workers": manifest["worker_config"]["workers"],
    }


def load_formal_context():
    boundary_lock = json.loads(LOCK.read_text(encoding="utf-8"))
    n7 = load_n7_context(PLAN, FREEZE, boundary_lock)
    n8 = load_n8_data_context(n7, LOCK)
    return n7, n8


def build_current_manifest(n7, n8, worker_config):
    repo = repository_state(ROOT)
    if not repo["clean"]:
        raise RuntimeError("formal_source_tree_not_clean")

    return build_manifest(
        n7,
        n8,
        source_git_commit=repo["commit"],
        worker_config=worker_config,
        output_destination=formal_output_destination(),
        created_at=utc_now(),
    )


def authorize_manifest(manifest, n7, n8):
    authority = build_authority(manifest, n7, n8)

    result = preflight_authorize(
        manifest,
        n7,
        n8,
        repo_root=ROOT,
        requested_windows=authority["requested_windows"],
        output_path=authority["output_path"],
        requested_workers=manifest["worker_config"]["workers"],
    )

    if result.get("market_data_reads") != 0:
        raise RuntimeError("n9_preflight_market_data_read_violation")

    return authority


def runtime_root_for(manifest):
    identity = manifest["manifest_identity"]
    if not isinstance(identity, str) or len(identity) != 64:
        raise RuntimeError("formal_manifest_identity_invalid")

    return (
        ROOT
        / "data/reports/formal_runs/runtime"
        / identity
    )


def initialize_or_resume(run_root, manifest, n7, n8):
    state_path = run_root / "run_state.json"

    if state_path.exists():
        return load_run(run_root, manifest, n7.plan)

    return initialize_run(
        run_root,
        manifest,
        n7.plan,
        n7=n7,
        n8=n8,
        repo_root=ROOT,
    )


def validated_task_artifacts(run_root, manifest, n7):
    state = load_run(run_root, manifest, n7.plan)
    task_index = {
        task["task_identity"]: task
        for task in n7.plan["tasks"]
    }

    if state.get("accounting", {}).get("completed_count") != len(task_index):
        raise RuntimeError("formal_run_not_complete")

    if state.get("accounting", {}).get("failed_count") != 0:
        raise RuntimeError("formal_run_contains_failed_tasks")

    artifacts = []

    for task_identity in sorted(task_index):
        path = run_root / "tasks" / f"{task_identity}.json"
        if not path.is_file():
            raise RuntimeError("formal_completed_task_artifact_missing")

        artifact = json.loads(path.read_text(encoding="utf-8"))

        validate_task_artifact(
            artifact,
            state,
            task_index[task_identity],
        )

        artifacts.append(artifact)

    if len(artifacts) != 216:
        raise RuntimeError("formal_task_artifact_count_invalid")

    return state, artifacts


def finalize_n11(run_root, manifest, n7, n8):
    # Reauthorize immediately before final packaging.  At this point the
    # immutable N9 destination must still not exist.
    authorize_manifest(manifest, n7, n8)

    state, artifacts = validated_task_artifacts(
        run_root,
        manifest,
        n7,
    )

    final_identity = final_result_identity(
        run_root,
        manifest,
        n7.plan,
    )

    binding = execution_binding(
        manifest,
        n7.plan,
        n7=n7,
        n8=n8,
    )

    if state.get("binding") != binding:
        raise RuntimeError("formal_execution_binding_drift")

    package = build_evidence_package(
        run_state=state,
        execution_binding=binding,
        task_artifacts=artifacts,
        authority_manifest=manifest,
        source_git_commit=manifest["source_git_commit"],
        environment={
            "python": sys.version,
            "platform": platform.platform(),
            "runner": "scripts/run_formal_train_validation.py",
            "workers": manifest["worker_config"]["workers"],
            "worker_config": manifest["worker_config"],
            "engine": "quantbot.backtest.engine_v2.BacktestEngine",
            "cost_model": "quantbot.backtest.costs.CostModel",
            "data_adapter": "quantbot.research.canonical_data_adapter",
            "n10_final_result_identity": final_identity,
        },
        created_at=utc_now(),
    )

    validate_evidence_package(
        package,
        expected_run_id=state["run_id"],
        expected_manifest_identity=manifest["manifest_identity"],
    )

    relative = Path(manifest["output"]["destination"])

    if (
        relative.is_absolute()
        or ".." in relative.parts
        or relative.parent
        != Path("data/reports/formal_runs")
    ):
        raise RuntimeError("formal_output_destination_invalid")

    output_root = ROOT / relative.parent

    output_path = write_named_new_json(
        output_root,
        relative.name,
        package,
    )

    return {
        "output_path": str(output_path),
        "artifact_identity": package["artifact_identity"],
        "run_id": state["run_id"],
        "final_result_identity": final_identity,
        "manifest_identity": manifest["manifest_identity"],
        "counts": package["counts"],
    }


def run_formal_train_validation(*, requested_workers=None):
    # Thread limits are process-local.  Formal worker-count/resource policy is
    # frozen by the immutable launch descriptor on first execution and reused
    # verbatim on every recovery invocation.
    apply_worker_thread_limits()
    n7, n8 = load_formal_context()

    if (
        n7.plan.get("oos_status") != "SEALED"
        or n7.plan.get("oos_authorization") != "NOT_AUTHORIZED"
    ):
        raise RuntimeError("formal_oos_not_sealed")

    manifest, authority = load_or_create_launch_manifest(
        n7,
        n8,
        requested_workers=requested_workers,
    )
    worker_config = manifest["worker_config"]

    run_root = runtime_root_for(manifest)

    initialize_or_resume(
        run_root,
        manifest,
        n7,
        n8,
    )

    initial_unfinished = unfinished_task_ids(
        run_root,
        manifest,
        n7.plan,
    )

    print(f"FORMAL_HEAD={manifest['source_git_commit']}")
    print(f"N9_MANIFEST_IDENTITY={manifest['manifest_identity']}")
    print(f"N10_RUN_ROOT={run_root}")
    print(f"TASKS_TOTAL={len(n7.plan['tasks'])}")
    print(f"TASKS_UNFINISHED_AT_START={len(initial_unfinished)}")
    print(f"RESOLVED_WORKERS={worker_config['workers']}")
    print(f"WORKER_CONFIG={json.dumps(worker_config, sort_keys=True)}")
    print("WINDOWS=TRAIN,VALIDATION")
    print("OOS_STATUS=SEALED")
    print("OOS_AUTHORIZATION=NOT_AUTHORIZED")

    task_rows={row["task_identity"]:row for row in n7.plan["tasks"]}
    payloads=[]
    for task_identity in initial_unfinished:
        task=task_rows[task_identity]
        print(f"TASK_QUEUED={task_identity} {task['model_id']} {task['symbol']}",flush=True)
        payloads.append({"repo_root":str(ROOT),"run_root":str(run_root),"manifest":manifest,"task_identity":task_identity,"owner":"formal-train-validation","lease_seconds":3600})
    # ProcessPoolExecutor is used deliberately: BacktestEngine CPU work is not
    # run in a thread pool. Spawn keeps child state independent/picklable.
    if payloads:
        context=multiprocessing.get_context("spawn")
        with ProcessPoolExecutor(max_workers=worker_config["workers"],mp_context=context) as pool:
            futures={pool.submit(execute_formal_task_payload,payload):payload["task_identity"] for payload in payloads}
            for future in as_completed(futures):
                task_identity=futures[future]
                try: result=future.result()
                except Exception as exc: raise RuntimeError(f"formal_worker_failed:{task_identity}") from exc
                state=load_run(run_root,manifest,n7.plan); accounting=state["accounting"]
                print(f"TASK_COMPLETE={result['task_identity']} completed={accounting['completed_count']}/216 failed={accounting['failed_count']} worker_pid={result['worker_pid']}",flush=True)

    remaining = unfinished_task_ids(
        run_root,
        manifest,
        n7.plan,
    )

    if remaining:
        raise RuntimeError(
            f"formal_tasks_still_unfinished:{len(remaining)}"
        )

    result = finalize_n11(
        run_root,
        manifest,
        n7,
        n8,
    )

    print("FORMAL_TRAIN_VALIDATION_COMPLETE")
    print(f"N11_OUTPUT={result['output_path']}")
    print(f"N11_ARTIFACT_IDENTITY={result['artifact_identity']}")
    print(f"N10_RUN_ID={result['run_id']}")
    print(
        "N10_FINAL_RESULT_IDENTITY="
        f"{result['final_result_identity']}"
    )
    print(f"N9_MANIFEST_IDENTITY={result['manifest_identity']}")
    print(f"COUNTS={json.dumps(result['counts'], sort_keys=True)}")
    print("OOS_STATUS=SEALED")
    print("OOS_AUTHORIZATION=NOT_AUTHORIZED")

    return result


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Formal frozen TRAIN/VALIDATION execution. "
            "OOS is structurally unauthorized."
        )
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="explicitly authorize this CLI invocation to execute TRAIN/VALIDATION",
    )
    parser.add_argument("--workers",type=int,default=None,help="optional bounded cap; resolver still applies CPU/RAM budgets and hard cap 16")
    args = parser.parse_args()

    if not args.execute:
        print("FORMAL_EXECUTION_NOT_STARTED")
        print("Pass --execute only after the committed clean launch audit.")
        return 2

    run_formal_train_validation(requested_workers=args.workers)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
