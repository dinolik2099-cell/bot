"""Completed-candle-only scheduling of already frozen model declarations."""
from __future__ import annotations
from .core import identity
def schedule_models(symbol,completed_candle_timestamp,models):
 rows=[]
 for row in sorted(models,key=lambda item:(item['model_id'],item['params_identity'])):
  if row.get('input_boundary')!='COMPLETED_CANDLE_T_MINUS_1':raise ValueError('forward_model_input_boundary_invalid')
  payload={'symbol':symbol,'model_id':row['model_id'],'params_identity':row['params_identity'],'completed_candle_timestamp':completed_candle_timestamp,'input_boundary':'COMPLETED_CANDLE_T_MINUS_1','forward_research_only':True};payload['schedule_identity']=identity(payload);rows.append(payload)
 return rows
