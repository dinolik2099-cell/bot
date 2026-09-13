"""Read-only bridge from completed forward candles to frozen model intents."""
from __future__ import annotations
import math
import pandas as pd
from .core import ForwardResearchError,identity,assert_shadow_only

def completed_frame(rows):
 """Build a UTC completed-candle frame; intrabar rows are rejected outright."""
 if not rows or any(not row.get('closed') for row in rows):raise ForwardResearchError('forward_completed_candle_required')
 frame=pd.DataFrame(rows).copy();index=pd.to_datetime(frame.pop('event_time'),utc=True)
 frame.index=index
 if not frame.index.is_monotonic_increasing or frame.index.has_duplicates:raise ForwardResearchError('forward_candle_order_invalid')
 return frame[['open','high','low','close','volume']].astype(float)

def _observation_row(*, symbol, model_name, params, frame, item):
 """Translate one canonical intent without adding an execution capability."""
 direction='LONG' if item.side=='buy' else 'SHORT'
 row={'schema_version':'quantbot-forward-signal-v1','symbol':symbol,'model_name':model_name,'model_id':None,'params':dict(params),'params_identity':identity(dict(params)),'direction':direction,'signal_timestamp':item.timestamp.isoformat(),'reference_price':float(frame.loc[item.timestamp,'open']),'completed_candle_timestamp':item.metadata['source_row_timestamp'],'input_boundary':'COMPLETED_CANDLE_T_MINUS_1','forward_research_only':True,'oos_allowed':False}
 from quantbot.research.model_registry import get_model
 row['model_id']=get_model(model_name).spec.model_id;row['signal_identity']=identity(row);return row

def frozen_signal_observations(*,symbol,model_name,params,rows=None,frame=None):
 """Call the registered strategy on completed data only; emits no order intent."""
 assert_shadow_only()
 if frame is None:frame=completed_frame(rows)
 elif rows is not None:raise ForwardResearchError('forward_signal_frame_input_ambiguous')
 from quantbot.signals.model_adapter import generate_model_intents
 intents=generate_model_intents(symbol,model_name,frame,params,execution_lag=1,metadata={'forward_research_only':True})
 return [_observation_row(symbol=symbol,model_name=model_name,params=params,frame=frame,item=item) for item in intents]

def incremental_frozen_signal_observations(*, symbol, model_name, params, frame):
 """Return only the T-1 strategy row newly observable at this Forward close.

 The strategy receives the full, immutable completed history just as it does in
 canonical research.  The Forward seam deliberately examines only the one row
 made executable by this close, avoiding historical signal re-emission while
 retaining per-model ``frame.copy()`` isolation.
 """
 assert_shadow_only()
 if len(frame)<2:return []
 from quantbot.research.model_registry import get_model
 registered=get_model(model_name)
 if registered.spec.status in {'retired','deferred'}:raise PermissionError(f'model is not eligible to emit signals: {model_name}')
 if registered.spec.oos_status!='sealed':raise PermissionError(f'model has invalid OOS lifecycle state: {model_name}')
 strategy_output=registered.strategy(frame.copy(),**dict(params))
 if not strategy_output.index.equals(frame.index):raise ValueError('strategy output index must exactly match the input frame')
 required={'signal','stop','target'};missing=required-set(strategy_output.columns)
 if missing:raise ValueError(f'strategy output missing columns: {sorted(missing)}')
 position=len(strategy_output)-2;row=strategy_output.iloc[position];raw_side=int(row['signal'])
 if raw_side==0:return []
 if raw_side not in {-1,1}:raise ValueError(f'invalid strategy signal: {raw_side}')
 stop=float(row['stop']);reference=float(frame.iloc[position]['close'])
 if not math.isfinite(stop) or not math.isfinite(reference):return []
 side='buy' if raw_side==1 else 'sell'
 if (side=='buy' and stop>=reference) or (side=='sell' and stop<=reference):return []
 target_value=row['target'];target=None if pd.isna(target_value) else float(target_value)
 if target is not None and (not math.isfinite(target) or (side=='buy' and target<=reference) or (side=='sell' and target>=reference)):return []
 from quantbot.signals.contracts import SignalIntent
 distance=abs(reference-stop);item=SignalIntent(symbol=symbol,timestamp=pd.Timestamp(frame.index[position+1]).tz_convert('UTC'),side=side,model=model_name,model_family=registered.spec.family,confidence=min(1.0,distance/max(abs(reference),1e-12)),score=float(raw_side)*min(1.0,distance/max(abs(reference),1e-12)),stop=stop,take_profit=target,risk_intent='requires_risk_approval',metadata={'forward_research_only':True,'source_row_timestamp':pd.Timestamp(frame.index[position]).tz_convert('UTC').isoformat()})
 return [_observation_row(symbol=symbol,model_name=model_name,params=params,frame=frame,item=item)]
