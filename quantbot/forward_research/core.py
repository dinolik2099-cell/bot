"""Pure forward-shadow contracts.  No formal dataset, order, or OOS access."""
from __future__ import annotations
import hashlib,json,os
from dataclasses import dataclass,asdict
from datetime import datetime,timezone
from pathlib import Path
from typing import Mapping,Sequence
from . import FORWARD_RESEARCH_ONLY,ORDER_PLACEMENT_ALLOWED,OOS_ALLOWED
class ForwardResearchError(RuntimeError):pass
def canon(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False)
def identity(value):return hashlib.sha256(canon(value).encode()).hexdigest()
def utc_now():return datetime.now(timezone.utc).isoformat()
def assert_shadow_only():
 if not FORWARD_RESEARCH_ONLY or ORDER_PLACEMENT_ALLOWED or OOS_ALLOWED:raise ForwardResearchError('forward_shadow_safety_violation')
@dataclass(frozen=True)
class UniverseSymbol:
 symbol:str;quote_volume:float;contract_type:str;quote_asset:str;status:str;tick_size:str='';step_size:str='';min_qty:str='';min_notional:str=''
 def eligible(self):return self.contract_type=='PERPETUAL' and self.quote_asset=='USDT' and self.status=='TRADING' and self.quote_volume>=3_000_000
def universe_snapshot(rows:Sequence[UniverseSymbol],timestamp:str):
 assert_shadow_only();eligible=sorted((asdict(row) for row in rows if row.eligible()),key=lambda row:row['symbol']);payload={'schema_version':'quantbot-forward-universe-v1','timestamp':timestamp,'symbols':eligible,'threshold_quote_volume':3_000_000,'source':'binance_public','forward_research_only':True};payload['universe_identity']=identity(payload);return payload
def directional_path(direction,entry,prices):
 if direction not in {'LONG','SHORT'} or entry<=0 or not prices:raise ForwardResearchError('path_input_invalid')
 returns=[(p/entry-1) if direction=='LONG' else (entry/p-1) for p in prices];mfe=max(returns);mae=min(returns);peak=returns.index(mfe);worst=returns.index(mae);return {'direction':direction,'entry_reference':entry,'close_return':returns[-1],'mfe':mfe,'mae':mae,'peak_index':peak,'worst_index':worst,'giveback':mfe-returns[-1],'time_to_mfe':peak,'time_to_mae':worst}
def trailing_exit(direction,entry,prices,drawdown):
 path=directional_path(direction,entry,prices);best=-float('inf')
 for i,p in enumerate(prices):
  value=(p/entry-1) if direction=='LONG' else (entry/p-1);best=max(best,value)
  if best-value>=drawdown:return {'exit_index':i,'exit_price':p,'reason':'TRAILING','gross_return':value,'max_profit':best}
 return {'exit_index':len(prices)-1,'exit_price':prices[-1],'reason':'HORIZON','gross_return':path['close_return'],'max_profit':path['mfe']}
def classify_opportunity(symbol,start,end,move,volume_expansion=1.0):
 if abs(move)<.05: return None
 return {'symbol':symbol,'event_start':start,'event_end':end,'direction':'UP' if move>0 else 'DOWN','move_magnitude':abs(move),'volume_expansion':volume_expansion,'event_identity':identity({'symbol':symbol,'start':start,'end':end,'move':move})}
class AppendOnlyStore:
 def __init__(self,root):self.root=Path(root)
 def append(self,partition,record):
  assert_shadow_only();path=self.root/partition;path.parent.mkdir(parents=True,exist_ok=True);line=canon(record)+'\n'
  if path.exists() and line.encode() in path.read_bytes().splitlines(keepends=True):return path
  with path.open('a',encoding='utf-8',newline='\n') as handle:handle.write(line);handle.flush();os.fsync(handle.fileno())
  return path
 def manifest(self,date,git_commit,config_identity):
  files=[]
  for path in sorted(self.root.rglob('*')):
   if path.is_file() and 'manifests' not in path.parts:files.append({'path':str(path.relative_to(self.root)).replace('\\','/'),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'bytes':path.stat().st_size})
  data={'schema_version':'quantbot-forward-research-day-v1','date':date,'git_commit':git_commit,'config_identity':config_identity,'files':files,'forward_research_only':True};data['artifact_identity']=identity(data);return data
 def verify_manifest(self,manifest):
  rebuilt=self.manifest(manifest['date'],manifest['git_commit'],manifest['config_identity'])
  if rebuilt['artifact_identity']!=manifest.get('artifact_identity'):raise ForwardResearchError('forward_daily_manifest_drift')
  return True
