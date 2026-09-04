from __future__ import annotations
import argparse, json
from collections import Counter, defaultdict
from pathlib import Path

THRESHOLDS = ((10, '合格'), (15, '警戒'), (20, '严重警戒'), (10**9, '淘汰候选'))

def grade(n: int) -> str:
    for mx, name in THRESHOLDS:
        if n <= mx: return name
    return '淘汰候选'

def q(values, p):
    if not values: return 0.0
    xs=sorted(values); pos=(len(xs)-1)*p; lo=int(pos); hi=min(lo+1,len(xs)-1); f=pos-lo
    return xs[lo]*(1-f)+xs[hi]*f

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--root', default='.')
    ap.add_argument('--out-dir', default='data/reports')
    args=ap.parse_args(); root=Path(args.root); out=Path(args.out_dir); out.mkdir(parents=True,exist_ok=True)
    d1=json.loads((root/'data/reports/phase2_3_5_d1_freeze_manifest.json').read_text())['records']
    d2=json.loads((root/'data/reports/phase2_3_5_d2_oos_validation.json').read_text())['results']
    oos={(r['model'],r['symbol']):r['oos_metrics'] for r in d2}
    rows=[]
    for r in d1:
        if r.get('status')!='FROZEN': continue
        key=(r['model'],r['symbol']); tm=r['train_metrics']; vm=r['validation_metrics']; om=oos.get(key,{})
        max_loss=max(int(tm['max_consecutive_losses']),int(vm['max_consecutive_losses']),int(om.get('max_consecutive_losses',0)))
        row={'model':r['model'],'symbol':r['symbol'],'category':r.get('category',''),'train_max_consecutive_losses':int(tm['max_consecutive_losses']),'validation_max_consecutive_losses':int(vm['max_consecutive_losses']),'oos_max_consecutive_losses':int(om.get('max_consecutive_losses',0)),'worst_max_consecutive_losses':max_loss,'grade':grade(max_loss),'train_return':tm['total_return'],'validation_return':vm['total_return'],'oos_return':om.get('total_return'),'train_pf':tm['profit_factor'],'validation_pf':vm['profit_factor'],'oos_pf':om.get('profit_factor'),'train_dd':tm['max_drawdown'],'validation_dd':vm['max_drawdown'],'oos_dd':om.get('max_drawdown'),'train_trades':tm['trades'],'validation_trades':vm['trades'],'oos_trades':om.get('trades')}
        rows.append(row)
    rows.sort(key=lambda x:(-x['worst_max_consecutive_losses'],x['model'],x['symbol']))
    by_model=defaultdict(list); by_symbol=defaultdict(list)
    for r in rows: by_model[r['model']].append(r); by_symbol[r['symbol']].append(r)
    summary={'total_sleeves':len(rows),'grades':dict(Counter(r['grade'] for r in rows)),'train_max':max(r['train_max_consecutive_losses'] for r in rows),'validation_max':max(r['validation_max_consecutive_losses'] for r in rows),'oos_max':max(r['oos_max_consecutive_losses'] for r in rows),'overall_max':max(r['worst_max_consecutive_losses'] for r in rows)}
    model_summary=[]
    for m,rs in sorted(by_model.items()):
        model_summary.append({'model':m,'sleeves':len(rs),'max_train':max(x['train_max_consecutive_losses'] for x in rs),'max_validation':max(x['validation_max_consecutive_losses'] for x in rs),'max_oos':max(x['oos_max_consecutive_losses'] for x in rs),'max_any':max(x['worst_max_consecutive_losses'] for x in rs),'grade':grade(max(x['worst_max_consecutive_losses'] for x in rs)),'validation_positive_pf':sum(x['validation_pf']>=1 for x in rs),'oos_positive_pf':sum((x['oos_pf'] or 0)>=1 for x in rs)})
    payload={'phase':'2.4-B','version':'V1.4.0','status':'COMPLETE','purpose':'冻结模型行为/连续亏损审计；不重跑回测，不读取OOS用于选模','source':'D1 freeze manifest + D2 OOS validation report','policy':{'<=10':'合格','11-15':'警戒','16-20':'严重警戒','>=21':'淘汰候选'},'summary':summary,'model_summary':model_summary,'rows':rows}
    (out/'phase2_4_b_model_behavior_audit_v140.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2))
    md=['# Phase 2.4-B V1.4.0 模型行为/连续亏损审计','','## 审计原则','- 本审计不重新回测。','- 不修改冻结参数。','- OOS 只作为独立诊断展示，不参与选模。','- 评价对象是 72 个冻结 Model × Symbol。','- 连续亏损：≤10 合格；11–15 警戒；16–20 严重警戒；≥21 淘汰候选。','',f"## 总体：{summary['total_sleeves']} 个冻结 Sleeve",'',f"- TRAIN 最大连续亏损：{summary['train_max']}",f"- VALIDATION 最大连续亏损：{summary['validation_max']}",f"- OOS 最大连续亏损：{summary['oos_max']}",f"- 三阶段最大值：{summary['overall_max']}",'',f"- 等级分布：{summary['grades']}",'','## 按模型','', '| 模型 | Sleeve | TRAIN最大 | VALID最大 | OOS最大 | 总最大 | 判定 |','|---|---:|---:|---:|---:|---:|---|']
    for x in model_summary: md.append(f"| {x['model']} | {x['sleeves']} | {x['max_train']} | {x['max_validation']} | {x['max_oos']} | {x['max_any']} | **{x['grade']}** |")
    md += ['','## 最严重的 Model × Symbol 样本','','| 模型 | 交易对 | TRAIN | VALIDATION | OOS | 最大值 | 判定 |','|---|---|---:|---:|---:|---:|---|']
    for x in rows[:20]: md.append(f"| {x['model']} | {x['symbol']} | {x['train_max_consecutive_losses']} | {x['validation_max_consecutive_losses']} | {x['oos_max_consecutive_losses']} | {x['worst_max_consecutive_losses']} | **{x['grade']}** |")
    (out/'phase2_4_b_model_behavior_audit_v140.md').write_text('\n'.join(md)+'\n')
    print('PHASE2_4_B_MODEL_BEHAVIOR_AUDIT_V1.4.0_OK')
    print(json.dumps(summary,ensure_ascii=False))
    for x in model_summary: print(x)
if __name__=='__main__': main()
