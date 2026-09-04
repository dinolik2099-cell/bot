from __future__ import annotations
import itertools, json, sys
from pathlib import Path
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from quantbot.research.model_registry import register_existing_models, list_models, validate_registry
from quantbot.strategies.model_pool import register_model_pool
from scripts.run_phase2_3_5_d1_parameter_research import _grid, _score, _stability, TOP_K_TRAIN

def frame(n=800):
    idx=pd.date_range("2024-01-01",periods=n,freq="1h",tz="UTC"); t=np.arange(n,dtype=float)
    c=100+0.03*t+2*np.sin(t/17)+0.5*np.sin(t/31); o=c+0.1*np.sin(t/7)
    h=np.maximum(o,c)+0.5; l=np.minimum(o,c)-0.5; v=1000+50*np.sin(t/13)
    return pd.DataFrame({"open":o,"high":h,"low":l,"close":c,"volume":v},index=idx)

def main():
    register_existing_models(); register_model_pool(); validate_registry(); models=list(list_models())
    assert len(models)==36 and len({m.spec.name for m in models})==36
    names={"price_ema_momentum","rsi_momentum","roc_momentum","higher_high_lower_low","volume_trend","bollinger_breakout","ema_slope","donchian_breakout","volume_breakout","volatility_regime_trend","trend_breakout","macd_trend"}
    assert len(names)==12
    counts={m.spec.name:len(_grid(m.spec)) for m in models if m.spec.name in names}
    assert sum(counts.values())==786, counts
    # Deterministic ranking and stability on synthetic result records.
    spec=next(m.spec for m in models if m.spec.name=="price_ema_momentum")
    grid=_grid(spec); results=[]
    for i,p in enumerate(grid): results.append({"params":p,"score":float(i),"metrics":{"total_return":float(i),"max_drawdown":0.0}})
    results.sort(key=lambda x:x["score"],reverse=True)
    s=_stability(results,results[0],spec)
    assert len(results)>=TOP_K_TRAIN and s["neighbor_count"]>0
    assert isinstance(_score({"total_return":1.2,"max_drawdown":0.3}),float)
    # Frozen stability diagnostics must describe the VALIDATION-selected candidate, not TRAIN rank #1.
    runner_source=(ROOT/"scripts/run_phase2_3_5_d1_parameter_research.py").read_text(encoding="utf-8")
    assert "selected = validation_results[0]" in runner_source
    assert "stability = _stability(train_results, selected, item.spec) if top else {}" in runner_source
    assert "stability = _stability(train_results, top[0], item.spec) if top else {}" not in runner_source
    # D-1 formal research must use the canonical engine path and Boundary Lock gaps.
    assert "from quantbot.backtest.engine_v2 import BacktestEngine" in runner_source
    assert "from quantbot.backtest.costs import CostModel" in runner_source
    assert "from quantbot.research.evaluation import evaluate_strategy" in runner_source
    assert "gap_indices={symbol: _gap_indices(dataset, symbol)}" in runner_source
    assert "_fast_backtest(" not in runner_source
    assert '"--allow-subset"' in runner_source
    assert "and not args.allow_subset" in runner_source
    assert "if not symbols:" in runner_source
    assert "issubset(set(SYMBOLS))" in runner_source
    # Every candidate grid tuple is unique.
    assert len({_key['params'].__repr__() for _key in results})==len(results)
    # C report provenance exists and contains exactly the locked 12.
    c=json.loads((ROOT/"data/reports/phase2_3_5_model_discovery_baseline.json").read_text())
    assert c["status"]=="PASS" and [x["model"] for x in c["shortlist"]]==["price_ema_momentum","rsi_momentum","roc_momentum","higher_high_lower_low","volume_trend","bollinger_breakout","ema_slope","donchian_breakout","volume_breakout","volatility_regime_trend","trend_breakout","macd_trend"]
    print("12模型与786参数组合计数：通过")
    print("Top-K与参数稳定性诊断：通过")
    print("C阶段shortlist来源锁定：通过")
    print("PHASE2_3_5_D1_PARAMETER_RESEARCH_TEST_OK")
if __name__=="__main__": main()
