"""Fault-isolated completed-candle model observation execution."""
from __future__ import annotations
from .signal_adapter import frozen_signal_observations
def run_scheduled_models(symbol,rows,declarations):
 signals=[];errors=[]
 for row in declarations:
  try:
   emitted=frozen_signal_observations(symbol=symbol,model_name=row['model_name'],params=row['params'],rows=rows)
   # Preserve the declaration's frozen chain on every downstream signal.  The
   # adapter supplies the observed signal; it is not allowed to invent model
   # provenance.
   for signal in emitted:
    if signal.get('model_id')!=row['model_id']:raise ValueError('forward_model_id_provenance_mismatch')
    signal.update({key:row[key] for key in ('research_freeze_identity','research_plan_identity','parameter_grid_hash','strategy_function_hash','implementation_module_hash','declaration_identity')})
   signals.extend(emitted)
  except Exception as exc:errors.append({'symbol':symbol,'model_id':row.get('model_id'),'declaration_identity':row.get('declaration_identity'),'error_type':type(exc).__name__,'error_message':str(exc)})
 return {'signals':signals,'errors':errors,'model_calls':len(declarations),'forward_research_only':True}
