"""Fault-isolated completed-candle model observation execution."""
from __future__ import annotations
from .signal_adapter import completed_frame,frozen_signal_observations,incremental_frozen_signal_observations

def run_scheduled_models(symbol,rows,declarations,*,incremental=False):
 # One canonical completed frame is shared read-only across declarations.  Each
 # strategy still receives its own copy inside the adapter.
 try:frame=completed_frame(rows)
 except Exception as exc:
  return {'signals':[],'errors':[{'symbol':symbol,'model_id':row.get('model_id'),'declaration_identity':row.get('declaration_identity'),'error_type':type(exc).__name__,'error_message':str(exc)} for row in declarations],'model_calls':len(declarations),'forward_research_only':True}
 def observe(row):
  try:
   emitted=(incremental_frozen_signal_observations(symbol=symbol,model_name=row['model_name'],params=row['params'],frame=frame) if incremental else frozen_signal_observations(symbol=symbol,model_name=row['model_name'],params=row['params'],frame=frame))
   # Preserve the declaration's frozen chain on every downstream signal.  The
   # adapter supplies the observed signal; it is not allowed to invent model
   # provenance.
   for signal in emitted:
    if signal.get('model_id')!=row['model_id']:raise ValueError('forward_model_id_provenance_mismatch')
    signal.update({key:row[key] for key in ('research_freeze_identity','research_plan_identity','parameter_grid_hash','strategy_function_hash','implementation_module_hash','declaration_identity')})
   return emitted,None
  except Exception as exc:return [],{'symbol':symbol,'model_id':row.get('model_id'),'declaration_identity':row.get('declaration_identity'),'error_type':type(exc).__name__,'error_message':str(exc)}
 results=[observe(row) for row in declarations]
 signals=[];errors=[]
 for emitted,error in results:
  signals.extend(emitted)
  if error is not None:errors.append(error)
 return {'signals':signals,'errors':errors,'model_calls':len(declarations),'forward_research_only':True}
