#!/usr/bin/env python3
"""Phase 2.4-B V1.1：最坏情况/尾部风险扩展压力测试。

原则：最坏情况 > 正常稳定性 > 最好收益。
仅 TRAIN/VALIDATION；不读取 D-2/D-3/OOS，不修改冻结参数。

本版修复 V1.0 的蒙特卡洛缺陷，并增加：
1. 交易顺序重排：只用于路径回撤；最终资金天然不随顺序变化。
2. 交易Bootstrap：有放回抽样，观察样本外交易分布扰动。
3. 每日收益Block Bootstrap：保留连续亏损/盈利簇的时间结构。
4. 收益削弱压力：随机/固定削弱交易收益，观察成本/执行恶化后的尾部。
5. 最坏排序：将亏损交易集中到前段，作为极端上界，不作为现实概率。
6. 组合回测结果审计：风险上限、单币重叠、字段完整性、NaN/Inf。
"""
from __future__ import annotations
import argparse, importlib.util, json, math, multiprocessing as mp, sys
from collections import defaultdict
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
P24B = ROOT / "scripts" / "run_phase2_4_b_shared_capital_backtest.py"

def load_p24b():
    spec=importlib.util.spec_from_file_location("p24b_v11_base", P24B)
    mod=importlib.util.module_from_spec(spec); sys.modules[spec.name]=mod
    spec.loader.exec_module(mod); return mod
P=load_p24b()

SCENARIOS=[
    ("基准成本",0.0004,2.0),
    ("手续费×1.5",0.0006,2.0),
    ("手续费×2",0.0008,2.0),
    ("手续费×3",0.0012,2.0),
    ("滑点×2",0.0004,4.0),
    ("滑点×3",0.0004,6.0),
    ("滑点×5",0.0004,10.0),
    ("手续费×2+滑点×2",0.0008,4.0),
    ("手续费×3+滑点×3",0.0012,6.0),
    ("手续费×3+滑点×5",0.0012,10.0),
]


def arr_trade_returns(trades):
    out=[]
    for t in trades:
        ee=float(getattr(t,'entry_equity',0.0) or 0.0)
        pnl=float(getattr(t,'net_pnl',0.0) or 0.0)
        if ee>0 and np.isfinite(ee) and np.isfinite(pnl): out.append(pnl/ee)
    return np.asarray(out,dtype=float)


def path_metrics(returns, start=10000.0):
    eq=float(start); peak=eq; maxdd=0.0; min_eq=eq; loss_streak=0; max_streak=0
    for r in returns:
        if not np.isfinite(r): continue
        eq=max(0.01, eq*(1.0+float(r)))
        if eq>peak: peak=eq
        maxdd=max(maxdd,1.0-eq/peak)
        min_eq=min(min_eq,eq)
        if r<0: loss_streak+=1; max_streak=max(max_streak,loss_streak)
        else: loss_streak=0
    return float(eq),float(maxdd),float(min_eq),int(max_streak)


def summarize_samples(final,dd,min_eq,streak):
    def q(a,p): return float(np.quantile(a,p))
    return {
        "模拟次数":int(len(final)),
        "最终资金中位数":q(final,.5),"最终资金最差10%":q(final,.10),"最终资金最差5%":q(final,.05),"最终资金最差1%":q(final,.01),"最终资金最差0.5%":q(final,.005),"最终资金最差0.1%":q(final,.001),
        "最大回撤中位数":q(dd,.5),"最大回撤最差10%":q(dd,.90),"最大回撤最差5%":q(dd,.95),"最大回撤最差1%":q(dd,.99),"最大回撤最差0.5%":q(dd,.995),"最大回撤最差0.1%":q(dd,.999),
        "最低资金中位数":q(min_eq,.5),"最低资金最差10%":q(min_eq,.10),"最低资金最差5%":q(min_eq,.05),"最低资金最差1%":q(min_eq,.01),"最低资金最差0.5%":q(min_eq,.005),"最低资金最差0.1%":q(min_eq,.001),
        "最大连续亏损中位数":q(streak,.5),"最大连续亏损最差10%":q(streak,.90),"最大连续亏损最差1%":q(streak,.99),
        "最低资金低于8000概率":float(np.mean(min_eq<8000)),"最低资金低于7000概率":float(np.mean(min_eq<7000)),"最低资金低于6000概率":float(np.mean(min_eq<6000)),"最低资金低于5000概率":float(np.mean(min_eq<5000)),
    }


def mc_permutation(rs,n,rng):
    finals=np.empty(n); dds=np.empty(n); mins=np.empty(n); streak=np.empty(n)
    for i in range(n):
        f,d,m,s=path_metrics(rng.permutation(rs)); finals[i]=f; dds[i]=d; mins[i]=m; streak[i]=s
    return summarize_samples(finals,dds,mins,streak)


def mc_bootstrap(rs,n,rng):
    finals=np.empty(n); dds=np.empty(n); mins=np.empty(n); streak=np.empty(n); L=len(rs)
    for i in range(n):
        seq=rs[rng.integers(0,L,size=L)]
        f,d,m,s=path_metrics(seq); finals[i]=f; dds[i]=d; mins[i]=m; streak[i]=s
    return summarize_samples(finals,dds,mins,streak)


def daily_returns(curve):
    if not curve: return np.asarray([],dtype=float)
    df=pd.DataFrame(curve,columns=['ts','equity']); df['ts']=pd.to_datetime(df['ts'],utc=True)
    df=df.sort_values('ts').drop_duplicates('ts').set_index('ts')
    d=df['equity'].resample('1D').last().dropna()
    if len(d)<2: return np.asarray([],dtype=float)
    r=d.pct_change().replace([np.inf,-np.inf],np.nan).dropna().to_numpy(dtype=float)
    return r


def mc_block_bootstrap(dr,n,rng,block_days=7,target_days=None):
    if target_days is None: target_days=len(dr)
    if len(dr)==0: return {}
    finals=np.empty(n); dds=np.empty(n); mins=np.empty(n); streak=np.empty(n)
    L=len(dr)
    for i in range(n):
        chunks=[]
        while sum(map(len,chunks))<target_days:
            start=int(rng.integers(0,L)); chunks.append(np.take(dr,np.arange(start,start+block_days)%L))
        seq=np.concatenate(chunks)[:target_days]
        f,d,m,s=path_metrics(seq); finals[i]=f; dds[i]=d; mins[i]=m; streak[i]=s
    return summarize_samples(finals,dds,mins,streak)


def mc_return_haircut(rs,n,rng,haircut=0.30):
    # 每笔交易的收益幅度按随机执行恶化因子削弱；亏损也略向坏处扩大。
    finals=np.empty(n); dds=np.empty(n); mins=np.empty(n); streak=np.empty(n)
    for i in range(n):
        factors=rng.uniform(1.0-haircut,1.0,size=len(rs))
        seq=np.where(rs>=0,rs*factors,rs*(1.0+haircut*factors))
        seq=seq[rng.permutation(len(seq))]
        f,d,m,s=path_metrics(seq); finals[i]=f; dds[i]=d; mins[i]=m; streak[i]=s
    return summarize_samples(finals,dds,mins,streak)


def adversarial(rs):
    # 极端顺序：亏损按绝对值从大到小优先，随后盈利按小到大；用于观察极端路径上界。
    neg=sorted([float(x) for x in rs if x<0],key=lambda x:abs(x),reverse=True)
    pos=sorted([float(x) for x in rs if x>=0],key=lambda x:x)
    f,d,m,s=path_metrics(neg+pos)
    return {"最终资金":f,"最大回撤":d,"最低资金":m,"最大连续亏损":s,"性质":"极端不利顺序，不代表现实概率"}


def audit_result(r):
    trades=r.get('trades',[]); errors=[]
    if not isinstance(trades,list): errors.append('trades不是列表'); return errors
    required=['symbol','side','entry_time','exit_time','qty','entry_price','exit_price','net_pnl','risk_amount','entry_equity']
    for i,t in enumerate(trades):
        for k in required:
            if not hasattr(t,k): errors.append(f'交易{i}缺少{k}')
        vals=[getattr(t,k,None) for k in ['qty','entry_price','exit_price','net_pnl','risk_amount','entry_equity']]
        if any(v is None or not np.isfinite(float(v)) for v in vals): errors.append(f'交易{i}存在NaN/Inf')
        if float(getattr(t,'qty',0))<=0 or float(getattr(t,'entry_equity',0))<=0: errors.append(f'交易{i}数量/入场资金非法')
        if float(getattr(t,'risk_amount',0))<0: errors.append(f'交易{i}风险金额非法')
    bysym=defaultdict(list)
    for t in trades:
        try: bysym[t.symbol].append((pd.Timestamp(t.entry_time),pd.Timestamp(t.exit_time)))
        except Exception: errors.append('交易时间解析失败')
    for sym,items in bysym.items():
        items.sort()
        for a,b in zip(items,items[1:]):
            if b[0] < a[1]: errors.append(f'{sym}存在持仓时间重叠')
    return errors


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--lock',default=str(ROOT/'data/reports/research_boundary_lock.json'))
    ap.add_argument('--freeze',default=str(ROOT/'data/reports/phase2_3_5_d1_freeze_manifest.json'))
    ap.add_argument('--recipe',default=str(ROOT/'data/reports/phase2_4_a_frozen_sleeve_research.json'))
    ap.add_argument('--raw-root',default=str(ROOT/'data/raw')); ap.add_argument('--parquet-root',default=str(ROOT/'data/parquet'))
    ap.add_argument('--workers',type=int,default=6); ap.add_argument('--mc',type=int,default=20000); ap.add_argument('--seed',type=int,default=20260902)
    ap.add_argument('--output',default=str(ROOT/'data/reports/phase2_4_b_worst_case_stress_v11.json'))
    args=ap.parse_args()
    lock=P.load_json(args.lock); dataset_id=lock.get('dataset_id')
    freeze=P.load_json(args.freeze); P.validate_freeze(freeze,dataset_id)
    recipe_doc=P.load_json(args.recipe); recipes=P.validate_recipes(recipe_doc,dataset_id)
    by_symbol=defaultdict(list)
    for rec in freeze['records']: by_symbol[rec['symbol']].append(rec)
    all_keys=sorted({tuple(x) for rec in recipes for x in rec['sleeves']})
    payloads=[(s,by_symbol[s],args.lock,args.raw_root,args.parquet_root,all_keys) for s in P.SYMBOLS]
    ctx=mp.get_context('spawn')
    with ctx.Pool(processes=max(1,min(args.workers,len(P.SYMBOLS)))) as pool: chunks=pool.map(P.worker,payloads)
    boundary=chunks[0][1]; locals_by_symbol={x[0]:x[3] for x in chunks}

    results=[]; audits=[]; original_fee=P.FEE_RATE; original_slip=P.SLIPPAGE_BPS
    try:
        for recipe in recipes:
            keys=[tuple(x) for x in recipe['sleeves']]
            for window in ('TRAIN','VALIDATION'):
                frames={s:locals_by_symbol[s][window]['frame'] for s in {k[1] for k in keys}}
                sigs={k:locals_by_symbol[k[1]][window]['signals'][k] for k in keys}
                for name,fee,slip in SCENARIOS:
                    P.FEE_RATE=fee; P.SLIPPAGE_BPS=slip
                    r=P.shared_backtest(frames,sigs,keys,boundary,P.INITIAL_EQUITY)
                    errs=audit_result(r)
                    audits.append({'组合':recipe['name'],'窗口':window,'场景':name,'审计通过':not errs,'错误':errs})
                    results.append({'组合':recipe['name'],'窗口':window,'场景':name,'指标':{'收益':r['total_return'],'最大回撤':r['max_drawdown'],'盈利因子':r['profit_factor'],'交易次数':len(r['trades']),'拒绝入场次数':r['rejected_entries'],'最终资金':r['final_equity']}})
    finally:
        P.FEE_RATE=original_fee; P.SLIPPAGE_BPS=original_slip

    mc=[]; rng=np.random.default_rng(args.seed)
    for recipe in recipes:
        keys=[tuple(x) for x in recipe['sleeves']]
        frames={s:locals_by_symbol[s]['VALIDATION']['frame'] for s in {k[1] for k in keys}}
        sigs={k:locals_by_symbol[k[1]]['VALIDATION']['signals'][k] for k in keys}
        P.FEE_RATE=original_fee; P.SLIPPAGE_BPS=original_slip
        r=P.shared_backtest(frames,sigs,keys,boundary,P.INITIAL_EQUITY)
        rs=arr_trade_returns(r['trades']); dr=daily_returns(r['curve'])
        entry={'组合':recipe['name'],'窗口':'VALIDATION','交易样本数':int(len(rs)),'日收益样本数':int(len(dr)),
               '交易顺序重排':mc_permutation(rs,args.mc,rng),'交易Bootstrap':mc_bootstrap(rs,args.mc,rng),
               '7日Block Bootstrap':mc_block_bootstrap(dr,args.mc,rng,7),'收益削弱30%':mc_return_haircut(rs,args.mc,rng,.30),
               '极端不利排序':adversarial(rs)}
        mc.append(entry)

    audit_ok=all(x['审计通过'] for x in audits)
    out={'阶段':'2.4-B最坏情况压力测试','版本':'1.1','状态':'PASS' if audit_ok else 'FAIL','数据集':dataset_id,'初始资金':P.INITIAL_EQUITY,
         '研究纪律':{'只读TRAIN和VALIDATION':True,'读取OOS':False,'读取D-2':False,'读取D-3':False,'修改冻结参数':False,'用于参数选择':False},
         '压力场景':SCENARIOS,'共享资金压力结果':results,'共享资金执行审计':audits,'验证期尾部风险模拟':mc,
         '解释':{'交易顺序重排':'最终资金在固定交易样本下理论上与顺序无关，只观察路径最大回撤/最低资金。','交易Bootstrap':'有放回重采样，会改变最终资金分布。','7日Block Bootstrap':'以实际验证期每日组合权益变化为基础，保留短期收益簇结构。','收益削弱30%':'执行恶化假设，不是参数优化。','极端不利排序':'人为构造极端路径，只用于生存边界观察。'}}
    op=Path(args.output); op.parent.mkdir(parents=True,exist_ok=True); op.write_text(json.dumps(out,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
    md=op.with_name('phase2_4_b_worst_case_summary_v11.md')
    lines=['# Phase 2.4-B 最坏情况压力测试 V1.1','','## 优先级','','1. 最坏情况下能否活下来','2. 正常情况下能否稳定盈利','3. 最好情况下能赚多少（本阶段不作为筛选依据）','','## 执行审计',f'- 审计结果：{"全部通过" if audit_ok else "存在失败，禁止继续"}',f'- 压力场景：{len(results)}/60']
    lines += ['','## 成本/滑点压力结果','', '|组合|窗口|场景|收益|最大回撤|盈利因子|交易次数|最终资金|','|---|---|---|---:|---:|---:|---:|---:|']
    for x in results:
        m=x['指标']; lines.append(f"|{x['组合']}|{x['窗口']}|{x['场景']}|{m['收益']:+.2%}|{m['最大回撤']:.2%}|{m['盈利因子']:.3f}|{m['交易次数']}|{m['最终资金']:.2f}|")
    lines += ['','## 验证期尾部风险模拟']
    for x in mc:
        lines += ['',f"### {x['组合']}",f"- 交易样本数：{x['交易样本数']}",f"- 每日收益样本数：{x['日收益样本数']}"]
        for method in ['交易顺序重排','交易Bootstrap','7日Block Bootstrap','收益削弱30%']:
            lines += [f"",f"#### {method}"]
            d=x[method]
            for k,v in d.items(): lines.append(f"- {k}：{v:.4f}" if isinstance(v,float) else f"- {k}：{v}")
        d=x['极端不利排序']; lines += ['', '#### 极端不利排序',f"- 最终资金：{d['最终资金']:.2f}",f"- 最大回撤：{d['最大回撤']:.2%}",f"- 最低资金：{d['最低资金']:.2f}",f"- 最大连续亏损：{d['最大连续亏损']}",f"- 性质：{d['性质']}"]
    lines += ['','## 纪律结论','','本阶段不根据最高收益选择组合。重点看最差1%、0.5%、0.1%路径、最低资金、最大回撤、连续亏损，以及高成本/高滑点条件下是否失去正期望。','OOS、D-2、D-3继续隔离；本报告不得反向修改D-1冻结参数。']
    md.write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print('='*72); print('Phase 2.4-B 最坏情况压力测试 V1.1'); print('='*72)
    print('共享资金压力场景：%d/60'%len(results)); print('执行审计：%s'%('全部通过' if audit_ok else '失败'))
    for x in mc:
        d=x['交易Bootstrap']; print(f"{x['组合']} / Bootstrap：最差1%最大回撤={d['最大回撤最差1%']:.2%}，最差1%最低资金={d['最低资金最差1%']:.2f}，低于5000概率={d['最低资金低于5000概率']:.2%}")
    print(f'报告：{op}'); print(f'总结：{md}'); print('PHASE2_4_B_WORST_CASE_STRESS_V11_OK')

if __name__=='__main__': main()
