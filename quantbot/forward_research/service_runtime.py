"""Controlled public-only Forward service assembly; does not auto-connect."""
from __future__ import annotations
from .config import validate_config
from .websocket_transport import PublicWebsocketTransport
from .core import ForwardResearchError,assert_shadow_only
def build_service(*,config_path,symbols,orchestrator,date_provider,pipeline=None):
 config=validate_config(config_path);assert_shadow_only()
 if not symbols:raise ForwardResearchError('forward_service_symbols_required')
 if pipeline is not None:
  # The public service may only route the already-validated pipeline object;
  # it never accepts an evaluator, loader, parameters, or strategy injection.
  from .pipeline import ForwardPipeline
  if not isinstance(pipeline,ForwardPipeline) or pipeline.orchestrator is not orchestrator:raise ForwardResearchError('forward_service_pipeline_invalid')
 def on_event(event):
  date=date_provider(event.receive_time);result=orchestrator.ingest(event,date)
  if result=='COMPLETED' and pipeline is not None:
   pipeline.on_completed_candle(date=date,symbol=event.symbol,interval=event.interval)
  return result
 return {'config_identity':config['config_identity'],'transport':PublicWebsocketTransport(symbols,on_event),'checkpoint':orchestrator.checkpoint,'shadow_only':True,'oos_allowed':False,'orders_allowed':False,'pipeline_bound':pipeline is not None}
