"""Fault-isolated completed-candle model observation execution."""
from __future__ import annotations
from .signal_adapter import frozen_signal_observations
def run_scheduled_models(symbol,rows,declarations):
 signals=[];errors=[]
 for row in declarations:
  try:signals.extend(frozen_signal_observations(symbol=symbol,model_name=row['model_name'],params=row['params'],rows=rows))
  except Exception as exc:errors.append({'symbol':symbol,'model_id':row.get('model_id'),'error_type':type(exc).__name__,'error_message':str(exc)})
 return {'signals':signals,'errors':errors,'model_calls':len(declarations),'forward_research_only':True}
