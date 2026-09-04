from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pandas as pd, numpy as np
from quantbot.strategies.models import trend_breakout
from quantbot.backtest.engine import backtest, metrics
idx=pd.date_range('2024-01-01', periods=1000, freq='h', tz='UTC')
r=np.random.default_rng(1)
close=100*np.exp(np.cumsum(r.normal(0.0001,0.01,len(idx))))
df=pd.DataFrame({'open':close*(1+r.normal(0,0.001,len(idx))), 'high':close*1.005,'low':close*0.995,'close':close,'volume':r.uniform(1,10,len(idx))},index=idx)
sig=trend_breakout(df,lookback=40,stop_atr=2,reward_r=3)
c,t,h=backtest(df,sig)
print(metrics(c,t)); print('SMOKE_OK')
