"""Completed-candle opportunity detector, separate from model inputs."""
from __future__ import annotations
from .core import classify_opportunity
def detect_moves(symbol,rows,thresholds=(.05,.1,.2,.3,.4)):
 out=[]
 for start in range(len(rows)):
  entry=float(rows[start]['close'])
  for end in range(start+1,len(rows)):
   move=float(rows[end]['close'])/entry-1
   if abs(move)>=min(thresholds):
    event=classify_opportunity(symbol,rows[start]['event_time'],rows[end]['event_time'],move)
    if event and event['move_magnitude']>=max(value for value in thresholds if value<=event['move_magnitude']):out.append(event)
    break
 return out
