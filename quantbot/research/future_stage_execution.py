"""Identity-bound execution coordination for authorized non-OOS future stages.

This module is deliberately small and contains no market-data implementation.
Public stage runners construct their own canonical executor before calling the
private coordinator below.  The coordinator owns deterministic ordering,
checkpoint/resume, and complete-only result sealing; it never accepts an OOS
work unit and cannot turn a partial execution into a final result.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence

from .artifact_store import seal
from .future_data_plane import FutureDataPlaneError, FutureRuntimeContext
from .future_stages import ResumableStageState, StageState


class FutureStageExecutionError(RuntimeError):
    pass


ChunkExecutor = Callable[[Mapping[str, Any]], Mapping[str, Any]]


@dataclass(frozen=True)
class FutureStageExecution:
    """A recoverable execution snapshot.

    ``result`` is populated only if every frozen chunk completed.  Consumers
    must therefore treat a checkpoint with FAILED/INTERRUPTED state as
    diagnostic material, never as a completed research artifact.
    """

    state: ResumableStageState
    checkpoint: Mapping[str, Any]
    rows: tuple[Mapping[str, Any], ...]
    result: Mapping[str, Any] | None


def _row_identity(*, runtime: FutureRuntimeContext, chunk: Mapping[str, Any], evidence: Mapping[str, Any]) -> str:
    return seal({
        "schema_version": "quantbot-future-stage-chunk-result-v1",
        "stage": runtime.protocol["stage"],
        "chunk_identity": chunk["chunk_identity"],
        "protocol_identity": runtime.protocol["artifact_identity"],
        "execution_plan_identity": runtime.plan["artifact_identity"],
        "input_identity": runtime.input_identity,
        "window": "TRAIN_VALIDATION",
        "evidence": dict(evidence),
        "oos_status": "SEALED",
        "oos_authorization": "NOT_AUTHORIZED",
    })["artifact_identity"]


def _validate_resume(runtime: FutureRuntimeContext, checkpoint: Mapping[str, Any] | None) -> ResumableStageState:
    if checkpoint is None:
        return ResumableStageState(runtime.protocol["artifact_identity"])
    state = runtime.validate_checkpoint(checkpoint)
    if state.state == StageState.COMPLETE:
        raise FutureStageExecutionError("future_stage_already_complete")
    if state.state == StageState.RUNNING:
        # A persisted RUNNING state is recovered as interrupted; no implicit
        # claim survives a process boundary.
        return ResumableStageState(state.protocol_identity, StageState.INTERRUPTED, state.completed_chunks, state.failed_chunks)
    return state


def _completed_rows(runtime: FutureRuntimeContext, rows: Sequence[Mapping[str, Any]], state: ResumableStageState) -> None:
    expected = set(state.completed_chunks)
    actual = {row.get("chunk_identity") for row in rows}
    if actual != expected or len(rows) != len(actual):
        raise FutureStageExecutionError("future_stage_resume_rows_invalid")
    for row in rows:
        if row.get("status") != "COMPLETED" or row.get("result_identity") != _row_identity(
            runtime=runtime,
            chunk={"chunk_identity": row.get("chunk_identity")},
            evidence=row.get("evidence") if isinstance(row.get("evidence"), Mapping) else {},
        ):
            raise FutureStageExecutionError("future_stage_resume_row_identity_invalid")


def _execute_verified_chunks(
    *,
    runtime: FutureRuntimeContext,
    source_git_commit: str,
    executor: ChunkExecutor,
    checkpoint: Mapping[str, Any] | None = None,
    prior_rows: Sequence[Mapping[str, Any]] = (),
    retry_failed: bool = False,
) -> FutureStageExecution:
    """Private coordinator used only by structurally canonical stage runners.

    Tests may exercise this function with a synthetic executor, but public
    production entrypoints below do not expose that injection point.
    """
    runtime.validate()
    if not isinstance(source_git_commit, str) or len(source_git_commit) != 40:
        raise FutureStageExecutionError("future_stage_source_git_commit_invalid")
    prior_state = _validate_resume(runtime, checkpoint)
    # Retrying failed chunks is an explicit coordinator choice, never an
    # implicit side effect of loading a checkpoint.  The immutable checkpoint
    # remains the diagnostic record of the failed attempt; the new checkpoint
    # starts a fenced retry attempt with the already-completed set unchanged.
    if retry_failed and prior_state.failed_chunks:
        prior_state = ResumableStageState(prior_state.protocol_identity, StageState.INTERRUPTED, prior_state.completed_chunks, ())
    state = prior_state.resume()
    rows = [dict(row) for row in prior_rows]
    _completed_rows(runtime, rows, ResumableStageState(state.protocol_identity, state.state, state.completed_chunks, ()))
    chunks = tuple(sorted(runtime.plan["chunks"], key=lambda row: row["ordinal"]))
    expected = tuple(row["chunk_identity"] for row in chunks)
    if (set(state.completed_chunks) | set(state.failed_chunks)) - set(expected):
        raise FutureStageExecutionError("future_stage_checkpoint_chunk_drift")
    for chunk in chunks:
        identity = chunk["chunk_identity"]
        if identity in state.completed_chunks or identity in state.failed_chunks:
            continue
        try:
            evidence = executor(dict(chunk))
            if not isinstance(evidence, Mapping):
                raise FutureStageExecutionError("future_stage_executor_evidence_invalid")
            row = {
                "chunk_identity": identity,
                "status": "COMPLETED",
                "window": "TRAIN_VALIDATION",
                "protocol_identity": runtime.protocol["artifact_identity"],
                "execution_plan_identity": runtime.plan["artifact_identity"],
                "input_identity": runtime.input_identity,
                "evidence": dict(evidence),
                "oos_status": "SEALED",
                "oos_authorization": "NOT_AUTHORIZED",
            }
            row["result_identity"] = _row_identity(runtime=runtime, chunk=chunk, evidence=row["evidence"])
            rows.append(row)
            state = state.record(identity, succeeded=True)
        except Exception:
            state = state.record(identity, succeeded=False)
            break
    if len(set(state.completed_chunks) | set(state.failed_chunks)) == len(expected):
        state = state.finish(expected)
    else:
        state = ResumableStageState(state.protocol_identity, StageState.INTERRUPTED, state.completed_chunks, state.failed_chunks)
    sealed_checkpoint = runtime.checkpoint(state)
    if state.state != StageState.COMPLETE:
        return FutureStageExecution(state, sealed_checkpoint, tuple(sorted(rows, key=lambda row: row["chunk_identity"])), None)
    result = runtime.result(rows, source_git_commit)
    return FutureStageExecution(state, sealed_checkpoint, tuple(sorted(rows, key=lambda row: row["chunk_identity"])), result)


def validate_future_stage_execution(execution: FutureStageExecution, *, runtime: FutureRuntimeContext) -> bool:
    state = runtime.validate_checkpoint(execution.checkpoint)
    if (state.protocol_identity != execution.state.protocol_identity or state.state != execution.state.state
            or set(state.completed_chunks) != set(execution.state.completed_chunks)
            or set(state.failed_chunks) != set(execution.state.failed_chunks)):
        raise FutureStageExecutionError("future_stage_execution_checkpoint_mismatch")
    if execution.result is None:
        if execution.state.state == StageState.COMPLETE:
            raise FutureStageExecutionError("future_stage_complete_result_missing")
        return True
    if execution.state.state != StageState.COMPLETE:
        raise FutureStageExecutionError("future_stage_partial_result_forbidden")
    return runtime.validate_result(execution.result)


def make_canonical_plan_chunk_executor(*, runtime: FutureRuntimeContext, n8_context, evaluator) -> ChunkExecutor:
    """Build a concrete N5 task executor for a canonical N7/N8 evaluator.

    The executor is intentionally constructed from the verified N8 context,
    not supplied by callers to a formal stage entrypoint.  Each frozen N5 task
    is assigned to exactly one predeclared chunk by its stable sorted ordinal.
    Within a task it evaluates the complete frozen TRAIN grid, ranks it with
    the accepted deterministic ranking, and sends only the fixed Top-K into
    VALIDATION.  No grid, window, or task discovery is performed here.
    """
    runtime.validate()
    plan = n8_context.n7.plan
    entries = {entry.model_id: entry for entry in n8_context.n7.entries}
    tasks = tuple(sorted(plan.get("tasks", ()), key=lambda row: row["task_identity"]))
    if not tasks or set(entries) != {row.get("model_id") for row in plan.get("models", ())}:
        raise FutureStageExecutionError("future_stage_n5_task_binding_invalid")
    chunk_count = len(runtime.plan["chunks"])
    from .plan_executor import frozen_grid, rank_train, validate_metrics

    def execute(chunk: Mapping[str, Any]) -> Mapping[str, Any]:
        ordinal = chunk.get("ordinal")
        if not isinstance(ordinal, int) or not 0 <= ordinal < chunk_count:
            raise FutureStageExecutionError("future_stage_chunk_ordinal_invalid")
        cells = []
        for index, task in enumerate(tasks):
            if index % chunk_count != ordinal:
                continue
            entry = entries.get(task["model_id"])
            if entry is None:
                raise FutureStageExecutionError("future_stage_task_entry_missing")
            train = []
            for params in frozen_grid(entry):
                metrics = validate_metrics(evaluator("TRAIN", entry, task, params))
                train.append({"params": dict(params), **metrics})
            top = rank_train(train)[: min(int(plan["top_k_train"]), len(train))]
            validation = []
            for row in top:
                metrics = validate_metrics(evaluator("VALIDATION", entry, task, row["params"]))
                validation.append({"params": dict(row["params"]), **metrics, "oos_authorized": False})
            cells.append({
                "task_identity": task["task_identity"], "model_id": task["model_id"], "symbol": task["symbol"],
                "parameter_grid_hash": entry.parameter_grid_hash, "train": train, "validation": validation,
            })
        return {"cells": cells, "task_count": len(cells), "train_evaluations": sum(len(row["train"]) for row in cells),
                "validation_evaluations": sum(len(row["validation"]) for row in cells),
                "oos_read": False}

    return execute
