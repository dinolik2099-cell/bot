"""Canonical TRAIN/VALIDATION-only walk-forward runner construction.

OOS fold requests remain handled by the separate locked request contract and
cannot enter this runner.
"""
from __future__ import annotations
from typing import Mapping
from .future_data_plane import FutureRuntimeContext, make_future_canonical_evaluator
from .future_stage_execution import _execute_verified_chunks, make_canonical_plan_chunk_executor


class WalkForwardRunnerError(RuntimeError):
    pass


def _validate_non_oos_folds(runtime: FutureRuntimeContext) -> None:
    if runtime.protocol.get('stage')!='walk_forward':
        raise WalkForwardRunnerError('walk_forward_stage_required')
    config=runtime.protocol.get('config')
    folds=config.get('folds') if isinstance(config,Mapping) else None
    if not isinstance(folds,list) or not folds:
        raise WalkForwardRunnerError('walk_forward_folds_missing')
    ids=[]
    for row in folds:
        if not isinstance(row,Mapping) or set(row)!={'fold_id','train','validation'}:
            raise WalkForwardRunnerError('walk_forward_fold_shape_invalid')
        if not all(isinstance(row.get(key),str) and row[key] for key in ('fold_id','train','validation')):
            raise WalkForwardRunnerError('walk_forward_fold_identity_invalid')
        if row['train']!='TRAIN' or row['validation']!='VALIDATION':
            raise WalkForwardRunnerError('walk_forward_window_not_authorized')
        ids.append(row['fold_id'])
    if len(ids)!=len(set(ids)):
        raise WalkForwardRunnerError('walk_forward_duplicate_fold')


def make_walk_forward_non_oos_evaluator(*, runtime: FutureRuntimeContext, evidence,
                                        n8_context, raw_root, strategy_resolver, engine_factory):
    """Build the only future walk-forward evaluator path without an OOS fold."""
    _validate_non_oos_folds(runtime)
    return make_future_canonical_evaluator(
        runtime=runtime,evidence=evidence,n8_context=n8_context,raw_root=raw_root,
        strategy_resolver=strategy_resolver,engine_factory=engine_factory,
    )


def run_authorized_walk_forward(*, runtime: FutureRuntimeContext, evidence, n8_context, raw_root,
                                strategy_resolver, engine_factory, source_git_commit: str,
                                checkpoint=None, prior_rows=()):
    """Run only frozen non-OOS folds with deterministic N5 task partitioning."""
    evaluator = make_walk_forward_non_oos_evaluator(
        runtime=runtime, evidence=evidence, n8_context=n8_context, raw_root=raw_root,
        strategy_resolver=strategy_resolver, engine_factory=engine_factory,
    )
    return _execute_verified_chunks(
        runtime=runtime, source_git_commit=source_git_commit,
        executor=make_canonical_plan_chunk_executor(runtime=runtime, n8_context=n8_context, evaluator=evaluator),
        checkpoint=checkpoint, prior_rows=prior_rows,
    )
