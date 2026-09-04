#!/usr/bin/env python3
"""QuantBot Phase 2.4-B V1.3.4 夜间多模型/多方向最坏情况耐久压力测试。

默认运行“短测”模式，避免误启动长时间压力测试；完整压力测试必须显式使用 --mode full。

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

BASE_FEE_RATE=float(P.FEE_RATE)
BASE_SLIPPAGE_BPS=float(P.SLIPPAGE_BPS)

def trade_returns(trades):
    out=[]
    for t in trades:
        e=float(t.entry_equity); p=float(t.net_pnl)
        if e>0 and math.isfinite(e) and math.isfinite(p): out.append(p/e)
    return np.asarray(out,dtype=float)

def path_metrics(rs):
    eq=peak=START; min_eq=eq; dd=0.; streak=mx=0
    for r in rs:
        eq=eq*(1+float(r));
        if eq <= 0:
            eq=0.0; peak=max(peak,eq); dd=max(dd,1.0 if peak>0 else 0.0); min_eq=0.0
            if r < 0: streak+=1; mx=max(mx,streak)
            break
        peak=max(peak,eq); dd=max(dd,1-eq/peak); min_eq=min(min_eq,eq)
        if r<0: streak+=1; mx=max(mx,streak)
        else: streak=0
    return eq,dd,min_eq,mx

def quantile_summary(samples, direction):
    a=np.asarray(samples,float)
    a=a[np.isfinite(a)]
    if len(a)==0: return {}
    q=lambda p: float(np.quantile(a,p))
    # “最差”方向必须与指标含义一致：资金/最低资金取低分位，
    # 回撤/连续亏损取高分位。
    if direction == "low":
        return {"中位数":q(.5),"最差10%":q(.1),"最差1%":q(.01),"最差0.1%":q(.001)}
    return {"中位数":q(.5),"最差10%":q(.9),"最差1%":q(.99),"最差0.1%":q(.999)}


def mc_trade_bootstrap(rs,n,rng):
    if len(rs)==0:return {}
    d=[];m=[];f=[];s=[];L=len(rs)
    for _ in range(n):
        q=rs[rng.integers(0,L,size=L)]; x,y,z,w=path_metrics(q); f.append(x);d.append(y);m.append(z);s.append(w)
    return {'模拟次数':n,'最终资金':quantile_summary(f,'low'),'最大回撤':quantile_summary(d,'high'),'最低资金':quantile_summary(m,'low'),'最大连续亏损':quantile_summary(s,'high'),
            '低于8000概率':float(np.mean(np.asarray(m)<8000)),'低于7000概率':float(np.mean(np.asarray(m)<7000)),'低于5000概率':float(np.mean(np.asarray(m)<5000))}

def block_bootstrap(curve,n,rng,block=7):
    df=pd.DataFrame(curve,columns=['ts','eq']); df.ts=pd.to_datetime(df.ts,utc=True); df=df.sort_values('ts').drop_duplicates('ts').set_index('ts')
    daily=df['eq'].resample('1D').last().dropna().pct_change().dropna().to_numpy(float)
    if len(daily)<10:return {}
    f=[];d=[];m=[];s=[];L=len(daily); target=L
    for _ in range(n):
        arr=[]
        while sum(len(x) for x in arr)<target:
            st=int(rng.integers(0,L)); arr.append(np.take(daily,np.arange(st,st+block)%L))
        x,y,z,w=path_metrics(np.concatenate(arr)[:target]); f.append(x);d.append(y);m.append(z);s.append(w)
    return {'模拟次数':n,'最终资金':quantile_summary(f,'low'),'最大回撤':quantile_summary(d,'high'),'最低资金':quantile_summary(m,'low'),'最大连续亏损':quantile_summary(s,'high'),
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

def model_streak_stats(trades):
    """按单个 Model×Symbol 统计连续亏损；组合总交易序列不能代替模型级质量。"""
    groups=defaultdict(list)
    for t in trades:
        key=tuple(t.sleeve_key) if getattr(t,'sleeve_key',None) else (str(t.tag), str(t.symbol))
        groups[key].append(t)
    rows=[]
    for key, items in groups.items():
        items=sorted(items,key=lambda t: pd.Timestamp(t.exit_time))
        streak=mx=0; loss_r=0.0; max_loss_r=0.0; start_eq=None; end_eq=None
        for t in items:
            pnl=float(t.net_pnl); risk=float(t.risk_amount)
            if pnl < 0:
                streak += 1; mx=max(mx,streak)
                if risk>0: loss_r += -pnl/risk
                max_loss_r=max(max_loss_r,loss_r)
                if start_eq is None: start_eq=float(t.entry_equity)
            else:
                streak=0; loss_r=0.0; start_eq=None
        rows.append({"模型":key[0],"交易对":key[1],"最大连续亏损":int(mx),"连续亏损累计R上限":float(max_loss_r)})
    return rows

def model_streak_gate(stats):
    max_streak=max((x["最大连续亏损"] for x in stats),default=0)
    severe=[x for x in stats if x["最大连续亏损"]>=16]
    reject=[x for x in stats if x["最大连续亏损"]>=21]
    return {"最高模型级连续亏损":max_streak,"严重模型数(>=16)":len(severe),"不合格模型数(>=21)":len(reject),"判定":"不合格" if reject else ("严重关注" if severe else "正常")}

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

def get_run_plan(mode):
    if mode == 'quick':
        # 短测：覆盖完整数据加载、共享资金回测、成本压力、模型级连续亏损审计，
        # 但只跑一个代表性组合、两个成本场景、TRAIN/VALIDATION，不做MC。
        recipes = [RECIPES[0]]
        scenarios = [SCENARIOS[0], SCENARIOS[-1]]
        windows = ('TRAIN', 'VALIDATION')
        return recipes, scenarios, windows, False
    return RECIPES, SCENARIOS, ('TRAIN', 'VALIDATION'), True

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--mode',choices=('quick','full'),default='quick'); ap.add_argument('--hours',type=float,default=8); ap.add_argument('--workers',type=int,default=24); ap.add_argument('--mc-per-round',type=int,default=2000); ap.add_argument('--seed',type=int,default=20260903)
    ap.add_argument('--rounds',type=int,default=0); args=ap.parse_args()
    recipes, scenarios, windows, enable_tail = get_run_plan(args.mode)
    lock_path=ROOT/'data/reports/research_boundary_lock.json'; freeze_path=ROOT/'data/reports/phase2_3_5_d1_freeze_manifest.json'
    lock=load_json(lock_path); freeze=load_json(freeze_path); validate(freeze,lock)
    all_keys=sorted({k for _,ks in recipes for k in ks}); by=defaultdict(list)
    for r in freeze['records']: by[r['symbol']].append(r)
    ctx=mp.get_context('spawn'); payloads=[(s,by[s],str(lock_path),str(ROOT/'data/raw'),str(ROOT/'data/parquet'),all_keys) for s in SYMBOLS]
    with ctx.Pool(processes=min(6,args.workers)) as pool: chunks=pool.map(worker,payloads)
    boundary=chunks[0][1]; locals_by={x[0]:x[2] for x in chunks}
    suffix='v134_quick' if args.mode=='quick' else 'v134_full'
    out=ROOT/'data/reports'/f'phase2_4_b_overnight_torture_{suffix}.jsonl'; out.parent.mkdir(parents=True,exist_ok=True)
    summary=ROOT/'data/reports'/f'phase2_4_b_overnight_torture_summary_{suffix}.md'
    rng=np.random.default_rng(args.seed); start=time.time()
    # 安全默认：短测最多约5分钟且只跑1轮；只有 --mode full 才允许按 --hours 长跑。
    if args.mode == 'quick':
        max_quick_hours = 5.0 / 60.0
        effective_hours = min(max(args.hours, 0.0), max_quick_hours) if args.hours != 8 else max_quick_hours
        round_limit = 1 if args.rounds <= 0 else min(args.rounds, 1)
    else:
        effective_hours = max(args.hours, 0.0)
        round_limit = args.rounds
    deadline=start+effective_hours*3600; rnd=0; total=0; audit_fail=0
    with out.open('w',encoding='utf-8') as fp:
        while time.time()<deadline and (round_limit<=0 or rnd<round_limit):
            rnd+=1; round_start=time.time(); records=[]
            for recipe,keys in recipes:
                for window in windows:
                    for sn,fm,sm in scenarios:
                        fee=BASE_FEE_RATE*fm; slip=BASE_SLIPPAGE_BPS*sm
                        r=run_shared(locals_by,boundary,keys,window,fee,slip); errs=audit(r); audit_fail+=bool(errs)
                        stats=model_streak_stats(r['trades']); gate=model_streak_gate(stats)
                        rec={'轮次':rnd,'组合':recipe,'模型数量':len(set(m for m,_ in keys)),'Sleeve数量':len(keys),'窗口':window,'场景':sn,
                             '收益':r['total_return'],'最大回撤':r['max_drawdown'],'盈利因子':r['profit_factor'],'交易次数':len(r['trades']),'拒绝入场':r['rejected_entries'],'最终资金':r['final_equity'],'最大模型级连续亏损':gate['最高模型级连续亏损'],'严重模型数':gate['严重模型数(>=16)'],'不合格模型数':gate['不合格模型数(>=21)'],'模型级判定':gate['判定'],'审计通过':not errs}
                        records.append(rec); fp.write(json.dumps(rec,ensure_ascii=False)+'\n'); total+=1
                    # 完整模式仅对 VALIDATION 做尾部模拟；短测跳过MC以控制运行时间。
                    if enable_tail and window=='VALIDATION':
                        r=run_shared(locals_by,boundary,keys,window,BASE_FEE_RATE,BASE_SLIPPAGE_BPS); rs=trade_returns(r['trades'])
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
    lines=[f'# Phase 2.4-B V1.3.4 {args.mode} 夜间多模型/多方向最坏情况压力测试','','状态：完成','',f'- 实际运行时间：{(time.time()-start)/3600:.2f} 小时',f'- 轮次：{rnd}',f'- 共享资金回测次数：{total}',f'- 审计失败记录：{audit_fail}','- OOS/D-2/D-3：未读取','- 选模：未使用 OOS；不按最好收益筛选','', '## 各组合最坏共享资金结果']
    for recipe in [x[0] for x in recipes]:
        sub=rows[rows['组合']==recipe]
        if sub.empty: continue
        worst=sub.loc[sub['最大回撤'].idxmax()]; low=sub.loc[sub['最终资金'].idxmin()]
        lines += [f'### {recipe}',f'- 模型数：{int(sub.iloc[0]["模型数量"])}，Sleeve数：{int(sub.iloc[0]["Sleeve数量"])}',f'- 历史测试最大回撤上界样本：{worst["最大回撤"]:.2%}（{worst["窗口"]}/{worst["场景"]}）',f'- 最低最终资金样本：{low["最终资金"]:.2f}（{low["窗口"]}/{low["场景"]}）',f'- 最差PF样本：{sub["盈利因子"].min():.3f}',f'- 最高模型×交易对连续亏损：{int(sub["最大模型级连续亏损"].max())}，不合格模型×交易对样本数：{int(sub["不合格模型数"].max())}']
    lines += ['', '## 判定原则','', '本轮不是选最高收益；优先判断本金破坏、最大回撤、连续亏损、风险上限执行和多方向同步冲击。','只有完成后续组合冻结、独立 OOS 后，才讨论正式交易授权。']
    summary.write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print('='*72); print('PHASE2_4_B_OVERNIGHT_TORTURE_V1.3.4_OK'); print(f'轮次={rnd} 共享回测={total} 审计失败={audit_fail}'); print(f'JSONL={out}'); print(f'SUMMARY={summary}')
if __name__=='__main__': main()
