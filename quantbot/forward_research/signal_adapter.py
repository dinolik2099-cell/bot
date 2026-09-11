"""Read-only bridge from completed forward candles to frozen model intents."""
from __future__ import annotations
import pandas as pd
from .core import ForwardResearchError,identity,assert_shadow_only

def completed_frame(rows):
 """Build a UTC completed-candle frame; intrabar rows are rejected outright."""
 if not rows or any(not row.get('closed') for row in rows):raise ForwardResearchError('forward_completed_candle_required')
 frame=pd.DataFrame(rows).copy();index=pd.to_datetime(frame.pop('event_time'),utc=True)
 frame.index=index
 if not frame.index.is_monotonic_increasing or frame.index.has_duplicates:raise ForwardResearchError('forward_candle_order_invalid')
 return frame[['open','high','low','close','volume']].astype(float)

def frozen_signal_observations(*,symbol,model_name,params,rows):
 """Call the registered strategy on completed data only; emits no order intent."""
 assert_shadow_only();frame=completed_frame(rows)
 from quantbot.signals.model_adapter import generate_model_intents
 intents=generate_model_intents(symbol,model_name,frame,params,execution_lag=1,metadata={'forward_research_only':True})
 output=[]
 for item in intents:
  direction='LONG' if item.side=='buy' else 'SHORT'
  row={'schema_version':'quantbot-forward-signal-v1','symbol':symbol,'model_name':model_name,'model_id':None,'params':dict(params),'params_identity':identity(dict(params)),'direction':direction,'signal_timestamp':item.timestamp.isoformat(),'reference_price':float(frame.loc[item.timestamp,'open']),'completed_candle_timestamp':item.metadata['source_row_timestamp'],'input_boundary':'COMPLETED_CANDLE_T_MINUS_1','forward_research_only':True,'oos_allowed':False}
  from quantbot.research.model_registry import get_model
  row['model_id']=get_model(model_name).spec.model_id;row['signal_identity']=identity(row);output.append(row)
 return output
