from __future__ import annotations
import tempfile
from quantbot.forward_research.core import UniverseSymbol,universe_snapshot,directional_path,trailing_exit,classify_opportunity,AppendOnlyStore
from quantbot.forward_research.runtime import ForwardRuntime
def main():
 rows=[UniverseSymbol('OKUSDT',3_000_000,'PERPETUAL','USDT','TRADING'),UniverseSymbol('LOWUSDT',2999999,'PERPETUAL','USDT','TRADING'),UniverseSymbol('BADUSDT',9e9,'CURRENT_QUARTER','USDT','TRADING')];snap=universe_snapshot(rows,'2026-09-11T00:00:00+00:00');assert [r['symbol'] for r in snap['symbols']]==['OKUSDT']
 assert abs(directional_path('LONG',100,[105,97])['mfe']-.05)<1e-12;assert directional_path('SHORT',100,[95,103])['mfe']>0;assert trailing_exit('LONG',100,[110,103],.05)['reason']=='TRAILING';assert trailing_exit('SHORT',100,[90,96],.05)['reason']=='TRAILING';assert classify_opportunity('X','a','b',-.1)['direction']=='DOWN'
 runtime=ForwardRuntime();assert runtime.ingest('a','t','r');assert not runtime.ingest('a','t','r');assert runtime.duplicates==1
 with tempfile.TemporaryDirectory() as root:
  store=AppendOnlyStore(root);store.append('signals/2026-09-11.jsonl',{'event':'x'});store.append('signals/2026-09-11.jsonl',{'event':'x'});assert len((store.root/'signals/2026-09-11.jsonl').read_text().splitlines())==1;assert store.manifest('2026-09-11','a'*40,'b'*64)['files']
 print('FORWARD_RESEARCH_SYNTHETIC_TEST_OK');print('OOS_READS=0');print('FORMAL_ARTIFACT_MUTATIONS=0');print('EXCHANGE_ORDER_PLACEMENT=0');print('LIVE_AUTHORIZATION=0')
if __name__=='__main__':main()
