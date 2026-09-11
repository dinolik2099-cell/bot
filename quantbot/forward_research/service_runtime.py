"""Controlled public-only Forward service assembly; does not auto-connect."""
from __future__ import annotations
from .config import validate_config
from .websocket_transport import PublicWebsocketTransport
from .core import ForwardResearchError,assert_shadow_only
def build_service(*,config_path,symbols,orchestrator,date_provider):
 config=validate_config(config_path);assert_shadow_only()
 if not symbols:raise ForwardResearchError('forward_service_symbols_required')
 def on_event(event):orchestrator.ingest(event,date_provider(event.receive_time))
 return {'config_identity':config['config_identity'],'transport':PublicWebsocketTransport(symbols,on_event),'checkpoint':orchestrator.checkpoint,'shadow_only':True,'oos_allowed':False,'orders_allowed':False}
