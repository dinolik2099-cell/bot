"""Strict Demo-only configuration and policy validation."""
from __future__ import annotations
import os
from pathlib import Path
from typing import Mapping
from . import DEMO_ENVIRONMENT,LIVE_ORDER_ENDPOINT_ALLOWED
from .core import DemoExecutionError,identity

DEMO_FUTURES_ENDPOINTS={"https://demo-fapi.binance.com"}
LIVE_MARKERS=("fapi.binance.com","binance.com")

def load_json(path):
 value=__import__('json').loads(Path(path).read_text(encoding='utf-8'))
 if not isinstance(value,Mapping):raise DemoExecutionError('demo_config_mapping_required')
 return dict(value)

def validate_config(raw:Mapping):
 row=dict(raw);endpoint=str(row.get('endpoint','')).rstrip('/')
 if row.get('environment')!=DEMO_ENVIRONMENT:raise DemoExecutionError('demo_environment_required')
 if row.get('live_order_endpoint_allowed') is not False or LIVE_ORDER_ENDPOINT_ALLOWED:raise DemoExecutionError('demo_live_order_permission_forbidden')
 if endpoint not in DEMO_FUTURES_ENDPOINTS or any(marker in endpoint and endpoint not in DEMO_FUTURES_ENDPOINTS for marker in LIVE_MARKERS):raise DemoExecutionError('demo_endpoint_fence_rejected')
 policy=row.get('execution_policy')
 # A policy is deliberately opt-in.  Missing/disabled policy supports only
 # diagnostics/dry-run and cannot create an order intent.
 if policy is not None:
  if not isinstance(policy,Mapping) or policy.get('enabled') is not True:raise DemoExecutionError('demo_execution_policy_invalid')
  required=('position_mode','margin_mode','leverage','order_notional','max_signal_age_seconds','risk')
  if any(key not in policy for key in required):raise DemoExecutionError('demo_execution_policy_incomplete')
  if policy['position_mode'] not in {'ONE_WAY','HEDGE'} or policy['margin_mode'] not in {'ISOLATED','CROSSED'}:raise DemoExecutionError('demo_execution_policy_mode_invalid')
  if type(policy['leverage']) is not int or policy['leverage']<1 or type(policy['order_notional']) not in {int,float} or policy['order_notional']<=0:raise DemoExecutionError('demo_execution_policy_size_invalid')
 row['endpoint']=endpoint;row['config_identity']=identity({key:value for key,value in row.items() if key!='config_identity'})
 return row

def load_credentials(environ=None):
 source=os.environ if environ is None else environ;key=source.get('BINANCE_DEMO_API_KEY');secret=source.get('BINANCE_DEMO_API_SECRET')
 return {'api_key':key,'api_secret':secret,'loaded':bool(key and secret)}
