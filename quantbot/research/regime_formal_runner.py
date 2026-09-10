"""Canonical non-OOS regime labeling runner construction."""
from __future__ import annotations
from typing import Mapping
from .future_data_plane import FutureRuntimeContext, make_future_canonical_window_loader
from .regime_framework import RegimePolicy, classify_point_in_time


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
