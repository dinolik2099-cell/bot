"""Bounded completed-candle Forward Shadow pipeline.

Completed ingress remains FIFO in ``PublicWebsocketTransport``.  Expensive
model observation is deliberately off that ingress thread, but its evidence is
committed by one ordered coordinator.  Thus a membership rollover can retire
mutable ingress without waiting behind CPU-bound model evaluation, while an
accepted completed candle is never coalesced or silently discarded.
"""
from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
import threading
import time
from typing import Mapping, Sequence

from .core import ForwardResearchError, assert_shadow_only
from .frozen_declarations import validate_forward_declarations
from .model_runtime import run_scheduled_models


def _evaluate_snapshot(symbol: str, rows, declarations):
    """Process-isolated canonical strategy evaluation for immutable history."""
    # Spawned workers cannot inherit a caller-provided evaluator.  They build
    # the same registered strategy universe used by the canonical authority.
    from quantbot.research.model_registry import _REGISTRY, register_existing_models, validate_registry
    from quantbot.strategies.model_pool import register_model_pool
    if not _REGISTRY:
        register_existing_models()
        register_model_pool()
    validate_registry()
    if len(_REGISTRY) != 36:
        raise ForwardResearchError("forward_pipeline_registry_count_invalid")
    return run_scheduled_models(symbol, rows, declarations, incremental=True)


class ForwardPipeline:
    """A bounded compute stage with serial, submission-ordered evidence commit."""

    # These are independent of websocket critical ingress capacity.  They cap
    # only immutable completed-history snapshots awaiting model evaluation.
    MAX_PENDING_OBSERVATIONS = 256
    WORKER_COUNT = 16
    SUBMIT_TIMEOUT_SECONDS = 5.0

    def __init__(self, *, orchestrator, plan: Mapping, declarations: Sequence[Mapping]):
        assert_shadow_only()
        self.orchestrator = orchestrator
        self.plan = dict(plan)
        self.declarations = validate_forward_declarations(self.plan, declarations)
        self.by_model = {row["model_id"]: row for row in self.declarations}
        self._condition = threading.Condition()
        self._pending = {}
        self._submitted = 0
        self._committed = 0
        self._accepting = True
        self._stopped = False
        self._failure = None
        self._executor = ProcessPoolExecutor(max_workers=self.WORKER_COUNT)
        self._committer = threading.Thread(target=self._commit_loop, name="forward-evidence-commit", daemon=True)
        self._committer.start()

    def _set_failure(self, exc: Exception) -> None:
        with self._condition:
            if self._failure is None:
                self._failure = exc
            self._accepting = False
            self._condition.notify_all()

    def _commit_loop(self) -> None:
        while True:
            with self._condition:
                while not self._stopped and self._committed not in self._pending:
                    self._condition.wait()
                if self._stopped and self._committed not in self._pending:
                    return
                sequence = self._committed
                date, symbol, interval, future = self._pending[sequence]
            try:
                result = future.result()
                self.orchestrator.persist_completed_model_result(date, result)
            except Exception as exc:  # preserve the failed job for diagnosis
                self._set_failure(ForwardResearchError("forward_pipeline_worker_failure:" + type(exc).__name__))
                return
            with self._condition:
                del self._pending[sequence]
                self._committed += 1
                self._condition.notify_all()

    def on_completed_candle(self, *, date: str, symbol: str, interval: str) -> dict:
        """Snapshot and enqueue one frozen-timeframe completed observation."""
        assert_shadow_only()
        if interval != self.plan.get("protocol_scope", {}).get("timeframe"):
            raise ForwardResearchError("forward_pipeline_interval_not_frozen")
        rows = self.orchestrator.candles.history(symbol, interval)
        if not rows or not all(row.get("closed") for row in rows):
            raise ForwardResearchError("forward_pipeline_completed_history_required")
        snapshot = tuple(dict(row) for row in rows)
        deadline = time.monotonic() + self.SUBMIT_TIMEOUT_SECONDS
        with self._condition:
            while self._submitted - self._committed >= self.MAX_PENDING_OBSERVATIONS:
                if self._failure is not None:
                    raise self._failure
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    failure = ForwardResearchError("forward_pipeline_capacity_exhausted")
                    self._failure = failure
                    self._accepting = False
                    self._condition.notify_all()
                    raise failure
                self._condition.wait(remaining)
            if self._failure is not None:
                raise self._failure
            if not self._accepting or self._stopped:
                raise ForwardResearchError("forward_pipeline_not_accepting")
            sequence = self._submitted
            self._submitted += 1
            # No parent orchestration object crosses the process boundary:
            # workers receive only an immutable snapshot and frozen metadata.
            future = self._executor.submit(_evaluate_snapshot, symbol, snapshot, self.declarations)
            self._pending[sequence] = (date, symbol, interval, future)
            self._condition.notify_all()
        return {"symbol": symbol, "interval": interval, "submission_sequence": sequence,
                "research_freeze_identity": self.plan["research_freeze_identity"],
                "research_plan_identity": self.plan["research_plan_identity"],
                "forward_research_only": True}

    def retire_and_drain(self, timeout: float = 30) -> bool:
        """Stop new work and wait only for accepted bounded work to commit."""
        deadline = time.monotonic() + max(0.0, timeout)
        with self._condition:
            self._accepting = False
            while self._committed != self._submitted and self._failure is None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                self._condition.wait(remaining)
            return self._failure is None and self._committed == self._submitted

    def begin_generation(self) -> None:
        """Re-open only after a successful prior generation drain.

        ``ForwardServiceAuthority`` intentionally keeps this pipeline across a
        membership rollover so surviving candle/path state is not reset.
        """
        with self._condition:
            if self._stopped or self._failure is not None or self._committed != self._submitted:
                raise ForwardResearchError("forward_pipeline_generation_handoff_invalid")
            self._accepting = True
            self._condition.notify_all()

    def close(self, timeout: float = 30) -> bool:
        drained = self.retire_and_drain(timeout)
        if not drained:
            return False
        with self._condition:
            self._stopped = True
            self._condition.notify_all()
        self._executor.shutdown(wait=True)
        self._committer.join(timeout=max(0.0, timeout))
        return not self._committer.is_alive()

    def health(self) -> dict:
        with self._condition:
            return {"submitted": self._submitted, "committed": self._committed,
                    "pending": self._submitted - self._committed,
                    "max_pending": self.MAX_PENDING_OBSERVATIONS,
                    "worker_count": self.WORKER_COUNT,
                    "failed": self._failure is not None,
                    "accepting": self._accepting}
