"""Crash-safe forward runtime checkpoint; never stores or changes formal state."""
from __future__ import annotations
import os,tempfile,json
from pathlib import Path
from .core import identity,assert_shadow_only
def checkpoint_payload(runtime,config_identity,git_commit):
 assert_shadow_only();data={'schema_version':'quantbot-forward-checkpoint-v1','config_identity':config_identity,'git_commit':git_commit,'runtime':runtime.health(),'forward_research_only':True,'oos_allowed':False};data['checkpoint_identity']=identity(data);return data
def write_checkpoint(path,payload):
 target=Path(path);target.parent.mkdir(parents=True,exist_ok=True);fd,tmp=tempfile.mkstemp(prefix=target.name+'.',dir=target.parent);os.close(fd)
 try:Path(tmp).write_text(json.dumps(payload,sort_keys=True),encoding='utf-8');os.replace(tmp,target)
 finally:
  if Path(tmp).exists():Path(tmp).unlink()
def load_checkpoint(path,*,config_identity=None,git_commit=None):
 value=json.loads(Path(path).read_text(encoding='utf-8'));expected=dict(value);seen=expected.pop('checkpoint_identity',None)
 if seen!=identity(expected):raise ValueError('forward_checkpoint_identity_mismatch')
 if config_identity is not None and value.get('config_identity')!=config_identity:raise ValueError('forward_checkpoint_config_drift')
 if git_commit is not None and value.get('git_commit')!=git_commit:raise ValueError('forward_checkpoint_git_drift')
 return value
