"""Canonical non-OOS stress evaluator construction.

This module only constructs the evaluator after a future explicit
TRAIN/VALIDATION authority.  It never runs a study by itself and has no OOS,
fallback-loader, or caller-supplied-engine path.
"""
from __future__ import annotations

from dataclasses import asdict
from typing import Any, Mapping

from quantbot.backtest.costs import CostModel
from quantbot.backtest.engine_v2 import BacktestEngine
from quantbot.backtest.stress_framework import CostStressScenario, scenario_identity

from .future_data_plane import FutureDataPlaneError, FutureRuntimeContext, make_future_canonical_evaluator
from .future_stage_execution import _execute_verified_chunks, make_canonical_plan_chunk_executor


class StressRunnerError(RuntimeError):
    pass


def _frozen_stress_cost_model(runtime: FutureRuntimeContext) -> CostModel:
    if runtime.protocol.get('stage') != 'stress':
        raise StressRunnerError('stress_stage_required')
    config=runtime.protocol.get('config')
    if not isinstance(config,Mapping):
        raise StressRunnerError('stress_config_missing')
    try:
        scenario=CostStressScenario(**dict(config['scenario']))
        base=CostModel(**dict(config['base_cost_model']))
    except (KeyError,TypeError,ValueError) as exc:
        raise StressRunnerError('stress_config_invalid') from exc
    if config.get('scenario_identity') != scenario_identity(scenario):
        raise StressRunnerError('stress_scenario_identity_mismatch')
    if config.get('base_cost_model') != asdict(base):
        raise StressRunnerError('stress_base_cost_model_mismatch')
    return scenario.stressed_cost_model(base)


def make_stress_canonical_evaluator(*, runtime: FutureRuntimeContext, evidence, n8_context,
                                    raw_root, strategy_resolver):
    """Bind a frozen adverse CostModel to the common N7/N8 evaluator path."""
    stressed=_frozen_stress_cost_model(runtime)
    return make_future_canonical_evaluator(
        runtime=runtime,evidence=evidence,n8_context=n8_context,raw_root=raw_root,
        strategy_resolver=strategy_resolver,
        engine_factory=lambda: BacktestEngine(stressed),
    )


def run_authorized_stress(*, runtime: FutureRuntimeContext, evidence, n8_context, raw_root,
                          strategy_resolver, source_git_commit: str, checkpoint=None, prior_rows=()):
    """Execute frozen stress chunks through only the N7/N8 canonical path.

    There is deliberately no evaluator argument.  A caller cannot replace the
    stressed BacktestEngine/CostModel with fabricated metrics while retaining
    formal provenance.
    """
    evaluator = make_stress_canonical_evaluator(
        runtime=runtime, evidence=evidence, n8_context=n8_context, raw_root=raw_root,
        strategy_resolver=strategy_resolver,
    )
    return _execute_verified_chunks(
        runtime=runtime, source_git_commit=source_git_commit,
        executor=make_canonical_plan_chunk_executor(runtime=runtime, n8_context=n8_context, evaluator=evaluator),
        checkpoint=checkpoint, prior_rows=prior_rows,
    )
