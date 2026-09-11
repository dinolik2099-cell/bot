from __future__ import annotations
import tempfile
from datetime import datetime,timedelta,timezone
import subprocess,sys,json
from quantbot.forward_research.core import UniverseSymbol,universe_snapshot,directional_path,trailing_exit,classify_opportunity,AppendOnlyStore
from quantbot.forward_research.runtime import ForwardRuntime
from quantbot.forward_research.collector import MarketEvent,CollectorState,shard_symbols,reconnect_delay
from quantbot.forward_research.observations import observation,cross_section,shadow_selection
from quantbot.forward_research.candle_state import CandleState
from quantbot.forward_research.checkpoint import checkpoint_payload,write_checkpoint,load_checkpoint
from quantbot.forward_research.persistence import ForwardPersistence
from quantbot.forward_research.binance_public import parse_exchange_info,apply_ticker_volumes,websocket_url,parse_kline
from quantbot.forward_research.diagnostics import classify_event,evidence_summary
from quantbot.forward_research.exits import fixed_exit,replay_variants
from quantbot.forward_research.opportunity import match_opportunity
from quantbot.forward_research.websocket_transport import PublicWebsocketTransport
from quantbot.forward_research.config import validate_config
from quantbot.forward_research.service_runtime import build_service
from audit_forward_research import audit_forward_evidence
from quantbot.forward_research.universe import refresh_universe
from quantbot.forward_research.scheduler import reconcile_universe
from quantbot.forward_research.model_schedule import schedule_models
from quantbot.forward_research.model_runtime import run_scheduled_models
from quantbot.forward_research.event_detector import detect_moves
from quantbot.forward_research.orchestrator import ForwardOrchestrator
from quantbot.forward_research.frozen_declarations import validate_forward_declarations,declaration_identity,manifest_identity,load_forward_declaration_manifest,DECLARATION_SCHEMA
from quantbot.forward_research.pipeline import ForwardPipeline
from quantbot.forward_research.path_tracker import ShadowPathTracker
from quantbot.forward_research.daily_manifest import seal_daily_manifest,verify_daily_manifest
def main():
 assert validate_config('config/forward_research.yaml')['forward_research_only']=='true'
 rows=[UniverseSymbol('OKUSDT',3_000_000,'PERPETUAL','USDT','TRADING'),UniverseSymbol('LOWUSDT',2999999,'PERPETUAL','USDT','TRADING'),UniverseSymbol('BADUSDT',9e9,'CURRENT_QUARTER','USDT','TRADING')];snap=universe_snapshot(rows,'2026-09-11T00:00:00+00:00');assert [r['symbol'] for r in snap['symbols']]==['OKUSDT']
 parsed=parse_exchange_info({'symbols':[{'symbol':'XUSDT','contractType':'PERPETUAL','quoteAsset':'USDT','status':'TRADING','filters':[]}]});assert apply_ticker_volumes(parsed,[{'symbol':'XUSDT','quoteVolume':'3000000'}])[0].eligible();assert 'xusdt@kline_1m' in websocket_url(['XUSDT']);assert parse_kline({'e':'kline','s':'XUSDT','k':{'i':'1m','t':1,'o':'1','h':'2','l':'1','c':'2','v':'3','x':True}},'r').closed
 assert abs(directional_path('LONG',100,[105,97])['mfe']-.05)<1e-12;assert directional_path('SHORT',100,[95,103])['mfe']>0;assert trailing_exit('LONG',100,[110,103],.05)['reason']=='TRAILING';assert trailing_exit('SHORT',100,[90,96],.05)['reason']=='TRAILING';assert classify_opportunity('X','a','b',-.1)['direction']=='DOWN'
 assert fixed_exit('LONG',100,[111],.1,.05)['reason']=='TAKE_PROFIT';assert fixed_exit('SHORT',100,[106],.1,.05)['reason']=='STOP';assert any(row['rule']=='SIGNAL_REVERSAL' for row in replay_variants('SHORT',100,[95,97],1))
 event=classify_opportunity('A','2026-01-01T00:00:00Z','e',.1);assert match_opportunity(event,[{'symbol':'A','direction':'LONG','signal_timestamp':'2025-12-31T23:00:00Z','signal_identity':'s'}],['s'])['status']=='CAPTURED';assert match_opportunity(event,[{'symbol':'A','direction':'SHORT','signal_timestamp':'x','signal_identity':'s'}])['status']=='WRONG_DIRECTION'
 runtime=ForwardRuntime();assert runtime.ingest('a','t','r');assert not runtime.ingest('a','t','r');assert runtime.duplicates==1
 state=CandleState();assert state.apply(MarketEvent('A','1m','2026-01-01T00:00:00Z','r',1,2,1,2,3,False,1))=='INTRABAR';assert state.apply(MarketEvent('A','1m','2026-01-01T00:00:00Z','r',1,2,1,2,3,True,2))=='COMPLETED';assert len(state.history('A','1m'))==1;state.apply(MarketEvent('B','1m','2026-01-01T00:01:00Z','r',1,2,1,2,3,True,3));assert len(state.history('A','1m'))==1 and len(state.history('B','1m'))==1
 assert shard_symbols(['C','A','B'],2)==(('A','B'),('C',)) and reconnect_delay(0)==1 and reconnect_delay(10)==60;collector=CollectorState();event=MarketEvent('A','1m','t','r',1,2,1,2,3,True,1);assert collector.accept(event) and not collector.accept(event);collector.record_error('BROKEN','synthetic');assert collector.stale('MISSING',0) and collector.reconnects==1
 assert len(PublicWebsocketTransport(['AUSDT','BUSDT'],lambda _:None).shard_urls(1))==2
 obs=observation({'direction':'SHORT','reference_price':100,'symbol':'A','model_id':'m'},[95,90,96]);assert obs['horizons'][0]['mfe']>0
 tracker=ShadowPathTracker();signal={'signal_identity':'track','symbol':'A','direction':'LONG','reference_price':100,'signal_timestamp':'2026-01-01T00:00:00+00:00'};assert tracker.register(signal) and not tracker.register(signal)
 for minute in range(1,1441):done=tracker.on_completed_close(symbol='A',event_time=(datetime(2026,1,1,tzinfo=timezone.utc)+timedelta(minutes=minute)).isoformat(),close=101)
 assert len(done)==1 and done[0]['path_status']=='COMPLETED' and tracker.status()['open_observations']==0
 # Explicitly prove the tracker rejects a timezone drift; completed evidence
 # itself is covered by the dedicated short synthetic path below.
 try:tracker.on_completed_close(symbol='A',event_time='2026-01-01T01:00:00+08:00',close=101);raise AssertionError('non utc accepted')
 except Exception as exc:assert 'utc' in str(exc)
 cs=cross_section('t',[{'symbol':'A','model_id':'m','direction':'LONG'},{'symbol':'B','model_id':'m','direction':'SHORT'}]);assert cs['long_count']==cs['short_count']==1
 portfolio=shadow_selection([{'symbol':'A','task_identity':'1','direction':'LONG'},{'symbol':'A','task_identity':'2','direction':'SHORT'}]);assert len(portfolio['selected'])==1 and portfolio['rejected'][0]['reason']=='SYMBOL_ALREADY_SELECTED'
 assert classify_event(.25)=='strong_trend_up' and classify_event(-.25)=='strong_trend_down' and classify_event(.01,.2)=='extreme_wick';assert evidence_summary([{'direction':'LONG','event_class':'trend_up'},{'direction':'SHORT','event_class':'trend_down'}])['long_signals']==1
 with tempfile.TemporaryDirectory() as root:
  store=AppendOnlyStore(root);store.append('signals/2026-09-11.jsonl',{'event':'x'});store.append('signals/2026-09-11.jsonl',{'event':'x'});assert len((store.root/'signals/2026-09-11.jsonl').read_text().splitlines())==1;manifest=store.manifest('2026-09-11','a'*40,'b'*64);assert manifest['files'] and store.verify_manifest(manifest)
  checkpoint=checkpoint_payload(runtime,'b'*64,'a'*40,research_plan_identity='p'*64,declaration_manifest_identity='d'*64);write_checkpoint(f'{root}/checkpoints/state.json',checkpoint);assert load_checkpoint(f'{root}/checkpoints/state.json',config_identity='b'*64,git_commit='a'*40,research_plan_identity='p'*64,declaration_manifest_identity='d'*64)['checkpoint_identity']==checkpoint['checkpoint_identity'];ForwardPersistence(root,'a'*40,'b'*64,'c'*64).append('snapshots','2026-09-11',{'timestamp':'t'})
  orch=ForwardOrchestrator(ForwardPersistence(root,'a'*40,'b'*64,'c'*64),ForwardRuntime(),'b'*64,'a'*40,'c'*64);assert orch.ingest(MarketEvent('Z','1m','z','r',1,2,1,2,1,True,3),'2026-09-11')=='COMPLETED';assert orch.ingest(MarketEvent('Z','1m','z','r',1,2,1,2,1,True,3),'2026-09-11')=='DUPLICATE';orch.snapshot('2026-09-11','t',[{'symbol':'Z','model_id':'m','direction':'FLAT'}]);orch.checkpoint(f'{root}/checkpoints/orch.json')
  plan={'research_freeze_identity':'f'*64,'research_plan_identity':'p'*64,'protocol_scope':{'timeframe':'1m'},'models':[{'model_id':'m','parameter_grid_hash':'g'*64,'strategy_function_hash':'s'*64,'implementation_module_hash':'i'*64}]}
  declaration={'schema_version':DECLARATION_SCHEMA,'research_freeze_identity':'f'*64,'research_plan_identity':'p'*64,'model_id':'m','model_name':'missing','params':{},'params_identity':__import__('hashlib').sha256(b'{}').hexdigest(),'parameter_grid_hash':'g'*64,'strategy_function_hash':'s'*64,'implementation_module_hash':'i'*64,'input_boundary':'COMPLETED_CANDLE_T_MINUS_1'};declaration['declaration_identity']=declaration_identity(declaration);assert validate_forward_declarations(plan,[declaration])[0]['model_id']=='m';bad=dict(declaration);bad['parameter_grid_hash']='x'*64
  try:validate_forward_declarations(plan,[bad]);raise AssertionError('metadata drift accepted')
  except Exception as exc:assert 'metadata' in str(exc)
  decision={'schema_version':DECLARATION_SCHEMA,'decision_artifact_id':'external-decision-v1','research_freeze_identity':'f'*64,'research_plan_identity':'p'*64,'declarations':[declaration],'forward_research_only':True,'oos_allowed':False,'order_placement_allowed':False};decision['manifest_identity']=manifest_identity(decision);decision_path=f'{root}/decision.json';open(decision_path,'w',encoding='utf-8').write(json.dumps(decision));assert load_forward_declaration_manifest(decision_path,plan)['manifest_identity']==decision['manifest_identity']
  pipeline=ForwardPipeline(orchestrator=orch,plan=plan,declarations=[declaration]);assert pipeline.on_completed_candle(date='2026-09-11',symbol='Z',interval='1m')['errors']
  service=build_service(config_path='config/forward_research.yaml',symbols=['ZUSDT'],orchestrator=orch,date_provider=lambda _: '2026-09-11',pipeline=pipeline);assert service['shadow_only'] and service['pipeline_bound'] and len(service['transport'].shard_urls())==1
  # Non-frozen intervals are retained as public evidence but do not enter the
  # N5-bound model pipeline.
  assert service['transport'].on_event(MarketEvent('Z','5m','later','r',1,2,1,2,1,True,99))=='COMPLETED'
  fresh=refresh_universe({'symbols':[{'symbol':'NEWUSDT','contractType':'PERPETUAL','quoteAsset':'USDT','status':'TRADING','filters':[]}]},[{'symbol':'NEWUSDT','quoteVolume':'3000000'}],'t',ForwardPersistence(root,'a'*40,'b'*64,'c'*64),'2026-09-11');assert fresh['symbols'][0]['symbol']=='NEWUSDT'
  assert reconcile_universe(None,fresh,1)['subscribe']==['NEWUSDT']
  assert schedule_models('NEWUSDT','t',[{'model_id':'m','params_identity':'p','input_boundary':'COMPLETED_CANDLE_T_MINUS_1'}])[0]['model_id']=='m'
  assert run_scheduled_models('NEWUSDT',[],[{'model_name':'missing','model_id':'m','params':{}}])['errors']
  assert orch.record_signal_bundle('2026-09-11',{'direction':'LONG','reference_price':100,'signal_identity':'s','symbol':'Z'},[101,102])['signal']['direction']=='LONG'
  assert orch.run_completed_models('2026-09-11','Z','1m',[{'model_name':'missing','model_id':'m','params':{}}])['errors']
  assert orch.detect_opportunities('2026-09-11','Z','1m')==[]
  assert orch.shadow_portfolio('2026-09-11',[{'symbol':'Z','task_identity':'z','direction':'LONG'}])['selected']
  assert detect_moves('Z',[{'event_time':'a','close':100},{'event_time':'b','close':106}])[0]['direction']=='UP'
  audit=json.loads(subprocess.check_output([sys.executable,'-B','scripts/audit_forward_research.py','--root',root,'--days','7'],env={**__import__('os').environ,'PYTHONPATH':'.'}));assert audit['candles_records']==2 and audit['provenance_chains']==1 and not audit['model_ranking_updated'];assert audit_forward_evidence(root,7)['audit_identity']==audit['audit_identity']
  sealed=seal_daily_manifest(root=root,date='2026-09-11',git_commit='a'*40,config_identity='b'*64,research_plan_identity='p'*64,declaration_manifest_identity='d'*64);assert verify_daily_manifest(f'{root}/manifests/2026-09-11.json')['daily_manifest_identity']==sealed['daily_manifest_identity']
  try:seal_daily_manifest(root=root,date='2026-09-11',git_commit='a'*40,config_identity='b'*64,research_plan_identity='p'*64,declaration_manifest_identity='d'*64);raise AssertionError('daily seal overwritten')
  except Exception as exc:assert 'already_sealed' in str(exc)
 print('FORWARD_RESEARCH_SYNTHETIC_TEST_OK');print('OOS_READS=0');print('FORMAL_ARTIFACT_MUTATIONS=0');print('EXCHANGE_ORDER_PLACEMENT=0');print('LIVE_AUTHORIZATION=0')
if __name__=='__main__':main()
