"""Single-process Shadow coordinator: route public events without formal access."""
from __future__ import annotations
from .collector import CollectorState,MarketEvent
from .candle_state import CandleState
from .observations import cross_section
from .checkpoint import checkpoint_payload,write_checkpoint
from .core import assert_shadow_only
class ForwardOrchestrator:
 def __init__(self,persistence,runtime,config_identity,git_commit,universe_identity):
  assert_shadow_only();self.persistence=persistence;self.runtime=runtime;self.collector=CollectorState();self.candles=CandleState();self.config_identity=config_identity;self.git_commit=git_commit;self.universe_identity=universe_identity
 def ingest(self,event:MarketEvent,date):
  if not self.collector.accept(event):self.runtime.duplicates+=1;return 'DUPLICATE'
  self.runtime.ingest(event.identity(),event.event_time,event.receive_time);kind=self.candles.apply(event)
  self.persistence.append('candles' if event.closed else 'intrabar',date,{'symbol':event.symbol,'interval':event.interval,'event_time':event.event_time,'receive_time':event.receive_time,'open':event.open,'high':event.high,'low':event.low,'close':event.close,'volume':event.volume,'closed':event.closed})
  return kind
 def snapshot(self,date,timestamp,states):
  row=cross_section(timestamp,states);self.persistence.append('snapshots',date,row);return row
 def record_signal_bundle(self,date,signal,prices,opportunity=None,portfolio=None):
  """Persist already-authorized shadow evidence; no model call or order occurs here."""
  from .observations import observation
  from .exits import replay_variants
  self.persistence.append('signals',date,signal)
  path=observation(signal,prices);self.persistence.append('paths',date,path)
  for row in replay_variants(signal['direction'],signal['reference_price'],prices):self.persistence.append('exits',date,{**row,'signal_identity':signal.get('signal_identity')})
  if opportunity is not None:self.persistence.append('opportunities',date,opportunity)
  if portfolio is not None:self.persistence.append('portfolio',date,portfolio)
  return path
 def checkpoint(self,path):write_checkpoint(path,checkpoint_payload(self.runtime,self.config_identity,self.git_commit))
 def run_completed_models(self,date,symbol,interval,declarations):
  """Only closed candles enter frozen model observation execution."""
  from .model_runtime import run_scheduled_models
  rows=self.candles.completed.get(interval,[])
  result=run_scheduled_models(symbol,rows,declarations)
  for row in result['signals']:self.persistence.append('signals',date,row)
  for row in result['errors']:self.persistence.append('diagnostics',date,row)
  return result
 def detect_opportunities(self,date,symbol,interval,signals=(),selected_signal_ids=()):
  from .event_detector import detect_moves
  from .opportunity import match_opportunity
  events=detect_moves(symbol,self.candles.completed.get(interval,[]));matches=[]
  for event in events:
   self.persistence.append('opportunities',date,event);match=match_opportunity(event,signals,selected_signal_ids);self.persistence.append('opportunities',date,match);matches.append(match)
  return matches
 def shadow_portfolio(self,date,signals):
  from .observations import shadow_selection
  result=shadow_selection(signals);self.persistence.append('portfolio',date,result);return result
