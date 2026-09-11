"""Binance USDT-M public protocol helpers; deliberately no authenticated API."""
from __future__ import annotations
from .core import UniverseSymbol,ForwardResearchError
PUBLIC_FAPI='https://fapi.binance.com';PUBLIC_WS='wss://fstream.binance.com/market/stream?streams='
def parse_exchange_info(payload):
 out=[]
 for row in payload.get('symbols',[]):
  filters={x.get('filterType'):x for x in row.get('filters',[])}
  out.append(UniverseSymbol(row.get('symbol',''),0.0,row.get('contractType',''),row.get('quoteAsset',''),row.get('status',''),filters.get('PRICE_FILTER',{}).get('tickSize',''),filters.get('LOT_SIZE',{}).get('stepSize',''),filters.get('LOT_SIZE',{}).get('minQty',''),filters.get('MIN_NOTIONAL',{}).get('notional','')))
 return out
def apply_ticker_volumes(symbols,tickers):
 volumes={row.get('symbol'):float(row.get('quoteVolume',0) or 0) for row in tickers}
 return [UniverseSymbol(**{**row.__dict__,'quote_volume':volumes.get(row.symbol,0.0)}) for row in symbols]
def websocket_url(symbols,intervals=('1m','5m','15m','1h')):
 streams=[f'{symbol.lower()}@kline_{interval}' for symbol in sorted(symbols) for interval in intervals]
 if not streams:raise ForwardResearchError('binance_streams_required')
 return PUBLIC_WS+'/'.join(streams)
def parse_kline(payload,receive_time):
 data=payload.get('data',payload);k=data.get('k',{})
 if data.get('e')!='kline' or not k:raise ForwardResearchError('binance_kline_payload_invalid')
 from .collector import MarketEvent
 return MarketEvent(data.get('s',''),k.get('i',''),str(k.get('t')),receive_time,float(k['o']),float(k['h']),float(k['l']),float(k['c']),float(k['v']),bool(k['x']),int(k.get('f',0)))
