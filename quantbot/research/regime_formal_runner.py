"""Canonical non-OOS regime labeling runner construction."""
from __future__ import annotations
from typing import Mapping
from .future_data_plane import FutureRuntimeContext, make_future_canonical_window_loader
from .regime_framework import RegimePolicy, classify_point_in_time
from .future_stage_execution import _execute_verified_chunks


class RegimeRunnerError(RuntimeError): pass


def make_regime_canonical_runner(*, runtime: FutureRuntimeContext, evidence, n8_context, raw_root):
 """Return a TRAIN/VALIDATION-only loader-and-label function after authority."""
 if runtime.protocol.get('stage')!='regime': raise RegimeRunnerError('regime_stage_required')
 config=runtime.protocol.get('config',{})
 try: policy=RegimePolicy(**dict(config.get('policy',{})))
 except (TypeError,ValueError) as exc: raise RegimeRunnerError('regime_policy_invalid') from exc
 loader=make_future_canonical_window_loader(runtime=runtime,evidence=evidence,n8_context=n8_context,raw_root=raw_root)
 def run(*,window:str,symbol:str,task:Mapping[str,object],boundary:Mapping[str,object]):
  if window not in {'TRAIN','VALIDATION'}: raise RegimeRunnerError('regime_window_not_authorized')
  return classify_point_in_time(loader(window=window,symbol=symbol,task=task,boundary=boundary),policy)
 return run


def run_authorized_regime(*, runtime: FutureRuntimeContext, evidence, n8_context, raw_root,
                          source_git_commit: str, checkpoint=None, prior_rows=()):
 """Produce sealed PIT regime diagnostics for every deterministically assigned task.

 The public path accepts neither a classifier nor a frame loader.  It binds to
 the accepted N8 raw reader and the one accepted point-in-time classifier.
 """
 runner=make_regime_canonical_runner(runtime=runtime,evidence=evidence,n8_context=n8_context,raw_root=raw_root)
 tasks=tuple(sorted(n8_context.n7.plan.get('tasks',()),key=lambda row:row['task_identity']))
 chunks=len(runtime.plan['chunks'])
 if not tasks: raise RegimeRunnerError('regime_tasks_missing')
 def execute(chunk):
  ordinal=chunk.get('ordinal')
  if not isinstance(ordinal,int) or not 0 <= ordinal < chunks: raise RegimeRunnerError('regime_chunk_invalid')
  diagnostics=[]
  for index,task in enumerate(tasks):
   if index % chunks != ordinal: continue
   windows=[]
   for window in ('TRAIN','VALIDATION'):
    labels=runner(window=window,symbol=task['symbol'],task=task,boundary=n8_context.dataset.boundary)
    windows.append({'window':window,'rows':len(labels),'first_timestamp':labels.index[0].isoformat(),
                    'last_timestamp':labels.index[-1].isoformat(),
                    'composite_counts':{str(key):int(value) for key,value in labels['composite'].value_counts().sort_index().items()}})
   diagnostics.append({'task_identity':task['task_identity'],'model_id':task['model_id'],'symbol':task['symbol'],'windows':windows})
  return {'diagnostics':diagnostics,'task_count':len(diagnostics),'classifier':'quantbot.research.regime_framework.classify_point_in_time','oos_read':False}
 return _execute_verified_chunks(runtime=runtime,source_git_commit=source_git_commit,executor=execute,checkpoint=checkpoint,prior_rows=prior_rows)
