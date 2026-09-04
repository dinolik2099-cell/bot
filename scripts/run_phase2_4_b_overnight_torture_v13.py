#!/usr/bin/env python3
"""QuantBot Phase 2.4-B V1.3 夜间多模型/多方向最坏情况耐久压力测试。

仅使用 D-1 冻结参数 + TRAIN/VALIDATION；绝不读取 D-2/D-3/OOS。
重点：最坏情况、生存边界、风险闸门、多模型竞争、多方向同步冲击。
"""
from __future__ import annotations
import argparse, json, math, multiprocessing as mp, sys, time
from collections import defaultdict
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from quantbot.portfolio import shared_capital as P

MODELS=list(P.MODELS)
SYMBOLS=list(P.SYMBOLS)
START=P.INITIAL_EQUITY

# 固定组合，不按收益筛选；用于观察“模型数量增加”本身的风险。
RECIPES=[]
for n in (4,8,12):
    RECIPES.append((f'MODEL_{n}_X6',[(m,s) for m in MODELS[:n] for s in SYMBOLS]))
RECIPES.append(('ALL12_X6',[(m,s) for m in MODELS for s in SYMBOLS]))

SCENARIOS=[
 ('基准',1.0,1.0),('手续费×2',2.0,1.0),('滑点×3',1.0,3.0),
 ('手续费×3+滑点×5',3.0,5.0),('手续费×3+滑点×10',3.0,10.0),
]


def load_json(p): return json.loads(Path(p).read_text(encoding='utf-8'))

def validate(freeze,lock):
    if freeze.get('phase')!='2.3.5-D-1' or freeze.get('dataset_id')!=lock.get('dataset_id'): raise ValueError('D-1 freeze/dataset mismatch')
    recs=freeze.get('records',[])
    if len(recs)!=72: raise ValueError('D-1 freeze must have 72 records')
    if any(r.get('status')!='FROZEN' for r in recs): raise ValueError('freeze contains non-FROZEN record')

def worker(payload):
    symbol,freeze_records,lock_path,raw_root,parquet_root,all_keys=payload
    if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
    from quantbot.research.model_registry import get_model
    P.register_all_models()
    boundary,dataset,full,source=P.load_symbol_frame(symbol,lock_path,raw_root,parquet_root)
    by={r['model']:r for r in freeze_records}; local={}
    needed=sorted({m for m,s in all_keys if s==symbol})
    for w in ('TRAIN','VALIDATION'):
        frame=P.split_by_window(dataset,full,w); sigs={}
        for m in needed:
            rec=by[m]; spec=get_model(m)
            sigs[(m,symbol)]=P.build_signal_map(frame,spec.strategy,rec['params'],f'P24B13:{m}:{symbol}:{w}')
        local[w]={'frame':frame,'signals':sigs}
    return symbol,boundary,local

def run_shared(locals_by_symbol,boundary,keys,window,fee,slip):
    P.FEE_RATE=fee; P.SLIPPAGE_BPS=slip
    frames={s:locals_by_symbol[s][window]['frame'] for _,s in keys}
    sigs={k:locals_by_symbol[k[1]][window]['signals'][k] for k in keys}
    return P.shared_backtest(frames,sigs,keys,boundary,START)

def trade_returns(trades):
    out=[]
    for t in trades:
        e=float(t.entry_equity); p=float(t.net_pnl)
        if e>0 and math.isfinite(e) and math.isfinite(p): out.append(p/e)
    return np.asarray(out,dtype=float)

def path_metrics(rs):
    eq=peak=START; min_eq=eq; dd=0.; streak=mx=0
    for r in rs:
        eq=max(.01,eq*(1+float(r))); peak=max(peak,eq); dd=max(dd,1-eq/peak); min_eq=min(min_eq,eq)
        if r<0: streak+=1; mx=max(mx,streak)
        else: streak=0
    return eq,dd,min_eq,mx

def quantile_summary(samples):
    a=np.asarray(samples,float)
    return {'中位数':float(np.quantile(a,.5)),'最差10%':float(np.quantile(a,.9) if np.nanmax(a)>1 else np.quantile(a,.1)),
            '最差1%':float(np.quantile(a,.99) if np.nanmax(a)>1 else np.quantile(a,.01)),
            '最差0.1%':float(np.quantile(a,.999) if np.nanmax(a)>1 else np.quantile(a,.001))}

def mc_trade_bootstrap(rs,n,rng):
    if len(rs)==0:return {}
    d=[];m=[];f=[];s=[];L=len(rs)
    for _ in range(n):
        q=rs[rng.integers(0,L,size=L)]; x,y,z,w=path_metrics(q); f.append(x);d.append(y);m.append(z);s.append(w)
    return {'模拟次数':n,'最终资金':quantile_summary(f),'最大回撤':quantile_summary(d),'最低资金':quantile_summary(m),'最大连续亏损':quantile_summary(s),
            '低于8000概率':float(np.mean(np.asarray(m)<8000)),'低于7000概率':float(np.mean(np.asarray(m)<7000)),'低于5000概率':float(np.mean(np.asarray(m)<5000))}

def block_bootstrap(curve,n,rng,block=7):
    df=pd.DataFrame(curve,columns=['ts','eq']); df.ts=pd.to_datetime(df.ts,utc=True); df=df.sort_values('ts').drop_duplicates('ts').set_index('ts')
    daily=df.eq.resample('1D').last().dropna().pct_change().dropna().to_numpy(float)
    if len(daily)<10:return {}
    f=[];d=[];m=[];s=[];L=len(daily); target=L
    for _ in range(n):
        arr=[]
        while sum(len(x) for x in arr)<target:
            st=int(rng.integers(0,L)); arr.append(np.take(daily,np.arange(st,st+block)%L))
        x,y,z,w=path_metrics(np.concatenate(arr)[:target]); f.append(x);d.append(y);m.append(z);s.append(w)
    return {'模拟次数':n,'最终资金':quantile_summary(f),'最大回撤':quantile_summary(d),'最低资金':quantile_summary(m),'最大连续亏损':quantile_summary(s),
            '低于8000概率':float(np.mean(np.asarray(m)<8000)),'低于7000概率':float(np.mean(np.asarray(m)<7000)),'低于5000概率':float(np.mean(np.asarray(m)<5000))}

def adverse_direction(trades,shock):
    """多方向同步冲击：对同一时间窗口内的多笔交易同时恶化；只做尾部路径压力，不伪装成K线重算。"""
    ts=[]
    for t in trades:
        ts.append((pd.Timestamp(t.entry_time),pd.Timestamp(t.exit_time),float(t.net_pnl/t.entry_equity) if t.entry_equity else 0.,t.symbol,t.side))
    ts.sort(); seq=[]
    # 按 entry_time 聚簇；同一小时内不同币种/方向同时受损。
    groups=defaultdict(list)
    for a,b,r,sym,side in ts: groups[a.floor('h')].append((a,b,r,sym,side))
    for _,g in sorted(groups.items()):
        if len(g)>=2:
            # 同步压力：亏损扩大，盈利削弱；冲击比例随同时持仓数上升。
            factor=1.0+shock*min(len(g),4)/4.0
            seq.extend([r*factor if r<0 else r/max(1.0,factor) for _,_,r,_,_ in g])
        else: seq.extend([g[0][2]])
    return path_metrics(np.asarray(seq,float))

def audit(r):
    errs=[]; trades=r.get('trades',[])
    by=defaultdict(list)
    for t in trades:
        for k in ('entry_equity','risk_amount','risk_fraction','net_pnl'):
            if not hasattr(t,k) or not math.isfinite(float(getattr(t,k))): errs.append(f'缺少/非法字段:{k}')
        by[t.symbol].append((pd.Timestamp(t.entry_time),pd.Timestamp(t.exit_time)))
    for sym,x in by.items():
        x.sort()
        for a,b in zip(x,x[1:]):
            if b[0]<a[1]: errs.append(f'{sym}持仓重叠')
    return errs

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--hours',type=float,default=8); ap.add_argument('--workers',type=int,default=24); ap.add_argument('--mc-per-round',type=int,default=2000); ap.add_argument('--seed',type=int,default=20260903)
    ap.add_argument('--rounds',type=int,default=0); args=ap.parse_args()
    lock_path=ROOT/'data/reports/research_boundary_lock.json'; freeze_path=ROOT/'data/reports/phase2_3_5_d1_freeze_manifest.json'
    lock=load_json(lock_path); freeze=load_json(freeze_path); validate(freeze,lock)
    all_keys=sorted({k for _,ks in RECIPES for k in ks}); by=defaultdict(list)
    for r in freeze['records']: by[r['symbol']].append(r)
    ctx=mp.get_context('spawn'); payloads=[(s,by[s],str(lock_path),str(ROOT/'data/raw'),str(ROOT/'data/parquet'),all_keys) for s in SYMBOLS]
    with ctx.Pool(processes=min(6,args.workers)) as pool: chunks=pool.map(worker,payloads)
    boundary=chunks[0][1]; locals_by={x[0]:x[2] for x in chunks}
    out=ROOT/'data/reports/phase2_4_b_overnight_torture_v13.jsonl'; out.parent.mkdir(parents=True,exist_ok=True)
    summary=ROOT/'data/reports/phase2_4_b_overnight_torture_summary_v13.md'
    rng=np.random.default_rng(args.seed); start=time.time(); deadline=start+args.hours*3600; rnd=0; total=0; audit_fail=0
    with out.open('w',encoding='utf-8') as fp:
        while time.time()<deadline and (args.rounds<=0 or rnd<args.rounds):
            rnd+=1; round_start=time.time(); records=[]
            for recipe,keys in RECIPES:
                for window in ('TRAIN','VALIDATION'):
                    for sn,fm,sm in SCENARIOS:
                        fee=P.FEE_RATE*fm; slip=P.SLIPPAGE_BPS*sm
                        r=run_shared(locals_by,boundary,keys,window,fee,slip); errs=audit(r); audit_fail+=bool(errs)
                        rec={'轮次':rnd,'组合':recipe,'模型数量':len(set(m for m,_ in keys)),'Sleeve数量':len(keys),'窗口':window,'场景':sn,
                             '收益':r['total_return'],'最大回撤':r['max_drawdown'],'盈利因子':r['profit_factor'],'交易次数':len(r['trades']),'拒绝入场':r['rejected_entries'],'最终资金':r['final_equity'],'审计通过':not errs}
                        records.append(rec); fp.write(json.dumps(rec,ensure_ascii=False)+'\n'); total+=1
                    # 仅对 VALIDATION 做尾部模拟；TRAIN 用于压力基准，不参与选择。
                    if window=='VALIDATION':
                        P.FEE_RATE=.0004; P.SLIPPAGE_BPS=2.0
                        r=run_shared(locals_by,boundary,keys,window,.0004,2.0); rs=trade_returns(r['trades'])
                        bt=mc_trade_bootstrap(rs,args.mc_per_round,rng); bb=block_bootstrap(r['curve'],args.mc_per_round,rng)
                        ad=[]
                        for shock in (.25,.50,.75,1.0):
                            x=adverse_direction(r['trades'],shock); ad.append({'同步冲击':shock,'最终资金':x[0],'最大回撤':x[1],'最低资金':x[2],'最大连续亏损':x[3]})
                        fp.write(json.dumps({'轮次':rnd,'组合':recipe,'类型':'尾部模拟','交易Bootstrap':bt,'7日BlockBootstrap':bb,'多方向同步冲击':ad},ensure_ascii=False)+'\n')
            fp.flush()
            print(f'轮次 {rnd} 完成：累计共享回测={total}，本轮耗时={time.time()-round_start:.1f}s，累计={time.time()-start:.1f}s',flush=True)
    # 生成摘要：从 JSONL 汇总全部真实回测，保留最坏观察。
    df=pd.read_json(out,lines=True)
    rows=df[df['类型'].isna()] if '类型' in df else df
    lines=['# Phase 2.4-B V1.3 夜间多模型/多方向最坏情况压力测试','','状态：完成','',f'- 总运行时间：{(time.time()-start)/3600:.2f} 小时',f'- 轮次：{rnd}',f'- 共享资金回测次数：{total}',f'- 审计失败记录：{audit_fail}','- OOS/D-2/D-3：未读取','- 选模：未使用 OOS；不按最好收益筛选','', '## 各组合最坏共享资金结果']
    for recipe in [x[0] for x in RECIPES]:
        sub=rows[rows['组合']==recipe]
        if sub.empty: continue
        worst=sub.loc[sub['最大回撤'].idxmax()]; low=sub.loc[sub['最终资金'].idxmin()]
        lines += [f'### {recipe}',f'- 模型数：{int(sub.iloc[0]["模型数量"])}，Sleeve数：{int(sub.iloc[0]["Sleeve数量"])}',f'- 历史测试最大回撤上界样本：{worst["最大回撤"]:.2%}（{worst["窗口"]}/{worst["场景"]}）',f'- 最低最终资金样本：{low["最终资金"]:.2f}（{low["窗口"]}/{low["场景"]}）',f'- 最差PF样本：{sub["盈利因子"].min():.3f}']
    lines += ['', '## 判定原则','', '本轮不是选最高收益；优先判断本金破坏、最大回撤、连续亏损、风险上限执行和多方向同步冲击。','只有完成后续组合冻结、独立 OOS 后，才讨论正式交易授权。']
    summary.write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print('='*72); print('PHASE2_4_B_OVERNIGHT_TORTURE_V13_OK'); print(f'轮次={rnd} 共享回测={total} 审计失败={audit_fail}'); print(f'JSONL={out}'); print(f'SUMMARY={summary}')
if __name__=='__main__': main()
