"""Separate immutable completed candle history from mutable intrabar observation state."""
from __future__ import annotations
from dataclasses import dataclass,field
from .collector import MarketEvent
from .core import ForwardResearchError
@dataclass
class CandleState:
 # Completed histories are intentionally partitioned by both symbol and
 # interval.  A shared interval-only list would leak another market's candles
 # into a model evaluation while still looking causally valid.
 completed:dict[tuple[str,str],list[dict]]=field(default_factory=dict);intrabar:dict[tuple[str,str],dict]=field(default_factory=dict)
 def history(self,symbol:str,interval:str)->list[dict]:
  """Return an immutable-view copy of one market's completed candle history."""
  return list(self.completed.get((symbol,interval),()))
 def apply(self,event:MarketEvent):
  row={'event_time':event.event_time,'open':event.open,'high':event.high,'low':event.low,'close':event.close,'volume':event.volume,'closed':event.closed}
  key=(event.symbol,event.interval)
  if event.closed:
   history=self.completed.setdefault(key,[])
   if history and history[-1]['event_time']>=event.event_time:raise ForwardResearchError('completed_candle_rewrite_or_order_violation')
   history.append(row);self.intrabar.pop(key,None);return 'COMPLETED'
  self.intrabar[key]=row;return 'INTRABAR'
