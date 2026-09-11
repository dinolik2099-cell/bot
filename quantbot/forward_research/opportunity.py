"""Evidence-only opportunity-to-signal matching; never a strategy selector."""
from __future__ import annotations
from .core import identity
def match_opportunity(event,signals,selected_signal_ids=()):
 direction='LONG' if event['direction']=='UP' else 'SHORT';start=event['event_start'];eligible=[row for row in signals if row.get('symbol')==event['symbol']]
 matching=[row for row in eligible if row.get('direction')==direction]
 if not matching:status='MISSED' if not eligible else 'WRONG_DIRECTION';chosen=None
 else:
  chosen=sorted(matching,key=lambda row:row.get('signal_timestamp',''))[0]
  status='CAPTURED' if chosen.get('signal_identity') in set(selected_signal_ids) else 'PORTFOLIO_REJECTED'
  if chosen.get('signal_timestamp','')>start:status='LATE'
 return {'schema_version':'quantbot-forward-opportunity-match-v1','event_identity':event['event_identity'],'symbol':event['symbol'],'event_direction':event['direction'],'expected_signal_direction':direction,'status':status,'signal_identity':chosen.get('signal_identity') if chosen else None,'candidate_signal_count':len(eligible),'matching_signal_count':len(matching),'ranking_updated':False,'match_identity':identity({'event':event['event_identity'],'signals':sorted(row.get('signal_identity','') for row in eligible),'selected':sorted(selected_signal_ids)})}
