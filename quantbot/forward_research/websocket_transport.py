"""Public websocket ingress separated from the single canonical processor."""
from __future__ import annotations
from collections import deque
import json
import threading
import time
from .binance_public import websocket_url, parse_kline
from .collector import reconnect_delay
from .core import assert_shadow_only


class ForwardTransportBackpressureError(RuntimeError):
    pass


class _Ingress:
    """Bounded mutable ingress plus a protected completed-candle lane."""
    def __init__(self, callback, on_error, capacity=8192, critical_capacity=2048, critical_put_timeout=5.0):
        if type(capacity) is not int or capacity < 1 or type(critical_capacity) is not int or critical_capacity < 1 or critical_put_timeout <= 0: raise ValueError('forward_ingress_capacity_invalid')
        self.callback,self.on_error,self.capacity,self.critical_capacity,self.critical_put_timeout=callback,on_error,capacity,critical_capacity,critical_put_timeout;self._critical=deque();self._intrabar={};self._lock=threading.Condition();self._accepting=True;self._stopped=False;self._failed=False;self._processing=0
        self.metrics={'raw_frames_received':0,'events_parsed':0,'queue_depth':0,'queue_high_water_mark':0,'intrabar_capacity':capacity,'critical_capacity':critical_capacity,'completed_events_received':0,'completed_events_processed':0,'completed_events_rejected':0,'critical_backpressure_failures':0,'intrabar_events_processed':0,'intrabar_events_coalesced':0,'intrabar_events_dropped':0,'processor_lag_seconds':0.0,'processing_exceptions':0,'transport_failed':False}
        self._thread=threading.Thread(target=self._consume,daemon=True,name='forward-canonical-processor');self._thread.start()
    def _depth(self): return len(self._critical)+len(self._intrabar)
    def raw_frame(self):
        with self._lock:self.metrics['raw_frames_received']+=1
    def put(self,event):
        with self._lock:
            if not self._accepting:return False
            self.metrics['events_parsed']+=1
            if event.closed:
                deadline=time.monotonic()+self.critical_put_timeout
                while self._accepting and len(self._critical)>=self.critical_capacity:
                    remaining=deadline-time.monotonic()
                    if remaining<=0:
                        self._failed=True;self._accepting=False;self.metrics['completed_events_rejected']+=1;self.metrics['critical_backpressure_failures']+=1;self.metrics['transport_failed']=True;self._lock.notify_all();return False
                    self._lock.wait(min(.25,remaining))
                if not self._accepting:return False
                self._critical.append((time.monotonic(),event));self.metrics['completed_events_received']+=1
            else:
                key=(event.symbol,event.interval)
                if key in self._intrabar:self.metrics['intrabar_events_coalesced']+=1
                elif len(self._intrabar)>=self.capacity:self.metrics['intrabar_events_dropped']+=1;return False
                self._intrabar[key]=(time.monotonic(),event)
            depth=self._depth();self.metrics['queue_depth']=depth;self.metrics['queue_high_water_mark']=max(self.metrics['queue_high_water_mark'],depth);self._lock.notify();return True
    def _next(self):
        with self._lock:
            while not self._stopped and not self._critical and not self._intrabar:self._lock.wait(.25)
            if self._critical:self._processing+=1;return self._critical.popleft()
            if self._intrabar:
                key=min(self._intrabar);self._processing+=1;return self._intrabar.pop(key)
            return None
    def _consume(self):
        while True:
            item=self._next()
            if item is None:
                if self._stopped:return
                continue
            enqueued,event=item
            try:
                self.callback(event)
                with self._lock:
                    key='completed_events_processed' if event.closed else 'intrabar_events_processed';self.metrics[key]+=1;self._processing-=1;self.metrics['processor_lag_seconds']=max(0.0,time.monotonic()-enqueued);self.metrics['queue_depth']=self._depth();self._lock.notify_all()
            except Exception as exc:
                with self._lock:self.metrics['processing_exceptions']+=1;self._processing-=1;self.metrics['queue_depth']=self._depth();self._lock.notify_all()
                if self.on_error is not None:
                    try:self.on_error('forward_processor',exc)
                    except Exception:pass
    def retire_and_drain(self,timeout=30):
        deadline=time.monotonic()+timeout
        with self._lock:
            self._accepting=False
            while self._critical or self._intrabar or self._processing:
                remaining=deadline-time.monotonic()
                if remaining<=0:return False
                self._lock.wait(min(.25,remaining))
            return not self._failed
    def close(self,timeout=30):
        drained=self.retire_and_drain(timeout)
        with self._lock:self._stopped=True;self._lock.notify_all()
        self._thread.join(timeout=max(0.0,timeout));return drained and not self._thread.is_alive() and not self._failed
    def health(self):
        with self._lock:return dict(self.metrics)


class PublicWebsocketTransport:
    """Many fast public readers feeding one safe canonical downstream lane."""
    def __init__(self,symbols,on_event,clock=time.sleep,on_error=None,ingress_capacity=8192,critical_capacity=2048,critical_put_timeout=5.0):
        self.symbols=tuple(symbols);self.on_event=on_event;self.clock=clock;self.on_error=on_error;self._ingress=_Ingress(on_event,on_error,ingress_capacity,critical_capacity,critical_put_timeout)
    def shard_urls(self,max_per_shard=200):
        from .collector import shard_symbols
        return tuple(websocket_url(shard) for shard in shard_symbols(self.symbols,max_per_shard))
    def ingest_event(self,event): return self._ingress.put(event)
    def health(self): return self._ingress.health()
    def retire_and_drain(self,timeout=30): return self._ingress.retire_and_drain(timeout)
    def close(self,timeout=30): return self._ingress.close(timeout)
    def run_shard(self,url,connect,receive_time,should_stop=lambda:False):
        assert_shadow_only();attempt=0
        while not should_stop():
            socket=None
            try:
                socket=connect(url)
                for raw in socket:
                    if should_stop():return
                    self._ingress.raw_frame();event=parse_kline(json.loads(raw),receive_time())
                    if not self._ingress.put(event) and event.closed:
                        raise ForwardTransportBackpressureError('forward_completed_ingress_capacity_exhausted')
                attempt=0
            except ForwardTransportBackpressureError as exc:
                if self.on_error is not None:
                    try:self.on_error('forward_completed_backpressure',exc)
                    except Exception:pass
                return
            except Exception as exc:
                if should_stop():return
                if self.on_error is not None:
                    try:self.on_error('websocket_shard',exc)
                    except Exception:pass
                self.clock(reconnect_delay(attempt));attempt+=1
            finally:
                if socket is not None:
                    try:socket.close()
                    except Exception:pass
