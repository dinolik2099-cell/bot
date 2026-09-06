from pathlib import Path
import json,sys,tempfile
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from quantbot.research.formal_runner import load_n7_context
from quantbot.research.canonical_data_adapter import N8DataError,load_n8_data_context,_make_n8_window_loader_for_test,make_n8_canonical_window_loader
from quantbot.research.authorization_gate import FreezeAuthorizationError

PLAN=ROOT/'docs/handoff/FROZEN_RESEARCH_PLAN_N5.json';FREEZE=ROOT/'docs/handoff/CANDIDATE_UNIVERSE_FREEZE_N3.json';LOCK=json.loads((ROOT/'data/reports/research_boundary_lock.json').read_text())
def clone(v):return json.loads(json.dumps(v))
def frame_at(start):
 index=pd.date_range(start,periods=3,freq='h',tz='UTC')
 return pd.DataFrame({'open':[1.,1.,1.],'high':[1.,1.,1.],'low':[1.,1.,1.],'close':[1.,1.,1.],'volume':[1.,1.,1.]},index=index)
def complete_frame(n8,symbol,window):
 item=next(x for x in n8.dataset.windows if x.name==window);index=pd.date_range(item.start,item.end,freq='1h',tz='UTC')
 from quantbot.research.integration import timestamp_in_non_tradable_gap
 index=index[[not timestamp_in_non_tradable_gap(n8.dataset,symbol,ts) for ts in index]]
 return pd.DataFrame({'open':1.,'high':1.,'low':1.,'close':1.,'volume':1.},index=index)
def main():
 n7=load_n7_context(PLAN,FREEZE,LOCK);n8=load_n8_data_context(n7,ROOT/'data/reports/research_boundary_lock.json');task=n7.plan['tasks'][0];calls=[]
 def source(**kwargs):calls.append(kwargs);return complete_frame(n8,kwargs['symbol'],kwargs['window']),'canonical_raw'
 loader=_make_n8_window_loader_for_test(n8,source)
 def reject(action):
  try:action()
  except (N8DataError,FreezeAuthorizationError,ValueError,TypeError):return
  raise AssertionError('unexpectedly accepted')
 # All authorization failures happen before source access.
 for window in ('OOS','oos','TRAIN ','UNKNOWN'):
  before=len(calls);reject(lambda w=window:loader(window=w,symbol=task['symbol'],task=task,boundary=n7.plan['boundary']));assert len(calls)==before
 before=len(calls);reject(lambda:loader(window='TRAIN',symbol='UNKNOWN',task=task,boundary=n7.plan['boundary']));assert len(calls)==before
 bad_task=clone(task);bad_task['symbol']='UNKNOWN';reject(lambda:loader(window='TRAIN',symbol=task['symbol'],task=bad_task,boundary=n7.plan['boundary']));assert len(calls)==before
 forged=clone(task);forged['task_identity']='x'*64;reject(lambda:loader(window='TRAIN',symbol=task['symbol'],task=forged,boundary=n7.plan['boundary']));assert len(calls)==before
 wrong_model=clone(task);wrong_model['model_id']='quantbot.unknown.v1';reject(lambda:loader(window='TRAIN',symbol=task['symbol'],task=wrong_model,boundary=n7.plan['boundary']));assert len(calls)==before
 with tempfile.TemporaryDirectory() as td:
  root=Path(td);bad_plan=clone(n7.plan);bad_plan['research_plan_identity']='x'*64;(root/'plan.json').write_text(json.dumps(bad_plan));reject(lambda:load_n7_context(root/'plan.json',FREEZE,LOCK))
  bad_freeze=clone(n7.freeze);bad_freeze['research_freeze_identity']='x'*64;(root/'freeze.json').write_text(json.dumps(bad_freeze));reject(lambda:load_n7_context(PLAN,root/'freeze.json',LOCK))
  for key,value in (('dataset_id','WRONG'),('interval','4h')):
   lock=clone(LOCK);lock[key]=value;(root/'lock.json').write_text(json.dumps(lock));reject(lambda p=root/'lock.json':load_n8_data_context(n7,p))
  lock=clone(LOCK);lock['splits'][0]['end']='2024-12-30T23:00:00+00:00';(root/'lock.json').write_text(json.dumps(lock));reject(lambda p=root/'lock.json':load_n8_data_context(n7,p))
 # Normal TRAIN/VALIDATION source requests are narrow and accepted.
 assert len(loader(window='TRAIN',symbol=task['symbol'],task=task,boundary=n7.plan['boundary']))>3
 assert len(loader(window='VALIDATION',symbol=task['symbol'],task=task,boundary=n7.plan['boundary']))>3
 gap_task=next(x for x in n7.plan['tasks'] if x['symbol']=='SOLUSDT')
 assert len(loader(window='TRAIN',symbol='SOLUSDT',task=gap_task,boundary=n7.plan['boundary']))>3
 assert [x['window'] for x in calls]==['TRAIN','VALIDATION','TRAIN']
 def invalid_source(frame,source_name='canonical_raw'):
  return _make_n8_window_loader_for_test(n8,lambda **kwargs:(frame,source_name))
 outside=frame_at('2025-01-01');reject(lambda:invalid_source(outside)(window='TRAIN',symbol=task['symbol'],task=task,boundary=n7.plan['boundary']))
 validation_in_train=frame_at('2024-12-31');reject(lambda:invalid_source(validation_in_train)(window='VALIDATION',symbol=task['symbol'],task=task,boundary=n7.plan['boundary']))
 duplicate=frame_at('2021-01-01');duplicate.index=pd.DatetimeIndex([duplicate.index[0],duplicate.index[0],duplicate.index[2]]);reject(lambda:invalid_source(duplicate)(window='TRAIN',symbol=task['symbol'],task=task,boundary=n7.plan['boundary']))
 nonmonotonic=frame_at('2021-01-01').iloc[[1,0,2]];reject(lambda:invalid_source(nonmonotonic)(window='TRAIN',symbol=task['symbol'],task=task,boundary=n7.plan['boundary']))
 missing=frame_at('2021-01-01').drop(columns=['volume']);reject(lambda:invalid_source(missing)(window='TRAIN',symbol=task['symbol'],task=task,boundary=n7.plan['boundary']))
 synthetic=frame_at('2021-01-01');synthetic.attrs['synthetic_candles']=True;reject(lambda:invalid_source(synthetic)(window='TRAIN',symbol=task['symbol'],task=task,boundary=n7.plan['boundary']))
 reject(lambda:invalid_source(frame_at('2021-01-01'),'parquet_fallback')(window='TRAIN',symbol=task['symbol'],task=task,boundary=n7.plan['boundary']))
 non_utc=complete_frame(n8,task['symbol'],'TRAIN');non_utc.index=non_utc.index.tz_convert('Asia/Shanghai');reject(lambda:invalid_source(non_utc)(window='TRAIN',symbol=task['symbol'],task=task,boundary=n7.plan['boundary']))
 prefix=complete_frame(n8,task['symbol'],'TRAIN').iloc[1:];reject(lambda:invalid_source(prefix)(window='TRAIN',symbol=task['symbol'],task=task,boundary=n7.plan['boundary']))
 suffix=complete_frame(n8,task['symbol'],'TRAIN').iloc[:-1];reject(lambda:invalid_source(suffix)(window='TRAIN',symbol=task['symbol'],task=task,boundary=n7.plan['boundary']))
 internal=complete_frame(n8,task['symbol'],'TRAIN').drop(complete_frame(n8,task['symbol'],'TRAIN').index[100]);reject(lambda:invalid_source(internal)(window='TRAIN',symbol=task['symbol'],task=task,boundary=n7.plan['boundary']))
 fake_calls=[];fake=lambda **kwargs:fake_calls.append(kwargs) or (complete_frame(n8,task['symbol'],'TRAIN'),'canonical_raw')
 reject(lambda:make_n8_canonical_window_loader(n8,fake)(window='TRAIN',symbol=task['symbol'],task=task,boundary=n7.plan['boundary']));assert not fake_calls
 assert all(item['window']!='OOS' for item in calls) and len(calls)==3
 print('N8_DATA_ADAPTER_SYNTHETIC_TEST_OK')
if __name__=='__main__':main()
