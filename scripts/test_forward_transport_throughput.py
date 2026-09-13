"""Synthetic production-shaped ingress test; no Binance connection is made."""
from __future__ import annotations
import time
from quantbot.forward_research.collector import MarketEvent
from quantbot.forward_research.websocket_transport import PublicWebsocketTransport
from quantbot.forward_research.production_runtime import _retire_reader_generation


def event(symbol, interval, sequence, closed=False):
    return MarketEvent(symbol,interval,f'2026-09-13T10:{sequence % 60:02d}:00+00:00','2026-09-13T10:10:00+00:00',1,2,1,1,1,closed,sequence)


def main():
    processed=[];errors=[]
    def slow_callback(row):
        time.sleep(.00025);processed.append(row.identity())
    transport=PublicWebsocketTransport([f'S{i}USDT' for i in range(240)],slow_callback,on_error=lambda source,exc:errors.append((source,str(exc))),ingress_capacity=240)
    intervals=('1m','5m','15m','1h');expected=[];started=time.monotonic()
    for repeat in range(8):
        for index in range(240):
            symbol=f'S{index}USDT'
            for interval in intervals:
                transport.ingest_event(event(symbol,interval,repeat,False))
    # Critical close evidence must survive a saturated mutable lane.
    for index in range(240):
        for interval in intervals:
            row=event(f'S{index}USDT',interval,1000+index,True);expected.append(row.identity());transport.ingest_event(row)
    assert transport.retire_and_drain(timeout=15)
    health=transport.health();transport.close(timeout=3)
    assert set(expected).issubset(processed) and len([item for item in processed if item in set(expected)])==len(expected)
    assert health['completed_events_received']==health['completed_events_processed']==960
    assert health['queue_high_water_mark']<=1200 and health['intrabar_events_coalesced']>0 and health['processing_exceptions']==0
    # A processor exception is observable and does not kill the worker thread.
    calls=[];fail_once={'value':True};faults=[]
    def flaky(row):
        if fail_once['value']:fail_once['value']=False;raise RuntimeError('synthetic_callback_failure')
        calls.append(row.identity())
    second=PublicWebsocketTransport(['XUSDT'],flaky,on_error=lambda source,exc:faults.append(source),ingress_capacity=2)
    first=event('XUSDT','1m',1,True);next_row=event('XUSDT','1m',2,True);second.ingest_event(first);second.ingest_event(next_row);assert second.retire_and_drain(timeout=3);health2=second.health();second.close(timeout=3)
    assert health2['processing_exceptions']==1 and faults==['forward_processor'] and next_row.identity() in calls
    # Critical memory is finite.  A stalled processor cannot make close
    # evidence accumulate without bound: admission waits briefly then fails
    # closed with an explicit rejected-close counter.
    stalled=[];saturation_errors=[]
    def stalled_callback(row):
        time.sleep(.08);stalled.append(row.identity())
    bounded=PublicWebsocketTransport(['BUSDT'],stalled_callback,on_error=lambda source,exc:saturation_errors.append(source),ingress_capacity=2,critical_capacity=2,critical_put_timeout=.01)
    accepted=[bounded.ingest_event(event('BUSDT','1m',100+i,True)) for i in range(8)]
    bounded.retire_and_drain(timeout=3);bounded_health=bounded.health();bounded.close(timeout=3)
    assert bounded_health['critical_capacity']==2 and bounded_health['queue_high_water_mark']<=4
    assert bounded_health['critical_backpressure_failures']==1 and bounded_health['completed_events_rejected']==1 and bounded_health['transport_failed'] is True
    assert bounded_health['completed_events_processed']==bounded_health['completed_events_received'] and accepted.count(False)>=1
    # Production-shaped rollover: roughly the observed 900 mutable entries
    # are explicitly retired, while all already accepted closes drain.
    rollover_processed=[]
    def rollover_callback(row):
        time.sleep(.001);rollover_processed.append(row.identity())
    rollover=PublicWebsocketTransport([f'R{i}USDT' for i in range(240)],rollover_callback,ingress_capacity=2048,critical_capacity=1024,critical_put_timeout=1)
    rollover_closes=[]
    for index in range(235):
        for interval in intervals:
            rollover.ingest_event(event(f'R{index}USDT',interval,index,False))
    for index in range(235):
        row=event(f'R{index}USDT','1m',2000+index,True);rollover_closes.append(row.identity());assert rollover.ingest_event(row)
    assert rollover.retire_and_drain(timeout=5);rollover_health=rollover.health();rollover.close(timeout=3)
    assert rollover_health['intrabar_events_retired']>=900 and rollover_health['completed_events_received']==rollover_health['completed_events_processed']==235
    assert set(rollover_closes).issubset(rollover_processed) and rollover_health['completed_events_rejected']==0 and rollover_health['critical_backpressure_failures']==0
    # Generation retirement closes ingress first, then drains already received
    # final closes exactly once before a replacement transport is created.
    retired=[];third=PublicWebsocketTransport(['RUSDT'],lambda row:retired.append(row.identity()),ingress_capacity=1)
    close=event('RUSDT','1h',9,True);third.ingest_event(event('RUSDT','1m',8,False));third.ingest_event(close);assert third.retire_and_drain(timeout=3) and close.identity() in retired and third.ingest_event(event('RUSDT','1m',10,False)) is False;third.close(timeout=3)
    class StuckReader:
        name='stuck-reader'
        def join(self,timeout):self.timeout=timeout
        def is_alive(self):return True
    class RetiredTransport:
        def __init__(self):self.closed=False
        def close(self,timeout):self.closed=True;return True
    fake=RetiredTransport()
    try:_retire_reader_generation([StuckReader()],fake,join_timeout=0,drain_timeout=0);raise AssertionError('reader timeout accepted')
    except Exception as exc:assert 'reader_shutdown_timeout' in str(exc) and fake.closed
    print('FORWARD_TRANSPORT_THROUGHPUT_SYNTHETIC_TEST_OK')
    print(f"INGRESS_SECONDS={time.monotonic()-started:.3f}")
    print('SYMBOLS=240 INTERVALS=4 COMPLETED_PRESERVED=960')
    print('BACKPRESSURE_INTRABAR_COALESCING=PASS')
    print('PROCESSOR_FAILURE_OBSERVABLE=PASS')
    print('GENERATION_ROLLOVER_COMPLETED_DRAIN=PASS')
    print('BROAD_MARKET_MUTABLE_ROLLOVER_RETIREMENT=PASS')
    print('CRITICAL_CAPACITY_FAIL_CLOSED=PASS')
    print('READER_SHUTDOWN_TIMEOUT_FAIL_CLOSED=PASS')
    print('OOS_READS=0');print('FORMAL_ARTIFACT_MUTATIONS=0');print('EXCHANGE_ORDER_PLACEMENT=0');print('LIVE_AUTHORIZATION=0')

if __name__=='__main__':main()
