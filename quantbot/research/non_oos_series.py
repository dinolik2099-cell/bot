"""Canonical TRAIN/VALIDATION series evidence for frozen N11 survivors.

This module is diagnostic-only.  It never authorizes OOS, changes ranking,
changes viability rules, or searches parameters.  It replays only the exact
N11 Validation survivors through caller-supplied canonical runtime components.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import numpy as np
import pandas as pd

from quantbot.backtest.costs import CostModel
from quantbot.backtest.engine_v2 import BacktestEngine
from quantbot.research.artifact_store import seal, validate_seal
from quantbot.research.evaluation import evaluate_strategy
from quantbot.research.formal_runner import authorize_n7_window
from quantbot.research.recoverable_execution import validate_task_artifact
from quantbot.research.result_package import validate_evidence_package

SCHEMA_VERSION = "quantbot-non-oos-series-n12-v1"
DIAGNOSTIC_SCHEMA_VERSION = "quantbot-non-oos-homogeneity-n12-v1"
RETAINED_STATE = "RETAINED_FOR_FUTURE_REVIEW"
ALLOWED_WINDOWS = ("TRAIN", "VALIDATION")


class NonOOSSeriesError(RuntimeError):
    pass


@dataclass(frozen=True)
class Candidate:
    candidate_identity: str
    validation_result_identity: str
    selected_train_result_identity: str
    task_identity: str
    model_id: str
    family: str
    symbol: str
    params: dict[str, Any]
    train_metrics: dict[str, Any]
    validation_metrics: dict[str, Any]


def _canon(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _hash(value: Any) -> str:
    return hashlib.sha256(_canon(value).encode("utf-8")).hexdigest()


def _task_state_from_package(package: Mapping[str, Any]) -> dict[str, Any]:
    """Reconstruct only the N10 fields needed by validate_task_artifact()."""
    tasks: dict[str, Any] = {}
    for row in package.get("tasks", []):
        task_id = row.get("task_identity")
        tasks[task_id] = {"attempt_id": row.get("attempt_id")}
    return {
        "run_id": package.get("run_id"),
        "binding": package.get("execution_binding"),
        "tasks": tasks,
    }


def _family_map(plan: Mapping[str, Any]) -> dict[str, str]:
    result = {row.get("model_id"): row.get("family") for row in plan.get("models", [])}
    if not result or any(not isinstance(k, str) or not isinstance(v, str) for k, v in result.items()):
        raise NonOOSSeriesError("frozen_family_metadata_invalid")
    return result


def retained_candidates(package: Mapping[str, Any], plan: Mapping[str, Any]) -> list[Candidate]:
    """Validate authoritative N11 v2 and extract exact retained identities."""
    validate_evidence_package(package)
    if package.get("oos_status") != "SEALED" or package.get("oos_authorization") != "NOT_AUTHORIZED":
        raise NonOOSSeriesError("oos_not_sealed")
    if plan.get("oos_status") != "SEALED" or plan.get("oos_authorization") != "NOT_AUTHORIZED":
        raise NonOOSSeriesError("plan_oos_not_sealed")
    for key in ("research_freeze_identity", "research_plan_identity", "candidate_universe_hash", "boundary_identity_hash"):
        if package.get(key) != plan.get(key):
            raise NonOOSSeriesError(f"n11_plan_{key}_mismatch")
    if package.get("dataset_id") != plan.get("boundary", {}).get("dataset_id"):
        raise NonOOSSeriesError("n11_plan_dataset_mismatch")

    plan_tasks = {row["task_identity"]: row for row in plan.get("tasks", [])}
    state = _task_state_from_package(package)
    families = _family_map(plan)
    out: list[Candidate] = []
    seen_validation: set[str] = set()
    seen_candidates: set[str] = set()

    for artifact in package.get("tasks", []):
        task_id = artifact.get("task_identity")
        task = plan_tasks.get(task_id)
        if task is None:
            raise NonOOSSeriesError("n11_task_not_in_frozen_plan")
        validate_task_artifact(artifact, state, task)
        train_by_params = {_canon(r.get("params")): r for r in artifact.get("train_results", [])}
        rows = artifact.get("validation_results", [])
        validation_ids = artifact.get("validation_result_identities", [])
        selected_ids = artifact.get("selected_train_top_k", [])
        if not (len(rows) == len(validation_ids) == len(selected_ids)):
            raise NonOOSSeriesError("validation_positional_binding_mismatch")

        for row, validation_id, selected_id in zip(rows, validation_ids, selected_ids):
            if row.get("research_state") != RETAINED_STATE:
                continue
            if row.get("oos_authorized") is not False:
                raise NonOOSSeriesError("retained_candidate_oos_authorized")
            params = row.get("params")
            if not isinstance(params, dict):
                raise NonOOSSeriesError("retained_params_invalid")
            metrics = {key: row[key] for key in ("total_return", "max_drawdown", "profit_factor", "trades")}
            train_row = train_by_params.get(_canon(params))
            if train_row is None:
                raise NonOOSSeriesError("retained_train_result_missing")
            train_metrics = {key: train_row[key] for key in ("total_return", "max_drawdown", "profit_factor", "trades")}
            identity_payload = {
                "schema_version": SCHEMA_VERSION,
                "n11_artifact_identity": package["artifact_identity"],
                "validation_result_identity": validation_id,
                "dataset_id": package["dataset_id"],
                "boundary_identity_hash": package["boundary_identity_hash"],
            }
            candidate_id = _hash(identity_payload)
            if validation_id in seen_validation:
                raise NonOOSSeriesError("validation_result_identity_duplicate")
            if candidate_id in seen_candidates:
                raise NonOOSSeriesError("candidate_identity_duplicate")
            seen_validation.add(validation_id); seen_candidates.add(candidate_id)
            out.append(Candidate(
                candidate_identity=candidate_id,
                validation_result_identity=validation_id,
                selected_train_result_identity=selected_id,
                task_identity=task_id,
                model_id=task["model_id"],
                family=families[task["model_id"]],
                symbol=task["symbol"],
                params=dict(params),
                train_metrics=train_metrics,
                validation_metrics=metrics,
            ))
    return sorted(out, key=lambda row: row.candidate_identity)


def metrics_match(actual: Mapping[str, Any], expected: Mapping[str, Any], *, atol: float = 1e-12, rtol: float = 1e-12) -> bool:
    if int(actual["trades"]) != int(expected["trades"]):
        return False
    for key in ("total_return", "max_drawdown", "profit_factor"):
        a = float(actual[key]); e = float(expected[key])
        if math.isinf(a) or math.isinf(e):
            if not (math.isinf(a) and math.isinf(e) and (a > 0) == (e > 0)):
                return False
        elif math.isnan(a) or math.isnan(e) or not math.isclose(a, e, abs_tol=atol, rel_tol=rtol):
            return False
    return True


def replay_candidate(
    candidate: Candidate,
    *,
    window: str,
    n7: Any,
    window_loader: Callable[..., pd.DataFrame],
    strategy_resolver: Callable[[str], Callable[..., pd.DataFrame]],
    engine_factory: Callable[[], BacktestEngine],
) -> dict[str, Any]:
    authorize_n7_window(window)
    if window not in ALLOWED_WINDOWS:
        raise NonOOSSeriesError("window_not_authorized")
    task_index = {row["task_identity"]: row for row in n7.plan["tasks"]}
    task = task_index.get(candidate.task_identity)
    if task is None or task.get("model_id") != candidate.model_id or task.get("symbol") != candidate.symbol:
        raise NonOOSSeriesError("candidate_task_binding_mismatch")
    frame = window_loader(window=window, symbol=candidate.symbol, task=task, boundary=n7.plan["boundary"])
    engine = engine_factory()
    if not isinstance(engine, BacktestEngine) or not isinstance(engine.cost_model, CostModel):
        raise NonOOSSeriesError("canonical_engine_or_cost_model_required")
    strategy = strategy_resolver(candidate.model_id)
    result = evaluate_strategy(
        symbol=candidate.symbol,
        window=window,
        frame=frame,
        strategy=strategy,
        engine=engine,
        params=candidate.params,
        tag=candidate.task_identity,
    )
    metrics = result.backtest.metrics()
    equity = result.backtest.equity_curve.astype(float)
    if equity.empty or not isinstance(equity.index, pd.DatetimeIndex):
        raise NonOOSSeriesError("equity_curve_invalid")
    returns = equity.pct_change(fill_method=None).fillna(0.0)
    ts_ns = equity.index.view("int64")
    equity_values = equity.to_numpy(dtype=np.float64)
    return_values = returns.to_numpy(dtype=np.float64)
    equity_identity = _hash({"timestamps_ns": ts_ns.tolist(), "values": equity_values.tolist()})
    return_identity = _hash({"timestamps_ns": ts_ns.tolist(), "values": return_values.tolist()})
    return {
        "window": window,
        "rows": int(len(equity)),
        "first_timestamp": equity.index[0].isoformat(),
        "last_timestamp": equity.index[-1].isoformat(),
        "metrics": {key: metrics[key] for key in ("total_return", "max_drawdown", "profit_factor", "trades")},
        "timestamps_ns": ts_ns,
        "equity": equity_values,
        "returns": return_values,
        "equity_series_identity": equity_identity,
        "return_series_identity": return_identity,
    }



def replay_candidate_group(
    candidates: Sequence[Candidate],
    *,
    n7: Any,
    window_loader: Callable[..., pd.DataFrame],
    strategy_resolver: Callable[[str], Callable[..., pd.DataFrame]],
    engine_factory: Callable[[], BacktestEngine],
) -> dict[str, dict[str, Any]]:
    """Replay candidates from one frozen model-symbol task, loading each window once."""
    if not candidates:
        return {}
    first = candidates[0]
    if any((c.task_identity, c.model_id, c.symbol) != (first.task_identity, first.model_id, first.symbol) for c in candidates):
        raise NonOOSSeriesError("candidate_group_task_mismatch")
    task_index = {row["task_identity"]: row for row in n7.plan["tasks"]}
    task = task_index.get(first.task_identity)
    if task is None or task.get("model_id") != first.model_id or task.get("symbol") != first.symbol:
        raise NonOOSSeriesError("candidate_task_binding_mismatch")
    strategy = strategy_resolver(first.model_id)
    frames = {}
    for window in ALLOWED_WINDOWS:
        authorize_n7_window(window)
        frames[window] = window_loader(window=window, symbol=first.symbol, task=task, boundary=n7.plan["boundary"])
    output: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        by_window = {}
        for window in ALLOWED_WINDOWS:
            engine = engine_factory()
            if not isinstance(engine, BacktestEngine) or not isinstance(engine.cost_model, CostModel):
                raise NonOOSSeriesError("canonical_engine_or_cost_model_required")
            result = evaluate_strategy(
                symbol=candidate.symbol, window=window, frame=frames[window], strategy=strategy,
                engine=engine, params=candidate.params, tag=candidate.task_identity,
            )
            metrics = result.backtest.metrics(); equity = result.backtest.equity_curve.astype(float)
            if equity.empty or not isinstance(equity.index, pd.DatetimeIndex):
                raise NonOOSSeriesError("equity_curve_invalid")
            returns = equity.pct_change(fill_method=None).fillna(0.0)
            ts_ns = equity.index.view("int64"); eq = equity.to_numpy(dtype=np.float64); ret = returns.to_numpy(dtype=np.float64)
            by_window[window] = {
                "window": window, "rows": int(len(equity)), "first_timestamp": equity.index[0].isoformat(),
                "last_timestamp": equity.index[-1].isoformat(),
                "metrics": {key: metrics[key] for key in ("total_return", "max_drawdown", "profit_factor", "trades")},
                "timestamps_ns": ts_ns, "equity": eq, "returns": ret,
                "equity_series_identity": _hash({"timestamps_ns": ts_ns.tolist(), "values": eq.tolist()}),
                "return_series_identity": _hash({"timestamps_ns": ts_ns.tolist(), "values": ret.tolist()}),
            }
        output[candidate.candidate_identity] = by_window
    return output

def series_metadata(candidate: Candidate, replay: Mapping[str, Any], package: Mapping[str, Any]) -> dict[str, Any]:
    payload = {
        "schema_version": SCHEMA_VERSION,
        "candidate_identity": candidate.candidate_identity,
        "validation_result_identity": candidate.validation_result_identity,
        "selected_train_result_identity": candidate.selected_train_result_identity,
        "task_identity": candidate.task_identity,
        "model_id": candidate.model_id,
        "family": candidate.family,
        "symbol": candidate.symbol,
        "params": candidate.params,
        "window": replay["window"],
        "n11_artifact_identity": package["artifact_identity"],
        "n9_manifest_identity": package["n9_manifest_identity"],
        "n10_run_id": package["run_id"],
        "research_freeze_identity": package["research_freeze_identity"],
        "research_plan_identity": package["research_plan_identity"],
        "dataset_id": package["dataset_id"],
        "boundary_identity_hash": package["boundary_identity_hash"],
        "engine_identity": package["environment"]["engine"],
        "cost_model_identity": package["environment"]["cost_model"],
        "rows": replay["rows"],
        "first_timestamp": replay["first_timestamp"],
        "last_timestamp": replay["last_timestamp"],
        "equity_series_identity": replay["equity_series_identity"],
        "return_series_identity": replay["return_series_identity"],
        "oos_status": "SEALED",
        "oos_authorization": "NOT_AUTHORIZED",
    }
    payload["series_identity"] = _hash(payload)
    return payload


def aligned_correlation(series: Sequence[tuple[np.ndarray, np.ndarray]]) -> np.ndarray:
    """Correlation over already-aligned timestamp/return arrays, fail closed otherwise."""
    if not series:
        return np.empty((0, 0), dtype=float)
    base = series[0][0]
    for ts, values in series:
        if not np.array_equal(ts, base) or len(values) != len(base):
            raise NonOOSSeriesError("return_series_alignment_mismatch")
    matrix = np.column_stack([values for _, values in series])
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.corrcoef(matrix, rowvar=False)


def _finite_pair_values(corr: np.ndarray) -> np.ndarray:
    if corr.shape[0] < 2:
        return np.array([], dtype=float)
    values = corr[np.triu_indices(corr.shape[0], k=1)]
    return values[np.isfinite(values)]


def correlation_summary(corr: np.ndarray) -> dict[str, Any]:
    values = _finite_pair_values(corr)
    if not len(values):
        return {"pairs": 0, "finite_pairs": 0, "mean": None, "median": None, "p90": None, "ge_0_90": 0, "ge_0_98": 0}
    return {
        "pairs": int(corr.shape[0] * (corr.shape[0] - 1) // 2),
        "finite_pairs": int(len(values)),
        "mean": float(np.mean(values)),
        "median": float(np.median(values)),
        "p90": float(np.quantile(values, 0.90)),
        "ge_0_90": int(np.sum(values >= 0.90)),
        "ge_0_98": int(np.sum(values >= 0.98)),
    }


def near_duplicate_components(corr: np.ndarray, threshold: float = 0.98) -> list[list[int]]:
    n = corr.shape[0]; seen: set[int] = set(); groups: list[list[int]] = []
    for start in range(n):
        if start in seen: continue
        stack = [start]; component: list[int] = []
        while stack:
            i = stack.pop()
            if i in seen: continue
            seen.add(i); component.append(i)
            for j in range(n):
                if j not in seen and i != j and np.isfinite(corr[i, j]) and corr[i, j] >= threshold:
                    stack.append(j)
        groups.append(sorted(component))
    return groups


def build_diagnostic_artifact(
    *, package: Mapping[str, Any], candidates: Sequence[Candidate], validation_corr: np.ndarray,
    group_summaries: Mapping[str, Any], replay_matches: int, replay_mismatches: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    groups = near_duplicate_components(validation_corr, 0.98)
    payload = {
        "schema_version": DIAGNOSTIC_SCHEMA_VERSION,
        "input_n11_artifact_identity": package["artifact_identity"],
        "candidate_count": len(candidates),
        "validation_correlation": correlation_summary(validation_corr),
        "near_duplicate_threshold": 0.98,
        "near_duplicate_cluster_count": sum(len(g) > 1 for g in groups),
        "effective_component_count_at_0_98": len(groups),
        "replay_verification": {"matches": replay_matches, "mismatches": len(replay_mismatches), "details": list(replay_mismatches)},
        "group_summaries": dict(group_summaries),
        "oos_status": "SEALED",
        "oos_authorization": "NOT_AUTHORIZED",
        "selection_rule_changed": False,
    }
    return seal(payload)


def validate_diagnostic_artifact(payload: Mapping[str, Any]) -> bool:
    if payload.get("schema_version") != DIAGNOSTIC_SCHEMA_VERSION:
        raise NonOOSSeriesError("diagnostic_schema_invalid")
    validate_seal(payload)
    if payload.get("oos_status") != "SEALED" or payload.get("oos_authorization") != "NOT_AUTHORIZED":
        raise NonOOSSeriesError("diagnostic_oos_not_sealed")
    if payload.get("selection_rule_changed") is not False:
        raise NonOOSSeriesError("diagnostic_selection_rule_changed")
    return True
