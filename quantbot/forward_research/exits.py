"""Predeclared, direction-aware shadow exit variants; never order execution."""
from __future__ import annotations
from .core import directional_path,trailing_exit
TRAILING_DRAWDOWNS=(.05,.08,.12,.15)
def fixed_exit(direction,entry,prices,take_profit,stop_loss):
 for index,price in enumerate(prices):
  ret=(price/entry-1) if direction=='LONG' else (entry/price-1)
  if ret>=take_profit:return {'exit_index':index,'exit_price':price,'reason':'TAKE_PROFIT','gross_return':ret}
  if ret<=-stop_loss:return {'exit_index':index,'exit_price':price,'reason':'STOP','gross_return':ret}
 path=directional_path(direction,entry,prices);return {'exit_index':len(prices)-1,'exit_price':prices[-1],'reason':'TIME_STOP','gross_return':path['close_return']}
def replay_variants(direction,entry,prices,reversal_index=None):
 out=[{'rule':'FIXED','parameter':{'tp':.1,'stop':.05},**fixed_exit(direction,entry,prices,.1,.05)}]
 out += [{'rule':'PEAK_DRAWDOWN','parameter':value,**trailing_exit(direction,entry,prices,value)} for value in TRAILING_DRAWDOWNS]
 if reversal_index is not None and 0<=reversal_index<len(prices):out.append({'rule':'SIGNAL_REVERSAL','parameter':None,'exit_index':reversal_index,'exit_price':prices[reversal_index],'reason':'REVERSAL','gross_return':directional_path(direction,entry,prices[:reversal_index+1])['close_return']})
 return out
