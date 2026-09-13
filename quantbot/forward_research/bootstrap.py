"""Public, causally bounded 1h seed history for Forward Shadow.

Bootstrap rows are inputs to frozen declarations only.  They are recorded in
their own append-only evidence stream and never increment websocket/Forward
observation counters.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from urllib.parse import urlencode

from .binance_public import PUBLIC_FAPI
from .core import ForwardResearchError, identity


def _utc(value):
    parsed=datetime.fromisoformat(str(value).replace('Z','+00:00'))
    if parsed.tzinfo is None or parsed.utcoffset().total_seconds()!=0: raise ForwardResearchError('forward_bootstrap_time_not_utc')
    return parsed


def frozen_warmup_bars(declarations, execution_lag_bars=1):
    values=[int(row.get('warmup_bars',0)) for row in declarations]
    if not values or any(value<1 for value in values) or execution_lag_bars<1: raise ForwardResearchError('forward_bootstrap_warmup_invalid')
    return max(values)+execution_lag_bars


def fetch_completed_1h_candles(session, *, symbol, decision_time, count):
    """Read only public completed klines ending strictly before decision time."""
    if not symbol or type(count) is not int or count<1: raise ForwardResearchError('forward_bootstrap_request_invalid')
    decision=_utc(decision_time)
    query=urlencode({'symbol':symbol,'interval':'1h','limit':min(1500,count+8),'endTime':int(decision.timestamp()*1000)-1})
    endpoint=f'{PUBLIC_FAPI}/fapi/v1/klines?{query}'
    response=session.get(endpoint,timeout=30);response.raise_for_status();payload=response.json()
    rows=[]
    for item in payload:
        if not isinstance(item,list) or len(item)<7: raise ForwardResearchError('forward_bootstrap_payload_invalid')
        close_time=datetime.fromtimestamp(int(item[6])/1000,timezone.utc)
        if close_time>=decision: continue
        rows.append({'event_time':datetime.fromtimestamp(int(item[0])/1000,timezone.utc).isoformat(),'open':float(item[1]),'high':float(item[2]),'low':float(item[3]),'close':float(item[4]),'volume':float(item[5]),'closed':True,'close_time':close_time.isoformat()})
    rows=sorted(rows,key=lambda row:row['event_time'])[-count:]
    if len(rows)<count: raise ForwardResearchError('forward_bootstrap_insufficient_completed_history')
    if any(_utc(row['close_time'])>=decision for row in rows): raise ForwardResearchError('forward_bootstrap_future_candle')
    digest=hashlib.sha256('\n'.join(f"{row['event_time']}:{row['close']}" for row in rows).encode()).hexdigest()
    return rows,{'symbol':symbol,'source_endpoint':PUBLIC_FAPI+'/fapi/v1/klines','requested_at':decision.isoformat(),'as_of':decision.isoformat(),'first_completed_candle':rows[0]['event_time'],'last_completed_candle':rows[-1]['event_time'],'count':len(rows),'bootstrap_identity':identity({'symbol':symbol,'as_of':decision.isoformat(),'count':len(rows),'sha256':digest}),'sha256':digest,'forward_observation_coverage':False}
