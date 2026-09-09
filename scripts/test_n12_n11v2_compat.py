from copy import deepcopy

from quantbot.research.artifact_store import seal
from quantbot.research.diagnostics import build_diagnostics, validate_diagnostics
from quantbot.research.result_package import build_result_package


def blocked(fn):
    try:
        fn()
    except Exception:
        return
    raise AssertionError("expected rejection")


def make_v1():
    binding = {
        "research_freeze_identity": "f" * 64,
        "research_plan_identity": "p" * 64,
        "candidate_universe_hash": "c" * 64,
        "dataset_id": "synthetic",
        "boundary_identity_hash": "b" * 64,
        "counts": {"model_symbol_cells": 1},
        "oos_status": "SEALED",
        "oos_authorization": "NOT_AUTHORIZED",
    }
    tasks = [{
        "task_identity": "1" * 64,
        "status": "COMPLETED",
        "actual_train_evaluations": 2,
        "actual_validation_evaluations": 1,
        "model_id": "m1",
        "symbol": "BTCUSDT",
        "family": "trend",
        "train": [{"params": {"x": 1}}, {"params": {"x": 2}}],
        "validation": [{
            "total_return": 0.1,
            "profit_factor": 1.2,
            "max_drawdown": 0.02,
            "trades": 12,
            "params": {"x": 1},
        }],
    }]
    return build_result_package(
        run_id="r" * 64,
        execution_binding=binding,
        task_artifacts=tasks,
        recovery_state={"revision": 1},
        source_git_commit="g" * 40,
    )


def make_v2():
    run_id = "r" * 64
    manifest_id = "m" * 64
    task_id = "1" * 64
    result_hash = "a" * 64
    task = {
        "task_identity": task_id,
        "run_id": run_id,
        "manifest_identity": manifest_id,
        "result_hash": result_hash,
        "status": "COMPLETED",
        "actual_train_evaluations": 2,
        "actual_validation_evaluations": 1,
        "model_id": "m1",
        "symbol": "BTCUSDT",
        "family": "trend",
        "train": [{"params": {"x": 1}}, {"params": {"x": 2}}],
        "validation": [{
            "total_return": 0.1,
            "profit_factor": 1.2,
            "max_drawdown": 0.02,
            "trades": 12,
            "params": {"x": 1},
        }],
    }
    return seal({
        "schema_version": "quantbot-research-result-package-n11-v2",
        "run_id": run_id,
        "n10_execution_identity": run_id,
        "n9_manifest_identity": manifest_id,
        "source_git_commit": "g" * 40,
        "research_freeze_identity": "f" * 64,
        "research_plan_identity": "p" * 64,
        "candidate_universe_hash": "c" * 64,
        "dataset_id": "synthetic",
        "boundary_identity_hash": "b" * 64,
        "execution_binding": {},
        "authority": {},
        "recovery": {},
        "tasks": [task],
        "checksums": {task_id: result_hash},
        "counts": {"tasks": 1, "train": 2, "validation": 1},
        "oos_status": "SEALED",
        "oos_authorization": "NOT_AUTHORIZED",
    })


def main():
    v1 = make_v1()
    d1 = build_diagnostics(v1)
    assert validate_diagnostics(d1, v1)

    v2 = make_v2()
    d2 = build_diagnostics(v2)
    assert validate_diagnostics(d2, v2)

    inf_v2 = make_v2()
    inf_v2["tasks"][0]["validation"][0]["profit_factor"] = float("inf")
    inf_v2 = seal({k: v for k, v in inf_v2.items() if k != "artifact_identity"})
    inf_d = build_diagnostics(inf_v2)
    inf_row = inf_d["task_diagnostics"][0]
    assert inf_row["profit_factor"] == float("inf")
    assert inf_row["profit_factor_finite_mean"] is None
    assert inf_row["profit_factor_finite_count"] == 0
    assert inf_row["profit_factor_nonfinite_count"] == 1

    unknown = deepcopy(v2)
    unknown["schema_version"] = "unknown"
    unknown = seal({k: v for k, v in unknown.items() if k != "artifact_identity"})
    blocked(lambda: build_diagnostics(unknown))

    tampered = deepcopy(v2)
    tampered["tasks"][0]["status"] = "FAILED"
    blocked(lambda: build_diagnostics(tampered))

    opened = deepcopy(v2)
    opened["oos_status"] = "OPEN"
    opened = seal({k: v for k, v in opened.items() if k != "artifact_identity"})
    blocked(lambda: build_diagnostics(opened))

    print("N12_N11V2_COMPAT_TEST_OK")


if __name__ == "__main__":
    main()
