"""Direction-symmetric shadow observations and non-mutating evidence labels."""
from __future__ import annotations
from .core import directional_path,trailing_exit,classify_opportunity,identity
HORIZONS=(5,15,30,60,120,240,480,720,1440)
def observation(signal,prices,horizons=HORIZONS):
 if signal.get('direction') not in {'LONG','SHORT'}:raise ValueError('shadow_direction_invalid')
 entry=float(signal['reference_price']);out={'signal':dict(signal),'horizons':[]}
 for horizon in horizons:
  path=list(prices[:horizon])
  if not path:continue
  out['horizons'].append({'minutes':horizon,**directional_path(signal['direction'],entry,path), 'exits':[trailing_exit(signal['direction'],entry,path,x) for x in (.05,.08,.12,.15)]})
 out['observation_identity']=identity(out);return out
def cross_section(timestamp,states):
 directions=[row.get('direction','FLAT') for row in states];return {'timestamp':timestamp,'symbols':len(states),'long_count':directions.count('LONG'),'short_count':directions.count('SHORT'),'flat_count':directions.count('FLAT'),'models_firing':len({row.get('model_id') for row in states if row.get('direction')!='FLAT'}),'rows':sorted(states,key=lambda row:(row.get('symbol',''),row.get('model_id','')))}
def shadow_selection(signals,max_positions=4):
 ordered=sorted(signals,key=lambda row:(row.get('task_identity',''),row.get('symbol','')));selected=[];rejected=[];symbols=set()
 for row in ordered:
  if row.get('direction') not in {'LONG','SHORT'}:continue
  if row['symbol'] in symbols:rejected.append({**row,'reason':'SYMBOL_ALREADY_SELECTED'})
  elif len(selected)>=max_positions:rejected.append({**row,'reason':'MAX_POSITIONS'})
  else:selected.append({**row,'allocation_fraction':1/max_positions});symbols.add(row['symbol'])
 return {'eligible':len(ordered),'selected':selected,'rejected':rejected,'engine':'quantbot.portfolio.shared_capital.shadow_selection_only'}
