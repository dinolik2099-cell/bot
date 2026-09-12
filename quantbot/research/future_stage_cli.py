"""Executable, fail-closed wiring for sealed future non-OOS stages."""
from __future__ import annotations
import argparse, importlib, json
from pathlib import Path
from typing import Any, Mapping
from .authorization import AuthorizationEvidence, Capability, locked_evidence
from .formal_execution_manifest import repository_state
from .future_data_plane import FutureRuntimeContext

class FutureStageCliError(RuntimeError): pass

def _load(path):
    value=json.loads(Path(path).read_text(encoding='utf-8'))
    if not isinstance(value,Mapping): raise FutureStageCliError('future_stage_cli_json_mapping_required')
    return value

def _authority(path,capability):
    if path is None: return locked_evidence(capability)
    row=_load(path)
    try: evidence=AuthorizationEvidence(Capability(row['capability']),row['status'],row['reason'],row.get('research_freeze_identity'),row.get('research_plan_identity'),row.get('evidence_identity'))
    except (KeyError,TypeError,ValueError) as exc: raise FutureStageCliError('future_stage_cli_authority_invalid') from exc
    if evidence.capability!=capability: raise FutureStageCliError('future_stage_cli_authority_capability_mismatch')
    return evidence

def resolve_canonical_runtime(runtime):
    """Reuse the accepted formal runner's N7/N8/context/engine dependencies."""
    formal=importlib.import_module('scripts.run_formal_train_validation')
    state=repository_state(formal.ROOT)
    if not state.get('clean'): raise FutureStageCliError('future_stage_cli_source_tree_not_clean')
    if runtime.protocol.get('source_git_commit')!=state.get('commit'): raise FutureStageCliError('future_stage_cli_source_commit_drift')
    n7,n8=formal.load_formal_context()
    if runtime.protocol.get('dataset_id')!=n8.dataset.dataset_id: raise FutureStageCliError('future_stage_cli_dataset_drift')
    if runtime.protocol.get('boundary_identity_hash')!=n7.plan.get('boundary_identity_hash'): raise FutureStageCliError('future_stage_cli_boundary_drift')
    return {'n8':n8,'raw_root':formal.RAW_ROOT,'strategy_resolver':formal.make_strategy_resolver([row['model_id'] for row in n7.plan['models']]),'engine_factory':formal.engine_factory,'source_git_commit':state['commit']}

def _checkpoint(runtime,path):
    if path is None:return None
    value=_load(path);runtime.validate_checkpoint(value);return value

def _rows(path):
    if path is None:return ()
    value=_load(path);rows=value.get('rows',value.get('prior_rows',[]))
    if not isinstance(rows,list) or any(not isinstance(row,Mapping) for row in rows):raise FutureStageCliError('future_stage_cli_rows_invalid')
    return tuple(dict(row) for row in rows)

def dispatch_authorized_stage(*,stage,runtime,authority,deps,checkpoint=None,prior_rows=(),evidence_path=None,workers='auto'):
    """Call an existing production runner; no evaluator/loader injection exists."""
    common=dict(runtime=runtime,evidence=authority,n8_context=deps['n8'],raw_root=deps['raw_root'],source_git_commit=deps['source_git_commit'],checkpoint=checkpoint,prior_rows=prior_rows)
    if stage=='stress':
        from .stress_formal_runner import run_authorized_stress
        return run_authorized_stress(strategy_resolver=deps['strategy_resolver'],workers=workers,**common)
    if stage=='regime':
        from .regime_formal_runner import run_authorized_regime
        return run_authorized_regime(**common)
    if stage=='walk_forward':
        from .walk_forward_non_oos_runner import run_authorized_walk_forward
        return run_authorized_walk_forward(strategy_resolver=deps['strategy_resolver'],engine_factory=deps['engine_factory'],**common)
    if stage=='long_horizon':
        from .long_horizon_formal_runner import run_authorized_long_horizon
        return run_authorized_long_horizon(strategy_resolver=deps['strategy_resolver'],engine_factory=deps['engine_factory'],**common)
    if stage=='failure':
        from quantbot.risk.failure_supervisor import FailureEvent
        from .failure_data_plane import run_authorized_failure_diagnostics
        source=_load(evidence_path) if evidence_path else {'events':{}}
        events={key:FailureEvent(**dict(row)) for key,row in dict(source.get('events',{})).items()}
        return run_authorized_failure_diagnostics(runtime=runtime,evidence=authority,events_by_chunk=events,source_git_commit=deps['source_git_commit'],checkpoint=checkpoint,prior_rows=prior_rows)
    if stage=='monte_carlo':
        from .monte_carlo_formal_runner import run_authorized_monte_carlo
        if evidence_path is None:raise FutureStageCliError('future_stage_cli_mc_evidence_required')
        return run_authorized_monte_carlo(runtime=runtime,evidence=authority,upstream_evidence=_load(evidence_path),source_git_commit=deps['source_git_commit'],checkpoint=checkpoint,prior_rows=prior_rows)
    if stage=='portfolio':
        from .portfolio_formal_runner import run_authorized_shared_capital_portfolio
        if evidence_path is None:raise FutureStageCliError('future_stage_cli_portfolio_evidence_required')
        row=_load(evidence_path)
        return run_authorized_shared_capital_portfolio(n8_context=deps['n8'],raw_root=deps['raw_root'],protocol=runtime.protocol,diagnostic=row['diagnostic'],manifest=row['manifest'],n11_identity=row['n11_identity'],candidate_count=row['candidate_count'],correlation_sha256=row['correlation_sha256'],evidence=authority,window=row.get('window','VALIDATION'),strategy_resolver=deps['strategy_resolver'],source_git_commit=deps['source_git_commit'])
    raise FutureStageCliError('future_stage_cli_unknown_stage')

def main_for_stage(stage):
    parser=argparse.ArgumentParser(description=f'QuantBot sealed {stage} non-OOS stage')
    parser.add_argument('--protocol',required=True);parser.add_argument('--plan',required=True);parser.add_argument('--input-identity',required=True)
    parser.add_argument('--execute',action='store_true');parser.add_argument('--authority-json');parser.add_argument('--checkpoint-json');parser.add_argument('--prior-rows-json');parser.add_argument('--stage-evidence-json');parser.add_argument('--execution-json');parser.add_argument('--workers',default='auto')
    args=parser.parse_args();runtime=FutureRuntimeContext(_load(args.protocol),_load(args.plan),args.input_identity);runtime.validate()
    if runtime.protocol.get('stage')!=stage:raise SystemExit('future_stage_cli_stage_mismatch')
    print(f'STAGE={stage}');print(f"PROTOCOL_IDENTITY={runtime.protocol['artifact_identity']}");print(f"EXECUTION_PLAN_IDENTITY={runtime.plan['artifact_identity']}");print('OOS_STATUS=SEALED');print('OOS_AUTHORIZATION=NOT_AUTHORIZED')
    if not args.execute:print('FORMAL_STAGE_NOT_STARTED');return 2
    capability=Capability.MONTE_CARLO if stage=='monte_carlo' else Capability.TRAIN_VALIDATION
    authority=_authority(args.authority_json,capability)
    # Authorization is deliberately before canonical context/source/evidence loading.
    runtime.authorize(authority,capability)
    workers=args.workers if args.workers=='auto' else int(args.workers)
    if stage!='stress' and workers!='auto':raise FutureStageCliError('future_stage_workers_unsupported')
    output=dispatch_authorized_stage(stage=stage,runtime=runtime,authority=authority,deps=resolve_canonical_runtime(runtime),checkpoint=_checkpoint(runtime,args.checkpoint_json),prior_rows=_rows(args.prior_rows_json),evidence_path=args.stage_evidence_json,workers=workers)
    if args.execution_json:
        if not all(hasattr(output,key) for key in ('state','checkpoint','rows','result')):
            raise FutureStageCliError('future_stage_cli_execution_snapshot_unavailable')
        destination=Path(args.execution_json)
        destination.parent.mkdir(parents=True,exist_ok=True)
        snapshot={
            'state':{
                'protocol_identity':output.state.protocol_identity,
                'state':output.state.state.value,
                'completed_chunks':list(output.state.completed_chunks),
                'failed_chunks':list(output.state.failed_chunks),
            },
            'checkpoint':dict(output.checkpoint),
            'rows':[dict(row) for row in output.rows],
            'result':dict(output.result) if output.result is not None else None,
        }
        try:
            with destination.open('x',encoding='utf-8') as handle:
                json.dump(snapshot,handle,indent=2,sort_keys=True)
                handle.write('\n')
        except FileExistsError as exc:
            raise FutureStageCliError('future_stage_cli_execution_snapshot_exists') from exc
        print(f'EXECUTION_JSON={destination}')
    result=getattr(output,'result',output);print('FORMAL_STAGE_DISPATCHED');print(f"RESULT_IDENTITY={result.get('artifact_identity') if result else 'PARTIAL'}");return 0
