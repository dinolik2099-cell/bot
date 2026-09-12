"""Canonical non-OOS stress evaluator construction.

This module only constructs the evaluator after a future explicit
TRAIN/VALIDATION authority.  It never runs a study by itself and has no OOS,
fallback-loader, or caller-supplied-engine path.
"""
from __future__ import annotations

from dataclasses import asdict
from functools import partial
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor,as_completed
import multiprocessing
from typing import Any, Mapping

from quantbot.backtest.costs import CostModel
from quantbot.backtest.engine_v2 import BacktestEngine
from quantbot.backtest.stress_framework import CostStressScenario, scenario_identity

from .future_data_plane import FutureDataPlaneError, FutureRuntimeContext, make_future_canonical_evaluator
from .future_stage_execution import FutureStageExecution, _row_identity, _validate_resume, _completed_rows, make_canonical_plan_chunk_executor
from .formal_parallel import resolve_workers, apply_worker_thread_limits
from .future_stages import ResumableStageState, StageState


class StressRunnerError(RuntimeError):
    pass


# This is the accepted immutable N5 plan, not a value inferred from a future
# stage's task payload.  A worker must bind to it again after spawn, before it
# constructs a canonical loader or evaluator.
ACCEPTED_N5_RESEARCH_PLAN_IDENTITY = '6cf38b06d364f1eefb02efed156e96d371eb14f58305c29aba47af4d2fa297d9'


def _stress_worker_provenance(request, runtime, evidence, n8_context, actual_source_git_commit):
    """Fail closed unless a spawned worker recreates the accepted chain.

    ``request`` is deliberately only a transport envelope.  It is never an
    authority: every value is compared with the independently reloaded N7/N8
    context, the locally observed Git commit, and the reconstructed runtime.
    This function performs no market-data access.
    """
    if not isinstance(request, Mapping):
        raise StressRunnerError('stress_worker_request_invalid')
    runtime.validate()
    evidence.require()
    if evidence.capability.name != 'TRAIN_VALIDATION':
        raise StressRunnerError('stress_worker_authority_invalid')
    frozen_plan = getattr(getattr(n8_context, 'n7', None), 'plan', None)
    frozen_freeze = getattr(getattr(n8_context, 'n7', None), 'freeze', None)
    dataset = getattr(n8_context, 'dataset', None)
    if not isinstance(frozen_plan, Mapping) or not isinstance(frozen_freeze, Mapping) or dataset is None:
        raise StressRunnerError('stress_worker_n8_context_invalid')
    if frozen_plan.get('research_plan_identity') != ACCEPTED_N5_RESEARCH_PLAN_IDENTITY:
        raise StressRunnerError('stress_worker_n5_plan_identity_drift')
    if request.get('research_plan_identity') != ACCEPTED_N5_RESEARCH_PLAN_IDENTITY:
        raise StressRunnerError('stress_worker_request_plan_identity_drift')
    if evidence.research_plan_identity != ACCEPTED_N5_RESEARCH_PLAN_IDENTITY:
        raise StressRunnerError('stress_worker_authority_plan_identity_drift')
    if frozen_plan.get('research_freeze_identity') != request.get('research_freeze_identity'):
        raise StressRunnerError('stress_worker_freeze_identity_drift')
    if frozen_freeze.get('research_freeze_identity') != frozen_plan.get('research_freeze_identity') or frozen_freeze.get('research_boundary') != frozen_plan.get('boundary'):
        raise StressRunnerError('stress_worker_n8_freeze_chain_drift')
    if evidence.research_freeze_identity != frozen_plan.get('research_freeze_identity'):
        raise StressRunnerError('stress_worker_authority_freeze_identity_drift')
    if frozen_plan.get('oos_status') != 'SEALED' or frozen_plan.get('oos_authorization') != 'NOT_AUTHORIZED':
        raise StressRunnerError('stress_worker_frozen_oos_violation')
    if runtime.protocol.get('oos_status') != 'SEALED' or runtime.protocol.get('oos_authorization') != 'NOT_AUTHORIZED':
        raise StressRunnerError('stress_worker_protocol_oos_violation')
    if runtime.plan.get('oos_status') != 'SEALED' or runtime.plan.get('oos_authorization') != 'NOT_AUTHORIZED':
        raise StressRunnerError('stress_worker_plan_oos_violation')
    if runtime.protocol.get('dataset_id') != getattr(dataset, 'dataset_id', None) or request.get('dataset_id') != getattr(dataset, 'dataset_id', None):
        raise StressRunnerError('stress_worker_dataset_identity_drift')
    if runtime.protocol.get('boundary_identity_hash') != frozen_plan.get('boundary_identity_hash') or request.get('boundary_identity_hash') != frozen_plan.get('boundary_identity_hash'):
        raise StressRunnerError('stress_worker_boundary_identity_drift')
    if runtime.protocol.get('artifact_identity') != request.get('protocol_identity'):
        raise StressRunnerError('stress_worker_protocol_identity_drift')
    if runtime.plan.get('artifact_identity') != request.get('execution_plan_identity'):
        raise StressRunnerError('stress_worker_execution_plan_identity_drift')
    if runtime.input_identity != request.get('input_identity'):
        raise StressRunnerError('stress_worker_input_identity_drift')
    if runtime.protocol.get('source_git_commit') != request.get('source_git_commit') or actual_source_git_commit != request.get('source_git_commit'):
        raise StressRunnerError('stress_worker_source_commit_drift')
    return True


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
        engine_factory=lambda: BacktestEngine(initial_equity=10_000.0, cost_model=stressed),
    )


def _stress_chunk_worker(request,chunk):
    """Spawn-safe worker: reconstruct canonical dependencies in its process."""
    apply_worker_thread_limits()
    import sys
    root=Path(request['repo_root'])
    if str(root) not in sys.path: sys.path.insert(0,str(root))
    from quantbot.research.authorization import AuthorizationEvidence,Capability
    from quantbot.research.future_data_plane import FutureRuntimeContext
    from quantbot.research.formal_execution_manifest import repository_state
    from scripts import run_formal_train_validation as formal
    runtime=FutureRuntimeContext(request['protocol'],request['plan'],request['input_identity']);runtime.validate()
    evidence=AuthorizationEvidence(Capability.TRAIN_VALIDATION,**request['evidence'])
    n7,n8=formal.load_formal_context()
    _stress_worker_provenance(request,runtime,evidence,n8,repository_state(root)['commit'])
    resolver=formal.make_strategy_resolver([row['model_id'] for row in n7.plan['models']])
    evaluator=make_stress_canonical_evaluator(runtime=runtime,evidence=evidence,n8_context=n8,raw_root=request['raw_root'],strategy_resolver=resolver)
    return make_canonical_plan_chunk_executor(runtime=runtime,n8_context=n8,evaluator=evaluator)(chunk)

def resolve_stress_workers(runtime,workers='auto'):
    count=len(runtime.plan['chunks'])
    if workers=='auto': cap=count
    elif type(workers) is int and workers>=1: cap=min(workers,count)
    else: raise StressRunnerError('stress_workers_invalid')
    return min(resolve_workers(requested_cap=cap).workers,count)

def _execute_stress_chunks(*,runtime,source_git_commit,executor,checkpoint=None,prior_rows=(),retry_failed=False,workers=1):
    """Stress-only deterministic process coordinator; other stages stay serial."""
    runtime.validate()
    if not isinstance(source_git_commit,str) or len(source_git_commit)!=40:raise StressRunnerError('stress_source_commit_invalid')
    state=_validate_resume(runtime,checkpoint)
    if retry_failed and state.failed_chunks:state=ResumableStageState(state.protocol_identity,StageState.INTERRUPTED,state.completed_chunks,())
    state=state.resume();rows=[dict(row) for row in prior_rows];_completed_rows(runtime,rows,ResumableStageState(state.protocol_identity,state.state,state.completed_chunks,()))
    chunks=tuple(sorted(runtime.plan['chunks'],key=lambda row:row['ordinal']));expected=tuple(row['chunk_identity'] for row in chunks)
    pending=[row for row in chunks if row['chunk_identity'] not in state.completed_chunks and row['chunk_identity'] not in state.failed_chunks]
    if workers>1 and len(pending)>1:
        with ProcessPoolExecutor(max_workers=min(workers,len(pending)),mp_context=multiprocessing.get_context('spawn')) as pool:
            futures={pool.submit(executor,dict(chunk)):chunk for chunk in pending};outcomes=[]
            for future in as_completed(futures):
                chunk=futures[future]
                try:outcomes.append((chunk,future.result(),None))
                except Exception as exc:outcomes.append((chunk,None,exc))
    else:
        outcomes=[]
        for chunk in pending:
            try:outcomes.append((chunk,executor(dict(chunk)),None))
            except Exception as exc:outcomes.append((chunk,None,exc));break
    for chunk,evidence,error in sorted(outcomes,key=lambda row:row[0]['ordinal']):
        try:
            if error is not None:raise error
            if not isinstance(evidence,Mapping):raise StressRunnerError('stress_worker_evidence_invalid')
            row={'chunk_identity':chunk['chunk_identity'],'status':'COMPLETED','window':'TRAIN_VALIDATION','protocol_identity':runtime.protocol['artifact_identity'],'execution_plan_identity':runtime.plan['artifact_identity'],'input_identity':runtime.input_identity,'evidence':dict(evidence),'oos_status':'SEALED','oos_authorization':'NOT_AUTHORIZED'}
            row['result_identity']=_row_identity(runtime=runtime,chunk=chunk,evidence=row['evidence']);rows.append(row);state=state.record(chunk['chunk_identity'],succeeded=True)
        except Exception:state=state.record(chunk['chunk_identity'],succeeded=False)
    if state.failed_chunks:state=ResumableStageState(state.protocol_identity,StageState.INTERRUPTED,state.completed_chunks,state.failed_chunks)
    elif len(state.completed_chunks)==len(expected):state=state.finish(expected)
    else:state=ResumableStageState(state.protocol_identity,StageState.INTERRUPTED,state.completed_chunks,state.failed_chunks)
    sealed=runtime.checkpoint(state);ordered=tuple(sorted(rows,key=lambda row:row['chunk_identity']))
    return FutureStageExecution(state,sealed,ordered,None if state.state!=StageState.COMPLETE else runtime.result(ordered,source_git_commit))

def run_authorized_stress(*, runtime: FutureRuntimeContext, evidence, n8_context, raw_root,
                          strategy_resolver, source_git_commit: str, checkpoint=None, prior_rows=(),workers='auto'):
    """Execute frozen stress chunks through only the N7/N8 canonical path.

    There is deliberately no evaluator argument.  A caller cannot replace the
    stressed BacktestEngine/CostModel with fabricated metrics while retaining
    formal provenance.
    """
    effective=resolve_stress_workers(runtime,workers)
    evaluator = make_stress_canonical_evaluator(runtime=runtime,evidence=evidence,n8_context=n8_context,raw_root=raw_root,strategy_resolver=strategy_resolver)
    if effective>1:
        frozen_plan=n8_context.n7.plan
        request={'repo_root':str(Path(raw_root).resolve().parents[1]),'protocol':dict(runtime.protocol),'plan':dict(runtime.plan),'input_identity':runtime.input_identity,'protocol_identity':runtime.protocol['artifact_identity'],'execution_plan_identity':runtime.plan['artifact_identity'],'research_plan_identity':frozen_plan['research_plan_identity'],'research_freeze_identity':frozen_plan['research_freeze_identity'],'dataset_id':n8_context.dataset.dataset_id,'boundary_identity_hash':frozen_plan['boundary_identity_hash'],'source_git_commit':source_git_commit,'raw_root':str(raw_root),'evidence':{'status':evidence.status,'reason':evidence.reason,'research_freeze_identity':evidence.research_freeze_identity,'research_plan_identity':evidence.research_plan_identity,'evidence_identity':evidence.evidence_identity}}
        executor=partial(_stress_chunk_worker,request)
    else: executor=make_canonical_plan_chunk_executor(runtime=runtime,n8_context=n8_context,evaluator=evaluator)
    return _execute_stress_chunks(
        runtime=runtime, source_git_commit=source_git_commit,
        executor=executor, checkpoint=checkpoint, prior_rows=prior_rows,workers=effective,
    )
