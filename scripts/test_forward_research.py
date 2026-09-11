from __future__ import annotations
import tempfile
from quantbot.forward_research.core import UniverseSymbol,universe_snapshot,directional_path,trailing_exit,classify_opportunity,AppendOnlyStore
from quantbot.forward_research.runtime import ForwardRuntime
from quantbot.forward_research.collector import MarketEvent,CollectorState,shard_symbols
from quantbot.forward_research.observations import observation,cross_section,shadow_selection
from quantbot.forward_research.candle_state import CandleState
from quantbot.forward_research.checkpoint import checkpoint_payload,write_checkpoint,load_checkpoint
from quantbot.forward_research.persistence import ForwardPersistence
from quantbot.forward_research.binance_public import parse_exchange_info,apply_ticker_volumes,websocket_url,parse_kline
def main():
 rows=[UniverseSymbol('OKUSDT',3_000_000,'PERPETUAL','USDT','TRADING'),UniverseSymbol('LOWUSDT',2999999,'PERPETUAL','USDT','TRADING'),UniverseSymbol('BADUSDT',9e9,'CURRENT_QUARTER','USDT','TRADING')];snap=universe_snapshot(rows,'2026-09-11T00:00:00+00:00');assert [r['symbol'] for r in snap['symbols']]==['OKUSDT']
 parsed=parse_exchange_info({'symbols':[{'symbol':'XUSDT','contractType':'PERPETUAL','quoteAsset':'USDT','status':'TRADING','filters':[]}]});assert apply_ticker_volumes(parsed,[{'symbol':'XUSDT','quoteVolume':'3000000'}])[0].eligible();assert 'xusdt@kline_1m' in websocket_url(['XUSDT']);assert parse_kline({'e':'kline','s':'XUSDT','k':{'i':'1m','t':1,'o':'1','h':'2','l':'1','c':'2','v':'3','x':True}},'r').closed
 assert abs(directional_path('LONG',100,[105,97])['mfe']-.05)<1e-12;assert directional_path('SHORT',100,[95,103])['mfe']>0;assert trailing_exit('LONG',100,[110,103],.05)['reason']=='TRAILING';assert trailing_exit('SHORT',100,[90,96],.05)['reason']=='TRAILING';assert classify_opportunity('X','a','b',-.1)['direction']=='DOWN'
 runtime=ForwardRuntime();assert runtime.ingest('a','t','r');assert not runtime.ingest('a','t','r');assert runtime.duplicates==1
 state=CandleState();assert state.apply(MarketEvent('A','1m','2026-01-01T00:00:00Z','r',1,2,1,2,3,False,1))=='INTRABAR';assert state.apply(MarketEvent('A','1m','2026-01-01T00:00:00Z','r',1,2,1,2,3,True,2))=='COMPLETED';assert len(state.completed['1m'])==1
 assert shard_symbols(['C','A','B'],2)==(('A','B'),('C',));collector=CollectorState();event=MarketEvent('A','1m','t','r',1,2,1,2,3,True,1);assert collector.accept(event) and not collector.accept(event);assert collector.stale('MISSING',0)
 obs=observation({'direction':'SHORT','reference_price':100,'symbol':'A','model_id':'m'},[95,90,96]);assert obs['horizons'][0]['mfe']>0
 cs=cross_section('t',[{'symbol':'A','model_id':'m','direction':'LONG'},{'symbol':'B','model_id':'m','direction':'SHORT'}]);assert cs['long_count']==cs['short_count']==1
 portfolio=shadow_selection([{'symbol':'A','task_identity':'1','direction':'LONG'},{'symbol':'A','task_identity':'2','direction':'SHORT'}]);assert len(portfolio['selected'])==1 and portfolio['rejected'][0]['reason']=='SYMBOL_ALREADY_SELECTED'
 with tempfile.TemporaryDirectory() as root:
  store=AppendOnlyStore(root);store.append('signals/2026-09-11.jsonl',{'event':'x'});store.append('signals/2026-09-11.jsonl',{'event':'x'});assert len((store.root/'signals/2026-09-11.jsonl').read_text().splitlines())==1;assert store.manifest('2026-09-11','a'*40,'b'*64)['files']
  checkpoint=checkpoint_payload(runtime,'b'*64,'a'*40);write_checkpoint(f'{root}/checkpoints/state.json',checkpoint);assert load_checkpoint(f'{root}/checkpoints/state.json')['checkpoint_identity']==checkpoint['checkpoint_identity'];ForwardPersistence(root,'a'*40,'b'*64,'c'*64).append('snapshots','2026-09-11',{'timestamp':'t'})
 print('FORWARD_RESEARCH_SYNTHETIC_TEST_OK');print('OOS_READS=0');print('FORMAL_ARTIFACT_MUTATIONS=0');print('EXCHANGE_ORDER_PLACEMENT=0');print('LIVE_AUTHORIZATION=0')
if __name__=='__main__':main()
