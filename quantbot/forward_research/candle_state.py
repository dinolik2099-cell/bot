"""Separate immutable completed candle history from mutable intrabar observation state."""
from __future__ import annotations
from dataclasses import dataclass,field
from .collector import MarketEvent
from .core import ForwardResearchError
@dataclass
class CandleState:
 completed:dict[str,list[dict]]=field(default_factory=dict);intrabar:dict[tuple[str,str],dict]=field(default_factory=dict)
 def apply(self,event:MarketEvent):
  row={'event_time':event.event_time,'open':event.open,'high':event.high,'low':event.low,'close':event.close,'volume':event.volume,'closed':event.closed}
  key=(event.symbol,event.interval)
  if event.closed:
   history=self.completed.setdefault(event.interval,[])
   if history and history[-1]['event_time']>=event.event_time:raise ForwardResearchError('completed_candle_rewrite_or_order_violation')
   history.append(row);self.intrabar.pop(key,None);return 'COMPLETED'
  self.intrabar[key]=row;return 'INTRABAR'
