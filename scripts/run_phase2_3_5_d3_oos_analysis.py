#!/usr/bin/env python3
"""Phase 2.3.5-D-3: frozen OOS result analysis only.

This stage reads D-1 freeze metadata and D-2 OOS outputs. It does not read market
bars and never re-runs or changes a strategy. OOS is used only for the predeclared
post-validation classification/diagnostic analysis.
"""
from __future__ import annotations
import argparse, json, math, statistics
from pathlib import Path
from collections import defaultdict
import numpy as np
from quantbot.research.authorization_gate import require_oos_authorized

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_D1 = ROOT / "data/reports/phase2_3_5_d1_freeze_manifest.json"
DEFAULT_D2 = ROOT / "data/reports/phase2_3_5_d2_oos_validation.json"
DEFAULT_CURVES = ROOT / "data/reports/phase2_3_5_d2_oos_equity_curves.jsonl"
EXPECTED_MODELS = [
    "price_ema_momentum","rsi_momentum","roc_momentum","higher_high_lower_low",
    "volume_trend","bollinger_breakout","ema_slope","donchian_breakout",
    "volume_breakout","volatility_regime_trend","trend_breakout","macd_trend",
]
EXPECTED_SYMBOLS = ["BTCUSDT","ETHUSDT","BNBUSDT","SOLUSDT","XRPUSDT","DOGEUSDT"]

# PREDECLARED BEFORE LOOKING AT D-2 DETAILED RESULTS.
MIN_TRADES_RELIABLE = 20
MIN_TRADES_STRONG = 30
STRONG_PF = 1.10
STRONG_DD = 0.25
STRONG_CALMAR = 0.75
RETAIN_PF = 1.00
RETAIN_DD = 0.35
RETAIN_CALMAR = 0.40


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def finite(x):
    try: return math.isfinite(float(x))
    except Exception: return False


def sharpe_from_curve(curve):
    vals = np.asarray([float(x[1]) for x in curve], dtype=float)
    if len(vals) < 3 or np.any(vals <= 0): return 0.0
    r = vals[1:] / vals[:-1] - 1.0
    r = r[np.isfinite(r)]
    if len(r) < 2 or float(r.std(ddof=1)) == 0: return 0.0
    return float(r.mean() / r.std(ddof=1) * math.sqrt(24*365))


def sortino_from_curve(curve):
    vals = np.asarray([float(x[1]) for x in curve], dtype=float)
    if len(vals) < 3 or np.any(vals <= 0): return 0.0
    r = vals[1:] / vals[:-1] - 1.0
    r = r[np.isfinite(r)]
    neg = r[r < 0]
    if len(r) < 2 or len(neg) == 0: return float("inf") if r.mean() > 0 else 0.0
    downside = math.sqrt(float(np.mean(neg**2)))
    return float(r.mean() / downside * math.sqrt(24*365)) if downside > 0 else 0.0


def extra(m, curve):
    ret = float(m.get("total_return", 0.0)); dd = float(m.get("max_drawdown", 0.0)); pf = float(m.get("profit_factor", 0.0))
    calmar = ret/dd if dd > 0 else (float("inf") if ret > 0 else 0.0)
    return {
        "sharpe_like": sharpe_from_curve(curve),
        "sortino_like": sortino_from_curve(curve),
        "calmar_like": calmar,
        "return_minus_dd": ret-dd,
        "pf_minus_one": pf-1.0,
        "return_per_trade": ret/float(m.get("trades",0)) if m.get("trades",0) else 0.0,
    }


def classify(m, e):
    ret=float(m.get("total_return",0)); pf=float(m.get("profit_factor",0)); dd=float(m.get("max_drawdown",0)); trades=int(m.get("trades",0)); cal=float(e["calmar_like"])
    # A/B/C/D are fixed post-OOS diagnostic buckets, not parameter-selection rules.
    if ret > 0 and pf >= STRONG_PF and dd <= STRONG_DD and trades >= MIN_TRADES_STRONG and cal >= STRONG_CALMAR:
        return "A_STRONG"
    if ret > 0 and pf >= RETAIN_PF and dd <= RETAIN_DD and trades >= MIN_TRADES_RELIABLE and cal >= RETAIN_CALMAR:
        return "B_RETAIN"
    if ret > 0 and pf >= RETAIN_PF:
        return "C_OBSERVE"
    return "D_RETIRE"


def validate_inputs(d1, d2):
    if d2.get("phase") != "2.3.5-D-2": raise ValueError("D-2报告phase不正确")
    if d1.get("phase") != "2.3.5-D-1": raise ValueError("D-1冻结清单phase不正确")
    if d1.get("dataset_id") != d2.get("dataset_id"): raise ValueError("D-1/D-2 dataset_id不一致")
    recs=d1.get("records",[]); results=d2.get("results",[])
    if len(recs)!=72 or len(results)!=72: raise ValueError(f"必须是72个单元：D1={len(recs)}, D2={len(results)}")
    keys={(r["model"],r["symbol"]) for r in recs}; keys2={(r["model"],r["symbol"]) for r in results}
    if keys != set((m,s) for m in EXPECTED_MODELS for s in EXPECTED_SYMBOLS): raise ValueError("D-1不是预期72-cell矩阵")
    if keys2 != keys: raise ValueError("D-2不是同一72-cell矩阵")
    if any(r.get("status")!="FROZEN" or not r.get("oos_authorized") for r in recs): raise ValueError("存在非FROZEN或未授权OOS的D-1记录")


def load_curves(path):
    curves=defaultdict(list)
    with Path(path).open(encoding="utf-8") as f:
        for line in f:
            if not line.strip(): continue
            x=json.loads(line); curves[(x["model"],x["symbol"])].append((x["timestamp"],float(x["equity"])))
    for k in curves: curves[k].sort()
    return curves


def pearson(a,b):
    if len(a)<3 or len(b)<3: return 0.0
    return float(np.corrcoef(np.asarray(a),np.asarray(b))[0,1]) if np.std(a)>0 and np.std(b)>0 else 0.0


def curve_return_series(curve):
    d=dict(curve); ts=sorted(d); vals=np.asarray([d[t] for t in ts],float)
    if len(vals)<3: return {},[]
    r=vals[1:]/vals[:-1]-1
    return {ts[i+1]:float(r[i]) for i in range(len(r)) if np.isfinite(r[i])},ts[1:]


def run(args):
    require_oos_authorized(ROOT / "docs/handoff/CANDIDATE_UNIVERSE_FREEZE_N3.json", json.loads((ROOT / "data/reports/research_boundary_lock.json").read_text(encoding="utf-8")))
    d1=load_json(args.d1); d2=load_json(args.d2); validate_inputs(d1,d2); curves=load_curves(args.curves)
    if set(curves) != {(m,s) for m in EXPECTED_MODELS for s in EXPECTED_SYMBOLS}: raise ValueError("OOS equity curve缺少72个单元")
    rows=[]
    for r in d2["results"]:
        key=(r["model"],r["symbol"]); m=r["oos_metrics"]; e=extra(m,curves[key]); cls=classify(m,e)
        rows.append({"model":r["model"],"category":r.get("category"),"symbol":r["symbol"],"params":r["params"],"d1_train_rank":r.get("d1_train_rank"),"d1_train_metrics":r.get("d1_train_metrics"),"d1_validation_metrics":r.get("d1_validation_metrics"),"oos_metrics":m,"oos_extra":e,"classification":cls,"rows":r.get("rows"),"trades_detail_count":len(r.get("trades",[]))})
    rows.sort(key=lambda x:(x["oos_metrics"].get("total_return",0)-x["oos_metrics"].get("max_drawdown",0),x["oos_metrics"].get("profit_factor",0)),reverse=True)
    rank_by_key={ (x["model"],x["symbol"]):i+1 for i,x in enumerate(rows)}
    for x in rows: x["oos_rank_return_minus_dd"]=rank_by_key[(x["model"],x["symbol"])]

    model_groups=defaultdict(list); symbol_groups=defaultdict(list)
    for x in rows: model_groups[x["model"]].append(x); symbol_groups[x["symbol"]].append(x)
    def aggregate(group):
        ms=[x["oos_metrics"] for x in group]; n=len(group)
        return {"cells":n,"positive_return":sum(float(m.get("total_return",0))>0 for m in ms),"pf_ge_1":sum(float(m.get("profit_factor",0))>=1 for m in ms),"a_strong":sum(x["classification"]=="A_STRONG" for x in group),"b_retain":sum(x["classification"]=="B_RETAIN" for x in group),"c_observe":sum(x["classification"]=="C_OBSERVE" for x in group),"d_retire":sum(x["classification"]=="D_RETIRE" for x in group),"median_return":statistics.median(float(m.get("total_return",0)) for m in ms),"median_dd":statistics.median(float(m.get("max_drawdown",0)) for m in ms),"median_pf":statistics.median(float(m.get("profit_factor",0)) for m in ms),"total_trades":sum(int(m.get("trades",0)) for m in ms),"mean_return":statistics.mean(float(m.get("total_return",0)) for m in ms),"mean_dd":statistics.mean(float(m.get("max_drawdown",0)) for m in ms)}
    model_summary={k:aggregate(v) for k,v in model_groups.items()}; symbol_summary={k:aggregate(v) for k,v in symbol_groups.items()}

    # Three-stage stability: compare signs and PF gates, plus validation->OOS return degradation.
    for x in rows:
        vm=x["d1_validation_metrics"] or {}; tm=x["d1_train_metrics"] or {}; om=x["oos_metrics"]
        x["three_stage"]={"train_positive":float(tm.get("total_return",0))>0,"validation_positive":float(vm.get("total_return",0))>0,"oos_positive":float(om.get("total_return",0))>0,"train_pf_ge_1":float(tm.get("profit_factor",0))>=1,"validation_pf_ge_1":float(vm.get("profit_factor",0))>=1,"oos_pf_ge_1":float(om.get("profit_factor",0))>=1,"validation_to_oos_return_delta":float(om.get("total_return",0))-float(vm.get("total_return",0)),"validation_to_oos_pf_delta":float(om.get("profit_factor",0))-float(vm.get("profit_factor",0))}

    # Model/symbol return-series correlation is diagnostic only; it does not select parameters.
    rs={k:curve_return_series(v)[0] for k,v in curves.items()}; corr=[]
    for i,k1 in enumerate(sorted(rs)):
        for k2 in sorted(rs)[i+1:]:
            common=sorted(set(rs[k1]) & set(rs[k2]))
            if len(common)>=20:
                corr.append({"left":list(k1),"right":list(k2),"correlation":pearson([rs[k1][t] for t in common],[rs[k2][t] for t in common]),"observations":len(common)})
    corr_sorted=sorted(corr,key=lambda x:abs(x["correlation"]))
    out={"phase":"2.3.5-D-3","version":"1.0","status":"PASS","purpose":"仅分析D-2冻结参数OOS结果，不重新运行策略、不改参数、不使用OOS反向调参。","dataset_id":d2["dataset_id"],"input_reports":{"d1":str(Path(args.d1)),"d2":str(Path(args.d2)),"curves":str(Path(args.curves))},"predeclared_classification_rules":{"A_STRONG":f"Return>0, PF>={STRONG_PF}, DD<={STRONG_DD:.0%}, Trades>={MIN_TRADES_STRONG}, Calmar-like>={STRONG_CALMAR}","B_RETAIN":f"Return>0, PF>={RETAIN_PF}, DD<={RETAIN_DD:.0%}, Trades>={MIN_TRADES_RELIABLE}, Calmar-like>={RETAIN_CALMAR}","C_OBSERVE":"Return>0 且 PF>=1，但未达到A/B；仅观察，不自动进入实盘","D_RETIRE":"其余结果；研究池淘汰候选，不代表删除历史研究记录"},"counts":{"cells":len(rows),"a_strong":sum(x["classification"]=="A_STRONG" for x in rows),"b_retain":sum(x["classification"]=="B_RETAIN" for x in rows),"c_observe":sum(x["classification"]=="C_OBSERVE" for x in rows),"d_retire":sum(x["classification"]=="D_RETIRE" for x in rows),"positive_return":sum(float(x["oos_metrics"].get("total_return",0))>0 for x in rows),"pf_ge_1":sum(float(x["oos_metrics"].get("profit_factor",0))>=1 for x in rows)},"cell_results":rows,"model_summary":model_summary,"symbol_summary":symbol_summary,"correlation_diagnostics":{"pairs":len(corr_sorted),"lowest_abs_10":corr_sorted[:10],"highest_abs_10":sorted(corr_sorted,key=lambda x:abs(x["correlation"]),reverse=True)[:10]},"interpretation":"D-3输出是OOS后分析与分类。任何A/B/C/D分类均不能回写D-1参数；后续组合研究应使用冻结参数和这些结果作为输入。"}
    outp=Path(args.output); outp.parent.mkdir(parents=True,exist_ok=True); outp.write_text(json.dumps(out,ensure_ascii=False,indent=2,default=str),encoding="utf-8")
    md=outp.with_name("phase2_3_5_d3_summary.md")
    lines=["# Phase 2.3.5-D-3 OOS深度分析", "", "状态：通过", "", "## 结果概览", f"- Model×Symbol：{len(rows)}", f"- A 强稳定：{out['counts']['a_strong']}", f"- B 保留：{out['counts']['b_retain']}", f"- C 观察：{out['counts']['c_observe']}", f"- D 淘汰候选：{out['counts']['d_retire']}", f"- 正收益：{out['counts']['positive_return']}/72", f"- PF≥1：{out['counts']['pf_ge_1']}/72", "", "## 固定分类规则", *[f"- {k}：{v}" for k,v in out["predeclared_classification_rules"].items()], "", "## 72个单元排名（Return - DD）", "", "|排名|模型|币种|分类|Return|DD|PF|Trades|Calmar|Sharpe-like|", "|---:|---|---|---|---:|---:|---:|---:|---:|---:|"]
    for i,x in enumerate(rows,1):
        m=x["oos_metrics"]; e=x["oos_extra"]; lines.append(f"|{i}|{x['model']}|{x['symbol']}|{x['classification']}|{float(m.get('total_return',0)):+.2%}|{float(m.get('max_drawdown',0)):.2%}|{float(m.get('profit_factor',0)):.3f}|{int(m.get('trades',0))}|{e['calmar_like']:.3f}|{e['sharpe_like']:.3f}|")
    lines += ["", "## 模型级汇总", "", "|模型|正收益|PF≥1|A|B|C|D|中位Return|中位DD|中位PF|总交易|", "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for k,v in sorted(model_summary.items(),key=lambda kv:(kv[1]['median_return']-kv[1]['median_dd']),reverse=True): lines.append(f"|{k}|{v['positive_return']}/6|{v['pf_ge_1']}/6|{v['a_strong']}|{v['b_retain']}|{v['c_observe']}|{v['d_retire']}|{v['median_return']:+.2%}|{v['median_dd']:.2%}|{v['median_pf']:.3f}|{v['total_trades']}|")
    lines += ["", "## 币种级汇总", "", "|币种|正收益|PF≥1|A|B|C|D|中位Return|中位DD|中位PF|总交易|", "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for k,v in symbol_summary.items(): lines.append(f"|{k}|{v['positive_return']}/12|{v['pf_ge_1']}/12|{v['a_strong']}|{v['b_retain']}|{v['c_observe']}|{v['d_retire']}|{v['median_return']:+.2%}|{v['median_dd']:.2%}|{v['median_pf']:.3f}|{v['total_trades']}|")
    lines += ["", "## 研究纪律", "- 本阶段只读取D-1冻结清单与D-2 OOS结果。", "- 不读取TRAIN/VALIDATION市场数据，不重新运行策略。", "- 不修改D-1参数，不因OOS结果重新调参。", "- 相关性仅用于后续组合研究诊断，不直接决定单模型参数。"]
    md.write_text("\n".join(lines)+"\n",encoding="utf-8")
    print("="*72); print("Phase 2.3.5-D-3 OOS深度分析"); print("="*72); print("状态：通过"); print(f"72-cell：{len(rows)}/72"); print(f"A强稳定：{out['counts']['a_strong']}"); print(f"B保留：{out['counts']['b_retain']}"); print(f"C观察：{out['counts']['c_observe']}"); print(f"D淘汰候选：{out['counts']['d_retire']}"); print(f"报告：{outp}"); print(f"总结：{md}"); print("PHASE2_3_5_D3_OOS_ANALYSIS_OK")

def main():
    ap=argparse.ArgumentParser(description="Phase 2.3.5-D-3 OOS深度分析")
    ap.add_argument("--d1",default=str(DEFAULT_D1)); ap.add_argument("--d2",default=str(DEFAULT_D2)); ap.add_argument("--curves",default=str(DEFAULT_CURVES));
    ap.add_argument("--output",default=str(ROOT/"data/reports/phase2_3_5_d3_oos_analysis.json"))
    run(ap.parse_args())

if __name__=="__main__": main()
