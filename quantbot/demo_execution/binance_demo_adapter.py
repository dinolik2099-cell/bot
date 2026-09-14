"""Single Demo Futures REST boundary; live URLs are unrepresentable."""
from __future__ import annotations
import hashlib,hmac,json,time
from urllib.parse import urlencode
from urllib.request import Request,urlopen
from .config import DEMO_FUTURES_ENDPOINTS
from .core import DemoExecutionError

class BinanceDemoAdapter:
 def __init__(self,endpoint,api_key=None,api_secret=None,transport=None):
  self.endpoint=str(endpoint).rstrip('/')
  if self.endpoint not in DEMO_FUTURES_ENDPOINTS:raise DemoExecutionError('demo_endpoint_fence_rejected')
  self.api_key,self.api_secret,self.transport=api_key,api_secret,transport
 def _request(self,method,path,params=None,signed=False):
  if not path.startswith('/fapi/') or 'order' in path and self.endpoint not in DEMO_FUTURES_ENDPOINTS:raise DemoExecutionError('demo_live_endpoint_forbidden')
  data=dict(params or {})
  if signed:
   if not self.api_key or not self.api_secret:raise DemoExecutionError('demo_credentials_missing')
   data['timestamp']=int(time.time()*1000);query=urlencode(sorted(data.items()));data['signature']=hmac.new(self.api_secret.encode(),query.encode(),hashlib.sha256).hexdigest()
  query=urlencode(data);url=self.endpoint+path+('?' + query if query else '')
  if self.transport:return self.transport(method,url,dict(data),signed)
  request=Request(url,method=method,headers={'X-MBX-APIKEY':self.api_key or ''})
  try:
   with urlopen(request,timeout=20) as response:return json.loads(response.read().decode())
  except Exception as exc:raise DemoExecutionError('demo_api_request_failed:'+type(exc).__name__) from exc
 def server_time(self):return self._request('GET','/fapi/v1/time')
 def exchange_info(self):return self._request('GET','/fapi/v1/exchangeInfo')
 def account(self):return self._request('GET','/fapi/v2/account',signed=True)
 def balance(self):return self._request('GET','/fapi/v2/balance',signed=True)
 def positions(self):return self._request('GET','/fapi/v2/positionRisk',signed=True)
 def position_mode(self):return self._request('GET','/fapi/v1/positionSide/dual',signed=True)
 def open_orders(self):return self._request('GET','/fapi/v1/openOrders',signed=True)
 def query_order(self,client_order_id,symbol):return self._request('GET','/fapi/v1/order',{'origClientOrderId':client_order_id,'symbol':symbol},True)
 def create_order(self,params):return self._request('POST','/fapi/v1/order',params,True)
 def cancel_order(self,client_order_id,symbol):return self._request('DELETE','/fapi/v1/order',{'origClientOrderId':client_order_id,'symbol':symbol},True)
 def change_leverage(self,symbol,leverage):return self._request('POST','/fapi/v1/leverage',{'symbol':symbol,'leverage':leverage},True)
 def change_margin_type(self,symbol,margin_type):return self._request('POST','/fapi/v1/marginType',{'symbol':symbol,'marginType':margin_type},True)
