"""Public-feed event validation, sharding and fault isolation; no network client."""
from __future__ import annotations
from dataclasses import dataclass,field
from .core import ForwardResearchError,assert_shadow_only
@dataclass(frozen=True)
class MarketEvent:
 symbol:str;interval:str;event_time:str;receive_time:str;open:float;high:float;low:float;close:float;volume:float;closed:bool;sequence:int
 def identity(self):return f'{self.symbol}:{self.interval}:{self.event_time}:{self.sequence}'
def shard_symbols(symbols,max_per_shard=200):
 if max_per_shard<1:raise ForwardResearchError('shard_limit_invalid')
 return tuple(tuple(sorted(symbols)[i:i+max_per_shard]) for i in range(0,len(symbols),max_per_shard))
@dataclass
class CollectorState:
 seen:set[str]=field(default_factory=set);last_event:dict[str,str]=field(default_factory=dict);reconnects:int=0;errors:dict[str,str]=field(default_factory=dict)
 def accept(self,event:MarketEvent):
  assert_shadow_only()
  if event.interval not in {'1m','5m','15m','1h'} or event.high<max(event.open,event.close) or event.low>min(event.open,event.close) or event.volume<0:raise ForwardResearchError('market_event_invalid')
  key=event.identity()
  if key in self.seen:return False
  self.seen.add(key);self.last_event[event.symbol]=event.receive_time;return True
 def stale(self,symbol,now_age_seconds,limit_seconds=90):return symbol not in self.last_event or now_age_seconds>limit_seconds
