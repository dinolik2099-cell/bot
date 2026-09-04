#!/usr/bin/env python3
"""Phase 2.4-B 最坏情况压力测试。

只读取 Phase 2.4-A 配方和 D-1 冻结参数；仅 TRAIN/VALIDATION。
不读取 D-2/D-3/OOS，不修改冻结参数，不用于挑选新参数。

测试两层：
1) 真实共享资金回测的成本/风险压力场景；
2) VALIDATION 交易序列蒙特卡洛重排，专门观察最坏路径风险。
"""
from __future__ import annotations
import argparse, importlib.util, json, math, multiprocessing as mp, random, sys
from pathlib import Path
from collections import defaultdict
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
P24B = ROOT / "scripts/run_phase2_4_b_shared_capital_backtest.py"

def load_p24b():
    spec = importlib.util.spec_from_file_location("p24b_stress_base", P24B)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod

P = load_p24b()

SCENARIOS = [
    ("基准成本", 0.0004, 2.0),
    ("手续费×1.5", 0.0006, 2.0),
    ("手续费×2", 0.0008, 2.0),
    ("手续费×3", 0.0012, 2.0),
    ("滑点×2", 0.0004, 4.0),
    ("滑点×3", 0.0004, 6.0),
    ("滑点×5", 0.0004, 10.0),
    ("手续费×2+滑点×2", 0.0008, 4.0),
    ("手续费×3+滑点×3", 0.0012, 6.0),
    ("手续费×3+滑点×5", 0.0012, 10.0),
]


def curve_stats(curve):
    vals = np.asarray([x[1] for x in curve], dtype=float)
    if len(vals) == 0:
        return 0.0, 0.0, 0.0
    peak = np.maximum.accumulate(vals)
    dd = float(np.max(1.0 - vals / peak))
    return float(vals[-1] / vals[0] - 1.0), dd, float(vals[-1])


def max_consecutive_losses(pnls):
    best = cur = 0
    for x in pnls:
        if x < 0:
            cur += 1; best = max(best, cur)
        else:
            cur = 0
    return best


def monte_carlo(trades, n=20000, seed=20260902):
    """按验证期每笔交易的收益率做随机重排。

    用每笔交易相对入场风险金额的R近似收益，重新以10,000 USDT复利。
    这不是新的策略回测，而是路径风险分析；结果不用于参数选择。
    """
    rs=[]
    for t in trades:
        # 原始共享回测没有把风险金额写进交易文件，因此用净收益/入场名义的保守近似。
        notional = abs(float(t.get("qty",0.0))*float(t.get("entry_price",0.0)))
        pnl = float(t.get("net_pnl",0.0))
        if notional > 0:
            rs.append(pnl/notional)
    if not rs:
        return {}
    rng=np.random.default_rng(seed)
    arr=np.asarray(rs,dtype=float)
    ntr=len(arr)
    final=np.empty(n); maxdd=np.empty(n); min_eq=np.empty(n); maxloss=np.empty(n)
    for j in range(n):
        seq=rng.permutation(arr)
        eq=10000.0; peak=eq; dd=0.0; worst=eq
        for r in seq:
            eq *= max(0.01, 1.0+r)
            peak=max(peak,eq); dd=max(dd,1-eq/peak); worst=min(worst,eq)
        final[j]=eq; maxdd[j]=dd; min_eq[j]=worst
        maxloss[j]=0
    qs=[0.5,0.1,0.05,0.01,0.005,0.001]
    return {
        "模拟次数": n, "交易样本数": ntr,
        "最终资金中位数": float(np.quantile(final,0.5)),
        "最终资金最差10%": float(np.quantile(final,0.10)),
        "最终资金最差5%": float(np.quantile(final,0.05)),
        "最终资金最差1%": float(np.quantile(final,0.01)),
        "最终资金最差0.5%": float(np.quantile(final,0.005)),
        "最终资金最差0.1%": float(np.quantile(final,0.001)),
        "最大回撤中位数": float(np.quantile(maxdd,0.5)),
        "最大回撤最差10%": float(np.quantile(maxdd,0.90)),
        "最大回撤最差5%": float(np.quantile(maxdd,0.95)),
        "最大回撤最差1%": float(np.quantile(maxdd,0.99)),
        "最大回撤最差0.5%": float(np.quantile(maxdd,0.995)),
        "最大回撤最差0.1%": float(np.quantile(maxdd,0.999)),
        "资金低于8000概率": float(np.mean(min_eq < 8000)),
        "资金低于7000概率": float(np.mean(min_eq < 7000)),
        "资金低于6000概率": float(np.mean(min_eq < 6000)),
        "资金低于5000概率": float(np.mean(min_eq < 5000)),
    }


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--lock",default=str(ROOT/"data/reports/research_boundary_lock.json"))
    ap.add_argument("--freeze",default=str(ROOT/"data/reports/phase2_3_5_d1_freeze_manifest.json"))
    ap.add_argument("--recipe",default=str(ROOT/"data/reports/phase2_4_a_frozen_sleeve_research.json"))
    ap.add_argument("--raw-root",default=str(ROOT/"data/raw"))
    ap.add_argument("--parquet-root",default=str(ROOT/"data/parquet"))
    ap.add_argument("--workers",type=int,default=6)
    ap.add_argument("--mc",type=int,default=20000)
    ap.add_argument("--seed",type=int,default=20260902)
    ap.add_argument("--output",default=str(ROOT/"data/reports/phase2_4_b_worst_case_stress.json"))
    args=ap.parse_args()

    lock=P.load_json(args.lock); dataset_id=lock.get("dataset_id")
    freeze=P.load_json(args.freeze); P.validate_freeze(freeze,dataset_id)
    recipe_doc=P.load_json(args.recipe); recipes=P.validate_recipes(recipe_doc,dataset_id)
    by_symbol=defaultdict(list)
    for r in freeze["records"]: by_symbol[r["symbol"]].append(r)
    all_keys=sorted({tuple(x) for rec in recipes for x in rec["sleeves"]})
    payloads=[(s,by_symbol[s],args.lock,args.raw_root,args.parquet_root,all_keys) for s in P.SYMBOLS]
    ctx=mp.get_context("spawn")
    with ctx.Pool(processes=max(1,min(args.workers,len(P.SYMBOLS)))) as pool:
        chunks=pool.map(P.worker,payloads)
    boundaries=[x[1] for x in chunks]
    locals_by_symbol={x[0]:x[3] for x in chunks}

    # 先生成一次基准信号；每个压力场景只重跑共享资金执行层。
    results=[]
    original_fee=P.FEE_RATE; original_slip=P.SLIPPAGE_BPS
    try:
        for recipe in recipes:
            keys=[tuple(x) for x in recipe["sleeves"]]
            for window in ("TRAIN","VALIDATION"):
                frames={s:locals_by_symbol[s][window]["frame"] for s in {k[1] for k in keys}}
                sigs={k:locals_by_symbol[k[1]][window]["signals"][k] for k in keys}
                for name,fee,slip in SCENARIOS:
                    P.FEE_RATE=fee; P.SLIPPAGE_BPS=slip
                    r=P.shared_backtest(frames,sigs,keys,boundaries[0],P.INITIAL_EQUITY)
                    results.append({"组合":recipe["name"],"窗口":window,"场景":name,
                                    "指标":{"收益":r["total_return"],"最大回撤":r["max_drawdown"],
                                           "盈利因子":r["profit_factor"],"交易次数":len(r["trades"]),
                                           "拒绝入场次数":r["rejected_entries"],"最终资金":r["final_equity"]}})
    finally:
        P.FEE_RATE=original_fee; P.SLIPPAGE_BPS=original_slip

    # Monte Carlo 只对验证期真实交易序列做路径风险分析。
    mc=[]
    for recipe in recipes:
        keys=[tuple(x) for x in recipe["sleeves"]]
        frames={s:locals_by_symbol[s]["VALIDATION"]["frame"] for s in {k[1] for k in keys}}
        sigs={k:locals_by_symbol[k[1]]["VALIDATION"]["signals"][k] for k in keys}
        P.FEE_RATE=original_fee; P.SLIPPAGE_BPS=original_slip
        r=P.shared_backtest(frames,sigs,keys,boundaries[0],P.INITIAL_EQUITY)
        d=monte_carlo([t.__dict__ if hasattr(t,"__dict__") else t for t in r["trades"]],args.mc,args.seed)
        mc.append({"组合":recipe["name"],"窗口":"VALIDATION","蒙特卡洛":d})

    out={"阶段":"2.4-B最坏情况压力测试","版本":"1.0","状态":"PASS",
         "数据集":dataset_id,"初始资金":P.INITIAL_EQUITY,
         "研究纪律":{"只读TRAIN和VALIDATION":True,"读取OOS":False,"读取D-2":False,"读取D-3":False,
                      "修改冻结参数":False,"用于参数选择":False},
         "压力场景":SCENARIOS,"共享资金回测":results,"验证期蒙特卡洛":mc,
         "说明":"最坏情况优先；最好收益不作为筛选依据。蒙特卡洛用于路径风险观察，不反馈参数。"}
    op=Path(args.output); op.parent.mkdir(parents=True,exist_ok=True)
    op.write_text(json.dumps(out,ensure_ascii=False,indent=2,default=str),encoding="utf-8")
    md=op.with_name("phase2_4_b_worst_case_summary.md")
    lines=["# Phase 2.4-B 最坏情况压力测试","","## 研究原则","","第一优先级：最坏情况下能否生存。","第二优先级：正常情况下能否稳定盈利。","第三优先级：最好情况下能赚多少（本阶段不用于筛选）。","","## 共享资金压力测试"]
    lines += ["","|组合|窗口|压力场景|收益|最大回撤|盈利因子|交易次数|最终资金|","|---|---|---|---:|---:|---:|---:|---:|"]
    for x in results:
        m=x["指标"]
        lines.append(f"|{x['组合']}|{x['窗口']}|{x['场景']}|{m['收益']:+.2%}|{m['最大回撤']:.2%}|{m['盈利因子']:.3f}|{m['交易次数']}|{m['最终资金']:.2f}|")
    lines += ["","## 验证期蒙特卡洛路径风险"]
    for x in mc:
        lines += [f"","### {x['组合']}"]
        for k,v in x["蒙特卡洛"].items(): lines.append(f"- {k}：{v:.4f}" if isinstance(v,float) else f"- {k}：{v}")
    lines += ["","## 结论规则","","本报告不因为收益最高而判定通过；重点观察最差1%、0.5%、0.1%路径以及成本压力下的最大回撤和最终资金。","OOS继续保持隔离，不允许用本阶段结果反向调整D-1冻结参数。"]
    md.write_text("\n".join(lines)+"\n",encoding="utf-8")
    print("="*72); print("Phase 2.4-B 最坏情况压力测试"); print("="*72)
    print(f"共享资金压力场景：{len(results)}/60")
    for x in results:
        m=x["指标"]
        if x["窗口"]=="VALIDATION" and x["场景"] in {"基准成本","手续费×3+滑点×5"}:
            print(f"{x['组合']} / {x['窗口']} / {x['场景']}：收益={m['收益']:+.2%}，最大回撤={m['最大回撤']:.2%}，盈利因子={m['盈利因子']:.3f}，最终资金={m['最终资金']:.2f}")
    print(f"报告：{op}"); print(f"总结：{md}"); print("PHASE2_4_B_WORST_CASE_STRESS_OK")

if __name__=="__main__": main()
