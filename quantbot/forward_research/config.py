"""Minimal strict config validation for isolated Forward Shadow Research."""
from __future__ import annotations
from pathlib import Path
from .core import ForwardResearchError,identity
def parse_simple_yaml(path):
 rows={}
 for raw in Path(path).read_text(encoding='utf-8').splitlines():
  if ':' in raw and not raw.lstrip().startswith('#'):
   key,value=raw.split(':',1);rows[key.strip()]=value.strip().lower()
 return rows
def validate_config(path):
 row=parse_simple_yaml(path)
 if row.get('forward_research_only')!='true' or row.get('order_placement_allowed')!='false' or row.get('oos_allowed')!='false':raise ForwardResearchError('forward_config_safety_drift')
 row['config_identity']=identity(row);return row
