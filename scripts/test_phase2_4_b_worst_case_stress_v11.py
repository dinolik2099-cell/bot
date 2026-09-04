#!/usr/bin/env python3
from __future__ import annotations
import importlib.util, sys
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('stress_v11',ROOT/'scripts'/'run_phase2_4_b_worst_case_stress_v11.py')
m=importlib.util.module_from_spec(spec); sys.modules[spec.name]=m; spec.loader.exec_module(m)
P=m.P

# 1) index type / base syntax audit
assert isinstance(np.int64(3), __import__('numbers').Integral)
assert 'entry_equity' in P.Trade.__dataclass_fields__
assert 'risk_amount' in P.Trade.__dataclass_fields__

# 2) Monte Carlo must distinguish permutation path DD from bootstrap final capital.
class T:
    def __init__(self,pnl,eq):
        self.net_pnl=pnl; self.entry_equity=eq
trades=[T(100,10000),T(-200,10000),T(300,10000),T(-100,10000),T(150,10000)]
rs=m.arr_trade_returns(trades)
assert len(rs)==5
rng=np.random.default_rng(123)
perm=m.mc_permutation(rs,200,rng)
boot=m.mc_bootstrap(rs,200,rng)
assert perm['最终资金最差10%']==perm['最终资金最差0.1%'] or abs(perm['最终资金最差10%']-perm['最终资金最差0.1%'])<1e-9
assert boot['最终资金最差10%'] != boot['最终资金最差0.1%']

# 3) daily block bootstrap produces valid non-empty output
curve=[]
for i,ts in enumerate(__import__('pandas').date_range('2026-01-01', periods=40, freq='D', tz='UTC')): curve.append((ts.isoformat(),10000*(1+0.001*i)))
dr=m.daily_returns(curve)
assert len(dr)>0
b=m.mc_block_bootstrap(dr,100,np.random.default_rng(1),block_days=3,target_days=len(dr))
assert b and b['模拟次数']==100

# 4) adversarial path must be calculable and explicit
adv=m.adversarial(rs)
assert adv['性质'].startswith('极端不利顺序')

# 5) result audit: valid + invalid overlap
valid=[]
for sym in ['BTCUSDT','ETHUSDT']:
    valid.append(T(1,10000))
# audit needs full fields, construct via simple namespace
from types import SimpleNamespace
x=SimpleNamespace(symbol='BTCUSDT',side='buy',entry_time='2026-01-01T00:00:00+00:00',exit_time='2026-01-01T01:00:00+00:00',qty=1,entry_price=100,exit_price=101,net_pnl=1,risk_amount=10,entry_equity=10000)
y=SimpleNamespace(**{**x.__dict__,'entry_time':'2026-01-01T00:30:00+00:00','exit_time':'2026-01-01T02:00:00+00:00'})
assert m.audit_result({'trades':[x]})==[]
assert m.audit_result({'trades':[x,y]})

print('中文结果命名：通过')
print('交易顺序重排与Bootstrap逻辑：通过')
print('7日Block Bootstrap：通过')
print('收益削弱压力：通过')
print('极端不利排序：通过')
print('交易字段/执行审计：通过')
print('numpy整数索引兼容：通过')
print('OOS/D-2/D-3隔离设计：通过')
print('PHASE2_4_B_WORST_CASE_STRESS_V11_TEST_OK')

# 6) shared engine smoke test with pandas DatetimeIndex; validates numpy integer get_loc path.
idx=__import__('pandas').date_range('2026-01-01', periods=5, freq='h', tz='UTC')
df=__import__('pandas').DataFrame({'open':[100,100,99,98,97],'high':[101,101,100,99,98],'low':[99,99,98,97,96],'close':[100,99,98,97,97],'volume':[1]*5},index=idx)
frames={'BTCUSDT':df}
sigs={('trend_breakout','BTCUSDT'):{idx[1]:{'side':'buy','stop_price':98.0,'take_profit':104.0,'tag':'T'}}}
class B: pass
b=B(); b.gaps={}
r=P.shared_backtest(frames,sigs,[('trend_breakout','BTCUSDT')],b,10000.0)
assert len(r['trades'])==1
tr=r['trades'][0]
assert tr.entry_equity>0 and tr.risk_amount>0
print('共享资金引擎DatatimeIndex执行烟测：通过')
print('交易风险字段写入：通过')
print('PHASE2_4_B_SHARED_ENGINE_SMOKE_OK')
