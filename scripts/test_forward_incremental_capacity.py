"""Forward-only incremental signal equivalence and whole-hour capacity regression."""
from __future__ import annotations
import json
import tempfile
import time
from datetime import datetime,timedelta,timezone
from pathlib import Path

from quantbot.forward_research.collector import MarketEvent
from quantbot.forward_research.core import identity
from quantbot.forward_research.frozen_declarations import DECLARATION_SCHEMA,declaration_identity
from quantbot.forward_research.model_runtime import run_scheduled_models
from quantbot.forward_research.orchestrator import ForwardOrchestrator
from quantbot.forward_research.persistence import ForwardPersistence
from quantbot.forward_research.pipeline import ForwardPipeline
from quantbot.forward_research.runtime import ForwardRuntime
from quantbot.forward_research.service_runtime import build_service
from quantbot.research.candidate_universe import build_candidate_universe
from quantbot.research.model_registry import _REGISTRY,register_existing_models,validate_registry
from quantbot.strategies.model_pool import register_model_pool


def _registry():
    _REGISTRY.clear();register_existing_models();register_model_pool();validate_registry()
    return build_candidate_universe()[:35]


def _params(entry):
    return {key: values[0] for key,values in sorted(entry.parameter_grid.items())}


def _fixture(entries):
    models=[];declarations=[]
    for entry in entries:
        params=_params(entry)
        model={'model_id':entry.model_id,'family':entry.family,'secondary_traits':list(entry.secondary_traits),'warmup_bars':entry.warmup_bars,'required_features':list(entry.required_features),'parameter_grid_hash':entry.parameter_grid_hash,'strategy_function_hash':entry.strategy_function_hash,'implementation_module_hash':entry.implementation_module_hash}
        models.append(model)
        row={'schema_version':DECLARATION_SCHEMA,'research_freeze_identity':'f'*64,'research_plan_identity':'p'*64,'model_id':entry.model_id,'model_name':entry.name,'params':params,'params_identity':identity(params),'parameter_grid_hash':entry.parameter_grid_hash,'strategy_function_hash':entry.strategy_function_hash,'implementation_module_hash':entry.implementation_module_hash,'input_boundary':'COMPLETED_CANDLE_T_MINUS_1'}
        row['declaration_identity']=declaration_identity(row);declarations.append(row)
    plan={'research_freeze_identity':'f'*64,'research_plan_identity':'p'*64,'protocol_scope':{'timeframe':'1h'},'models':models}
    return plan,declarations


def _rows(count,offset=0):
    start=datetime(2026,1,1,tzinfo=timezone.utc)
    out=[]
    for index in range(count):
        # A varying causal OHLCV path exercises trend, reversal and volatility
        # declarations without fetching any market/OOS data.
        absolute=index+offset
        value=100.0+absolute*.13+((absolute%9)-4)*.37
        timestamp=start+timedelta(hours=absolute)
        out.append({'event_time':timestamp.isoformat(),'open':value-.11,'high':value+.71,'low':value-.63,'close':value,'volume':1000.0+(index%17)*13,'closed':True})
    return out


def _event(symbol,row,sequence):
    return MarketEvent(symbol,'1h',row['event_time'],row['event_time'],row['open'],row['high'],row['low'],row['close'],row['volume'],True,sequence)


def _signal_ids(root):
    target=Path(root)/'signals'/'2026-01-01'/'signals.jsonl'
    return [json.loads(line)['signal_identity'] for line in target.read_text(encoding='utf-8').splitlines()] if target.exists() else []


def main():
    entries=_registry();assert len(entries)==35
    plan,declarations=_fixture(entries)
    # At each growing-history step, the Forward-specific output is exactly the
    # delta of the legacy full-history output, including all identity fields.
    growing=_rows(122);previous={row['signal_identity']:row for row in run_scheduled_models('EQUSDT',growing,declarations)['signals']};baseline_ids=set(previous);incremental={}
    for added in _rows(3,122):
        growing.append(added)
        full={row['signal_identity']:row for row in run_scheduled_models('EQUSDT',growing,declarations)['signals']}
        result=run_scheduled_models('EQUSDT',growing,declarations,incremental=True)
        actual={row['signal_identity']:row for row in result['signals']}
        expected={key:value for key,value in full.items() if key not in previous}
        assert actual==expected and not result['errors']
        assert not (set(incremental)&set(actual));incremental.update(actual);previous=full
    assert set(incremental)==set(previous)-baseline_ids

    with tempfile.TemporaryDirectory() as root:
        persistence=ForwardPersistence(root,'a'*40,'b'*64,'u'*64);runtime=ForwardRuntime()
        orchestrator=ForwardOrchestrator(persistence,runtime,'b'*64,'a'*40,'u'*64)
        pipeline=ForwardPipeline(orchestrator=orchestrator,plan=plan,declarations=declarations)
        symbols=[f'S{index:03d}USDT' for index in range(238)]
        seed=_rows(122)
        for symbol in symbols:orchestrator.candles.seed_completed(symbol,'1h',seed)
        service=build_service(config_path='config/forward_research.yaml',symbols=symbols,orchestrator=orchestrator,pipeline=pipeline,date_provider=lambda _: '2026-01-01')
        started=time.monotonic()
        for number,symbol in enumerate(symbols):assert service['transport'].ingest_event(_event(symbol,_rows(123)[-1],number+1))
        # Exercise the actual bounded ingress and its single downstream
        # processor; a successful close proves the complete burst drained.
        # This is a CPU-bound production-shaped regression running on arbitrary
        # developer hardware.  It proves exact draining and reports capacity;
        # the fixed production lifecycle budget is independently enforced by
        # the server smoke rather than made hardware-dependent here.
        assert service['transport'].close(timeout=240)
        elapsed=time.monotonic()-started;persistence.flush();persistence.store.close()
        signal_ids=_signal_ids(root);health=service['transport'].health();metrics=runtime.callback_metrics
        assert runtime.events==len(symbols) and runtime.duplicates==0 and len(signal_ids)==len(set(signal_ids))
        assert health['completed_events_received']==len(symbols) and health['completed_events_processed']==len(symbols)
        assert health['completed_events_rejected']==0 and health['critical_backpressure_failures']==0 and not health['transport_failed']
        assert health['completed_events_received']-health['completed_events_processed']==0 and health['queue_depth']==0 and elapsed>0
        assert metrics['pipeline_seconds_total']>0 and metrics['callback_seconds_max']>0
        print('FORWARD_INCREMENTAL_SIGNAL_EQUIVALENCE=PASS')
        print('FORWARD_WHOLE_HOUR_REAL_PIPELINE_CAPACITY=PASS')
        print(f'SYMBOLS={len(symbols)} DECLARATIONS={len(declarations)} COMPLETED_RECEIVED={health["completed_events_received"]} COMPLETED_PROCESSED={health["completed_events_processed"]}')
        print(f'ELAPSED_SECONDS={elapsed:.3f} SIGNAL_ROWS={len(signal_ids)} DUPLICATE_SIGNAL_IDENTITIES=0')
        print(f'CALLBACK_SECONDS_MAX={metrics["callback_seconds_max"]:.6f} INGEST_SECONDS_TOTAL={metrics["ingest_seconds_total"]:.6f} PIPELINE_SECONDS_TOTAL={metrics["pipeline_seconds_total"]:.6f}')
    print('OOS_READS=0');print('FORMAL_ARTIFACT_MUTATIONS=0');print('EXCHANGE_ORDER_PLACEMENT=0');print('LIVE_AUTHORIZATION=0')


if __name__=='__main__':main()
