"""Controlled public-only Forward service assembly; does not auto-connect."""
from __future__ import annotations
from .config import validate_config
from .websocket_transport import PublicWebsocketTransport
from .core import ForwardResearchError,assert_shadow_only
import time
def build_service(*,config_path,symbols,orchestrator,date_provider,pipeline=None):
 config=validate_config(config_path);assert_shadow_only()
 if not symbols:raise ForwardResearchError('forward_service_symbols_required')
 if pipeline is not None:
  # The public service may only route the already-validated pipeline object;
  # it never accepts an evaluator, loader, parameters, or strategy injection.
  from .pipeline import ForwardPipeline
  if not isinstance(pipeline,ForwardPipeline) or pipeline.orchestrator is not orchestrator:raise ForwardResearchError('forward_service_pipeline_invalid')
 def on_event(event):
  started=time.monotonic();date=date_provider(event.receive_time);result=orchestrator.ingest(event,date);ingest_seconds=time.monotonic()-started
  # The public collector can retain multiple evidence intervals, while model
  # execution is pinned to the single N5 protocol timeframe.
  if result=='COMPLETED' and pipeline is not None and event.interval==pipeline.plan.get('protocol_scope',{}).get('timeframe'):
   pipeline.on_completed_candle(date=date,symbol=event.symbol,interval=event.interval)
  total=time.monotonic()-started;metrics=orchestrator.runtime.callback_metrics;metrics['events']=metrics.get('events',0)+1;metrics['ingest_seconds_total']=metrics.get('ingest_seconds_total',0.0)+ingest_seconds;metrics['pipeline_seconds_total']=metrics.get('pipeline_seconds_total',0.0)+max(0.0,total-ingest_seconds);metrics['callback_seconds_max']=max(metrics.get('callback_seconds_max',0.0),total)
  return result
 def on_transport_error(source,exc):
  orchestrator.collector.record_error(source,exc)
  orchestrator.runtime.errors+=1
  orchestrator.runtime.reconnects+=1
 return {'config_identity':config['config_identity'],'transport':PublicWebsocketTransport(symbols,on_event,on_error=on_transport_error),'checkpoint':orchestrator.checkpoint,'shadow_only':True,'oos_allowed':False,'orders_allowed':False,'pipeline_bound':pipeline is not None}
