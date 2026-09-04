from __future__ import annotations
import argparse, itertools, json, os, sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from quantbot.data.load import load_symbol
from quantbot.strategies.models import trend_breakout, trend_pullback, volatility_breakout, mean_reversion
from quantbot.backtest.engine import backtest, metrics

MODEL_FUNCS = {
    "trend_breakout": trend_breakout,
    "trend_pullback": trend_pullback,
    "volatility_breakout": volatility_breakout,
    "mean_reversion": mean_reversion,
}

def grid(d):
    keys, vals = list(d.keys()), list(d.values())
    return [dict(zip(keys, x)) for x in itertools.product(*vals)]

def task(t):
    cfg = t["cfg"]; symbol=t["symbol"]; name=t["model"]; params=t["params"]
    try:
        df = load_symbol(ROOT/"data/raw", symbol, cfg["project"]["base_interval"])
        fn = MODEL_FUNCS[name]
        sig = fn(df, **params)
        c, trades, halted = backtest(df, sig, initial=cfg["project"]["initial_capital"],
            risk_pct=t["risk_pct"], max_position_pct=t["max_position_pct"],
            fee_rate=cfg["costs"]["fee_rate"], slippage_bps=cfg["costs"]["slippage_bps"],
            max_drawdown_stop=cfg["risk"]["max_drawdown_stop"])
        m=metrics(c,trades,cfg["project"]["initial_capital"])
        m.update({"symbol":symbol,"model":name,"risk_pct":t["risk_pct"],"max_position_pct":t["max_position_pct"],"params":json.dumps(params,sort_keys=True),"halted":halted})
        return m
    except Exception as e:
        return {"symbol":symbol,"model":name,"error":repr(e),"risk_pct":t["risk_pct"],"max_position_pct":t["max_position_pct"]}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--config",default=str(ROOT/"config/research.yaml")); a=ap.parse_args()
    cfg=yaml.safe_load(open(a.config,encoding="utf-8"))
    tasks=[]
    for name, spec in cfg["strategies"].items():
        if not spec.get("enabled",True): continue
        param_spec={k:v for k,v in spec.items() if isinstance(v,list)}
        for symbol in cfg["universe"]["symbols"]:
            for params in grid(param_spec):
                for rp in cfg["risk"]["risk_per_trade"]:
                    for mp in cfg["risk"]["max_position_pct"]:
                        tasks.append({"cfg":cfg,"symbol":symbol,"model":name,"params":params,"risk_pct":rp,"max_position_pct":mp})
    workers=cfg["research"].get("workers") or max(1,(os.cpu_count() or 2)-2)
    print(f"tasks={len(tasks)} workers={workers}",flush=True)
    out=ROOT/"reports"; out.mkdir(exist_ok=True)
    results=[]
    with ProcessPoolExecutor(max_workers=workers) as ex:
        futs=[ex.submit(task,t) for t in tasks]
        for n,f in enumerate(as_completed(futs),1):
            results.append(f.result())
            if n%100==0: print(f"completed={n}/{len(tasks)}",flush=True)
    df=pd.DataFrame(results)
    df.to_csv(out/"research_results.csv",index=False)
    df.to_json(out/"research_results.json",orient="records",force_ascii=False,indent=2)
    print(f"saved {len(df)} results -> {out}")

if __name__ == "__main__": main()
