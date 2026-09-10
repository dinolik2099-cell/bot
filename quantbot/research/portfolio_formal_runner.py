"""Canonical future portfolio entrypoint; deny before any protected data access."""
from __future__ import annotations
from typing import Any, Callable, Mapping
from .authorization import AuthorizationEvidence, Capability
from .future_stages import validate_portfolio_protocol
from .non_oos_series import validate_external_n12_anchor
from .evaluation import make_strategy_adapter
from .canonical_data_adapter import make_n8_canonical_window_loader
from .artifact_store import seal, validate_seal, write_new_json

class PortfolioRunnerError(RuntimeError): pass

def authorize_portfolio_run(*, protocol: Mapping[str,Any], diagnostic: Mapping[str,Any], manifest: Mapping[str,Any],
                            n11_identity: str, candidate_count: int, correlation_sha256: str,
                            evidence: AuthorizationEvidence) -> None:
    """Metadata-only pre-data gate for the future canonical runner."""
    validate_portfolio_protocol(protocol)
    validate_external_n12_anchor(diagnostic,manifest,expected_n11_identity=n11_identity,
                                 expected_candidate_count=candidate_count,actual_correlation_sha256=correlation_sha256)
    if protocol.get('n11_identity')!=n11_identity or protocol.get('correlation_sha256')!=correlation_sha256:
        raise PortfolioRunnerError('portfolio_external_anchor_mismatch')
    if evidence.capability!=Capability.TRAIN_VALIDATION: raise PortfolioRunnerError('portfolio_capability_invalid')
    evidence.require()

def build_canonical_signal_map(*, frame, strategy, params, model_id, symbol, task_identity,
                               risk_fraction: float=0.01, position_fraction: float=1.0):
    """Convert the canonical T-1 adapter into shared-capital signal-map rows.

    This helper is deliberately internal-facing: callers obtain ``frame`` only
    after ``authorize_portfolio_run`` and the N8 formal loader have succeeded.
    """
    if not model_id or not symbol or not task_identity: raise PortfolioRunnerError('portfolio_signal_identity_missing')
    adapter=make_strategy_adapter(strategy,full_frame=frame,params=params,risk_fraction=risk_fraction,
                                  position_fraction=position_fraction,tag=task_identity)
    signals={}
    for index in range(len(frame)):
        signal=adapter(frame.iloc[:index],index)
        if signal is not None:
            if signal.stop_price is None: raise PortfolioRunnerError('portfolio_signal_stop_required')
            signals[frame.index[index]]={'side':signal.side,'stop_price':signal.stop_price,'take_profit':signal.take_profit,'tag':signal.tag}
    return {(model_id,symbol):signals}

def make_portfolio_window_loader(*, n8_context, raw_root, protocol, diagnostic, manifest,
                                 n11_identity, candidate_count, correlation_sha256, evidence):
    """Formal constructor: authorization precedes canonical loader creation."""
    authorize_portfolio_run(protocol=protocol,diagnostic=diagnostic,manifest=manifest,n11_identity=n11_identity,
                            candidate_count=candidate_count,correlation_sha256=correlation_sha256,evidence=evidence)
    return make_n8_canonical_window_loader(n8_context,raw_root)


def _frozen_candidates(protocol: Mapping[str, Any], manifest: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """Return N12 candidates only when the protocol and manifest agree exactly.

    ``candidate_identity`` is deliberately the shared-capital sleeve key.  A
    model/symbol pair can have several separately retained N12 parameter sets;
    using only ``(model_id, symbol)`` would silently discard all but one.
    """
    protocol_rows=protocol.get('candidates')
    manifest_rows=manifest.get('rows')
    if not isinstance(protocol_rows,list) or not isinstance(manifest_rows,list):
        raise PortfolioRunnerError('portfolio_candidate_rows_missing')
    by_protocol={row.get('candidate_identity'): row for row in protocol_rows if isinstance(row,Mapping)}
    by_manifest={row.get('candidate',{}).get('candidate_identity'): row.get('candidate')
                 for row in manifest_rows if isinstance(row,Mapping) and isinstance(row.get('candidate'),Mapping)}
    if not by_protocol or set(by_protocol)!=set(by_manifest) or len(by_protocol)!=len(protocol_rows):
        raise PortfolioRunnerError('portfolio_candidate_set_mismatch')
    required=('candidate_identity','validation_result_identity','selected_train_result_identity',
              'task_identity','model_id','family','symbol','params')
    rows=[]
    for identity in sorted(by_protocol):
        left,right=by_protocol[identity],by_manifest[identity]
        if any(left.get(key)!=right.get(key) for key in required):
            raise PortfolioRunnerError('portfolio_candidate_metadata_mismatch')
        rows.append(left)
    return rows


def build_shared_capital_inputs(*, frames_by_symbol: Mapping[str, Any], protocol: Mapping[str, Any],
                                manifest: Mapping[str, Any], strategy_resolver: Callable[[str], Callable[..., Any]],
                                risk_fraction: float=0.01, position_fraction: float=1.0):
    """Build complete deterministic N12 sleeves for the existing shared engine.

    Frames must already have passed the N8 formal canonical loader.  This
    adapter does not load data, rank candidates, tune parameters, or authorize
    a run.  The returned recipe keys pass unchanged to shared_backtest.
    """
    validate_portfolio_protocol(protocol)
    candidates=_frozen_candidates(protocol,manifest)
    frames=dict(frames_by_symbol)
    if set(frames)!={row['symbol'] for row in candidates}:
        raise PortfolioRunnerError('portfolio_frame_symbol_set_mismatch')
    signal_maps={}; provenance={}
    for row in candidates:
        candidate_id=row['candidate_identity']; symbol=row['symbol']
        strategy=strategy_resolver(row['model_id'])
        if not callable(strategy): raise PortfolioRunnerError('portfolio_strategy_resolver_invalid')
        signal_maps.update(build_canonical_signal_map(
            frame=frames[symbol],strategy=strategy,params=row['params'],model_id=candidate_id,
            symbol=symbol,task_identity=row['task_identity'],risk_fraction=risk_fraction,
            position_fraction=position_fraction))
        provenance[candidate_id]={
            'candidate_identity':candidate_id,'validation_result_identity':row['validation_result_identity'],
            'selected_train_result_identity':row['selected_train_result_identity'],'task_identity':row['task_identity'],
            'model_id':row['model_id'],'family':row['family'],'symbol':symbol,'params':dict(row['params']),
        }
    recipe_keys=sorted(signal_maps)
    return {'frames':frames,'signal_maps':signal_maps,'recipe_keys':recipe_keys,
            'sleeve_provenance':provenance,'candidate_count':len(recipe_keys),
            'oos_status':'SEALED','oos_authorization':'NOT_AUTHORIZED'}


def prepare_authorized_portfolio_inputs(*, n8_context, raw_root, protocol, diagnostic, manifest,
                                        n11_identity, candidate_count, correlation_sha256, evidence,
                                        window: str, strategy_resolver: Callable[[str], Callable[..., Any]]):
    """Formal pre-execution preparation, structurally bound to the N8 loader.

    Authorization and frozen candidate checks finish before a canonical loader
    is constructed.  It loads every required symbol once for a TRAIN or
    VALIDATION request, then stops before shared-capital accounting; a separate
    reviewed authority remains required for formal portfolio execution.
    """
    if window not in {'TRAIN','VALIDATION'}: raise PortfolioRunnerError('portfolio_window_not_authorized')
    loader=make_portfolio_window_loader(
        n8_context=n8_context,raw_root=raw_root,protocol=protocol,diagnostic=diagnostic,manifest=manifest,
        n11_identity=n11_identity,candidate_count=candidate_count,correlation_sha256=correlation_sha256,evidence=evidence)
    candidates=_frozen_candidates(protocol,manifest)
    tasks={task['task_identity']:task for task in n8_context.n7.plan['tasks']}
    frames={}
    for row in candidates:
        task=tasks.get(row['task_identity'])
        if task is None or task.get('model_id')!=row['model_id'] or task.get('symbol')!=row['symbol']:
            raise PortfolioRunnerError('portfolio_task_binding_mismatch')
        if row['symbol'] not in frames:
            frames[row['symbol']]=loader(window=window,symbol=row['symbol'],task=task,boundary=n8_context.n7.plan['boundary'])
    prepared=build_shared_capital_inputs(frames_by_symbol=frames,protocol=protocol,manifest=manifest,
                                         strategy_resolver=strategy_resolver)
    prepared.update({'window':window,'research_freeze_identity':n8_context.n7.plan['research_freeze_identity'],
                     'research_plan_identity':n8_context.n7.plan['research_plan_identity'],
                     'boundary_identity_hash':n8_context.n7.plan['boundary_identity_hash'],
                     'dataset_id':n8_context.dataset.dataset_id})
    return prepared


def run_authorized_shared_capital_portfolio(*, n8_context, raw_root, protocol, diagnostic, manifest,
                                            n11_identity, candidate_count, correlation_sha256, evidence,
                                            window: str, strategy_resolver, source_git_commit: str):
    """Formal Portfolio execution path using only the established engine.

    This callable is intentionally not invoked by engineering/preflight code.
    It prepares N8-validated inputs, delegates to the one shared-capital engine
    and seals a new result object; it never overwrites N3/N5/N11/N12 artifacts.
    """
    if not isinstance(source_git_commit,str) or len(source_git_commit)!=40:
        raise PortfolioRunnerError('portfolio_source_git_commit_invalid')
    prepared=prepare_authorized_portfolio_inputs(
        n8_context=n8_context,raw_root=raw_root,protocol=protocol,diagnostic=diagnostic,manifest=manifest,
        n11_identity=n11_identity,candidate_count=candidate_count,correlation_sha256=correlation_sha256,
        evidence=evidence,window=window,strategy_resolver=strategy_resolver)
    from quantbot.portfolio.shared_capital import shared_backtest
    accounting=shared_backtest(prepared['frames'],prepared['signal_maps'],prepared['recipe_keys'],
                               {'dataset_id':prepared['dataset_id'],'boundary_identity_hash':prepared['boundary_identity_hash']})
    return seal({'schema_version':'quantbot-portfolio-formal-result-v1','portfolio_protocol_identity':protocol['artifact_identity'],
                 'n11_identity':n11_identity,'n12_manifest_identity':manifest['artifact_identity'],
                 'research_freeze_identity':prepared['research_freeze_identity'],'research_plan_identity':prepared['research_plan_identity'],
                 'boundary_identity_hash':prepared['boundary_identity_hash'],'dataset_id':prepared['dataset_id'],
                 'window':window,'source_git_commit':source_git_commit,'candidate_count':prepared['candidate_count'],
                 'recipe_keys':[list(key) for key in prepared['recipe_keys']], 'sleeve_provenance':prepared['sleeve_provenance'],
                 'accounting':accounting,'oos_status':'SEALED','oos_authorization':'NOT_AUTHORIZED'})


def validate_portfolio_formal_result(result: Mapping[str,Any], *, protocol: Mapping[str,Any], manifest: Mapping[str,Any]) -> bool:
    validate_seal(result); validate_portfolio_protocol(protocol)
    if result.get('schema_version')!='quantbot-portfolio-formal-result-v1' or result.get('portfolio_protocol_identity')!=protocol.get('artifact_identity') or result.get('n12_manifest_identity')!=manifest.get('artifact_identity'):
        raise PortfolioRunnerError('portfolio_result_binding_invalid')
    if result.get('oos_status')!='SEALED' or result.get('oos_authorization')!='NOT_AUTHORIZED' or result.get('candidate_count')!=len(protocol.get('candidates',[])):
        raise PortfolioRunnerError('portfolio_result_oos_or_count_invalid')
    candidates=_frozen_candidates(protocol,manifest)
    expected={row['candidate_identity']:row for row in candidates}; provenance=result.get('sleeve_provenance')
    if not isinstance(provenance,Mapping) or set(provenance)!=set(expected): raise PortfolioRunnerError('portfolio_result_sleeve_set_invalid')
    for identity,row in expected.items():
        if any(provenance[identity].get(key)!=row.get(key) for key in ('candidate_identity','task_identity','model_id','family','symbol','params','validation_result_identity','selected_train_result_identity')):
            raise PortfolioRunnerError('portfolio_result_sleeve_provenance_invalid')
    return True


def write_portfolio_formal_result(root, result: Mapping[str,Any]):
    validate_seal(result)
    return write_new_json(root,'PORTFOLIO_FORMAL_RESULT',result)
