"""Shadow runtime state; public feed adapters must be injected only by service wiring."""
from __future__ import annotations
from dataclasses import dataclass,field
from .core import assert_shadow_only,utc_now
@dataclass
class ForwardRuntime:
 last_event_at:str|None=None;events:int=0;duplicates:int=0;reconnects:int=0;errors:int=0;open_observations:int=0;completed_observations:int=0;seen:set[str]=field(default_factory=set)
 def ingest(self,event_id,event_time,receive_time):
  assert_shadow_only()
  if event_id in self.seen:self.duplicates+=1;return False
  self.seen.add(event_id);self.events+=1;self.last_event_at=receive_time;return True
 def health(self):return {'runtime':'SHADOW_ONLY','events_received':self.events,'duplicates':self.duplicates,'reconnects':self.reconnects,'errors':self.errors,'last_event_at':self.last_event_at,'oos_allowed':False,'order_placement_allowed':False}
