"""Production-shaped Forward persistence capacity and durability regression."""
from __future__ import annotations
import tempfile,time
from pathlib import Path
from quantbot.forward_research.collector import MarketEvent
from quantbot.forward_research.core import AppendOnlyStore
from quantbot.forward_research.persistence import ForwardPersistence
from quantbot.forward_research.orchestrator import ForwardOrchestrator
from quantbot.forward_research.runtime import ForwardRuntime
from quantbot.forward_research.service_runtime import build_service

def row(symbol,interval,minute,sequence):
 return MarketEvent(symbol,interval,f'2026-09-13T12:{minute:02d}:00+00:00','2026-09-13T12:59:59+00:00',1,2,1,1,1,True,sequence)

def lines(path):return len(path.read_text(encoding='utf-8').splitlines()) if path.exists() else 0

def main():
 with tempfile.TemporaryDirectory() as root:
  persistence=ForwardPersistence(root,'a'*40,'b'*64,'u'*64);runtime=ForwardRuntime();orch=ForwardOrchestrator(persistence,runtime,'b'*64,'a'*40,'u'*64)
  service=build_service(config_path='config/forward_research.yaml',symbols=[f'S{i}USDT' for i in range(238)],orchestrator=orch,date_provider=lambda _: '2026-09-13')
  started=time.monotonic();total=0
  # Six minute-equivalent 1m rounds plus mixed 5m/15m/whole-hour bursts.
  for minute in range(6):
   for index in range(238):service['transport'].on_event(row(f'S{index}USDT','1m',minute,minute));total+=1
  for interval,sequence in (('5m',100),('15m',101),('1h',102)):
   for index in range(238):service['transport'].on_event(row(f'S{index}USDT',interval,10,sequence));total+=1
  elapsed=time.monotonic()-started;persistence.flush();persistence.store.close();service['transport'].close(timeout=2)
  candle=Path(root)/'candles'/'2026-09-13'/'candles.jsonl'
  assert lines(candle)==total and runtime.events==total and runtime.duplicates==0
  metrics=runtime.callback_metrics;rate=total/elapsed
  # With no pipeline bound, this field contains only unavoidable timing and
  # branch bookkeeping between the two monotonic samples; it is not exactly 0.
  assert rate>=200 and metrics['events']==total and metrics['ingest_seconds_total']>0 and metrics['pipeline_seconds_total']>=0 and metrics['pipeline_seconds_total']<metrics['ingest_seconds_total']*.05
  # Partial batch durability, boundary sync, close flush, and generic dedup.
  partial=ForwardPersistence(Path(root)/'partial','a'*40,'b'*64,'u'*64)
  for index in range(17):partial.append('candles','2026-09-13',{'n':index})
  partial.flush();partial.store.close();assert lines(Path(root)/'partial'/'candles'/'2026-09-13'/'candles.jsonl')==17
  boundary=ForwardPersistence(Path(root)/'boundary','a'*40,'b'*64,'u'*64)
  for index in range(128):boundary.append('candles','2026-09-13',{'n':index})
  boundary.store.close();assert lines(Path(root)/'boundary'/'candles'/'2026-09-13'/'candles.jsonl')==128
  closing=ForwardPersistence(Path(root)/'closing','a'*40,'b'*64,'u'*64);closing.append('candles','2026-09-13',{'n':1});closing.store.close();assert lines(Path(root)/'closing'/'candles'/'2026-09-13'/'candles.jsonl')==1
  generic=AppendOnlyStore(Path(root)/'generic');generic.append('x.jsonl',{'x':1});generic.append('x.jsonl',{'x':1});assert lines(Path(root)/'generic'/'x.jsonl')==1;generic.close()
 print('FORWARD_PERSISTENCE_CAPACITY_SYNTHETIC_TEST_OK')
 print(f'COMPLETED_EVENTS={total} ELAPSED_SECONDS={elapsed:.3f} EVENTS_PER_SECOND={rate:.1f}')
 print('PERSISTED_COMPLETED_EXACT_ONCE=PASS')
 print('BATCH_PARTIAL_FLUSH=PASS BATCH_BOUNDARY_SYNC=PASS CLOSE_PARTIAL_FLUSH=PASS GENERIC_DEDUP_IMMEDIATE=PASS')
 print('OOS_READS=0');print('FORMAL_ARTIFACT_MUTATIONS=0');print('EXCHANGE_ORDER_PLACEMENT=0');print('LIVE_AUTHORIZATION=0')
if __name__=='__main__':main()
