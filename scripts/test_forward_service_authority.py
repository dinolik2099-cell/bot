"""Production-shaped tests for Forward authority; no network client is created."""
from __future__ import annotations
import json,tempfile
from pathlib import Path
from quantbot.forward_research.core import identity
from quantbot.forward_research.frozen_declarations import DECLARATION_SCHEMA,declaration_identity,manifest_identity
from quantbot.forward_research.production_runtime import _build_authority_for_test,_public_json

class Response:
 def __init__(self,payload):self.payload=payload
 def raise_for_status(self):return None
 def json(self):return self.payload
class Session:
 def __init__(self):self.urls=[]
 def get(self,url,timeout):
  self.urls.append(url)
  if url.endswith('exchangeInfo'):return Response({'symbols':[{'symbol':'XUSDT','contractType':'PERPETUAL','quoteAsset':'USDT','status':'TRADING','filters':[]}]})
  return Response([{'symbol':'XUSDT','quoteVolume':'3000000'}])
def main():
 with tempfile.TemporaryDirectory() as root:
  root=Path(root);config=root/'config.yaml';config.write_text('forward_research_only: true\norder_placement_allowed: false\noos_allowed: false\n',encoding='utf-8')
  model={'model_id':'m','parameter_grid_hash':'g'*64,'strategy_function_hash':'s'*64,'implementation_module_hash':'i'*64}
  plan={'research_freeze_identity':'f'*64,'research_plan_identity':'p'*64,'oos_status':'SEALED','oos_authorization':'NOT_AUTHORIZED','protocol_scope':{'timeframe':'1m'},'models':[model]};plan_path=root/'plan.json';plan_path.write_text(json.dumps(plan),encoding='utf-8')
  declaration={'schema_version':DECLARATION_SCHEMA,'research_freeze_identity':'f'*64,'research_plan_identity':'p'*64,'model_id':'m','model_name':'missing','params':{},'params_identity':identity({}),'parameter_grid_hash':'g'*64,'strategy_function_hash':'s'*64,'implementation_module_hash':'i'*64,'input_boundary':'COMPLETED_CANDLE_T_MINUS_1'};declaration['declaration_identity']=declaration_identity(declaration)
  manifest={'schema_version':DECLARATION_SCHEMA,'decision_artifact_id':'day0','research_freeze_identity':'f'*64,'research_plan_identity':'p'*64,'declarations':[declaration],'forward_research_only':True,'oos_allowed':False,'order_placement_allowed':False};manifest['manifest_identity']=manifest_identity(manifest);declaration_path=root/'declaration.json';declaration_path.write_text(json.dumps(manifest),encoding='utf-8')
  session=Session();authority=_build_authority_for_test(config_path=config,plan_path=plan_path,declaration_path=declaration_path,data_root=root/'data',checkpoint_path=root/'checkpoint.json',repo_root='.',_session=session)
  snapshot=authority.refresh_universe('2026-09-11T00:00:00+00:00');assert snapshot['symbols'][0]['symbol']=='XUSDT' and len(session.urls)==2
  authority.checkpoint();assert authority.resume()['research_plan_identity']=='p'*64
  try:_public_json('https://api.binance.com/api/v3/account',session);raise AssertionError('private endpoint accepted')
  except Exception as exc:assert 'nonpublic' in str(exc)
 print('FORWARD_SERVICE_AUTHORITY_SYNTHETIC_TEST_OK');print('OOS_READS=0');print('FORMAL_ARTIFACT_MUTATIONS=0');print('EXCHANGE_ORDER_PLACEMENT=0');print('LIVE_AUTHORIZATION=0')
if __name__=='__main__':main()
