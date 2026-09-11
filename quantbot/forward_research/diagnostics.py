"""Evidence-only forward diagnostics; no ranking or model-selection output."""
from __future__ import annotations
from collections import Counter
from .core import identity
def classify_event(returns,wick_ratio=0.0):
 value=float(returns)
 if wick_ratio>=.1:return 'extreme_wick'
 if value>=.2:return 'strong_trend_up'
 if value>=.05:return 'trend_up'
 if value<=-.2:return 'strong_trend_down'
 if value<=-.05:return 'trend_down'
 return 'low_vol_chop'
def evidence_summary(rows):
 directions=Counter(row.get('direction','FLAT') for row in rows);events=Counter(row.get('event_class','unknown') for row in rows)
 payload={'schema_version':'quantbot-forward-diagnostics-v1','observations':len(rows),'long_signals':directions['LONG'],'short_signals':directions['SHORT'],'event_classes':dict(sorted(events.items())),'ranking_updated':False,'oos_read':False};payload['diagnostic_identity']=identity(payload);return payload
