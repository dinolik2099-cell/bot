#!/usr/bin/env python3
"""Phase 2.4-B: true shared-capital portfolio/risk backtest.

Research contract:
- Inputs: D-1 frozen Model×Symbol parameters + Phase 2.4-A Validation portfolio recipes.
- Windows: TRAIN and VALIDATION only.
- OOS/D-2/D-3 outputs are never read.
- Frozen model parameters are never modified.
- Multiple symbols/sleeves share one portfolio equity account.
- One live position per symbol; a symbol cannot consume two sleeves at once.
- Entries execute at the current actual candle OPEN.
- New entry cannot hit its own SL/TP on the entry candle.
- Later OHLC: STOP wins if both stop and target are touched.
- Missing candles are never synthesized; the first actual candle after a gap is non-tradable.
- End-of-data positions close at the final actual close.

This stage compares fixed portfolio recipes under a fixed shared-capital risk policy.
It does not authorize OOS. A later stage must freeze the portfolio recipe before OOS.
"""
from __future__ import annotations
import argparse, json, math, multiprocessing as mp, sys
from numbers import Integral
from dataclasses import dataclass
from pathlib import Path
from collections import defaultdict

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_LOCK = ROOT / "data/reports/research_boundary_lock.json"
DEFAULT_FREEZE = ROOT / "data/reports/phase2_3_5_d1_freeze_manifest.json"
DEFAULT_RECIPE = ROOT / "data/reports/phase2_4_a_frozen_sleeve_research.json"
DEFAULT_OUT = ROOT / "data/reports/phase2_4_b_shared_capital_backtest.json"
DEFAULT_CURVES = ROOT / "data/reports/phase2_4_b_portfolio_equity_curves.jsonl"
DEFAULT_TRADES = ROOT / "data/reports/phase2_4_b_portfolio_trades.jsonl"
SYMBOLS = ["BTCUSDT","ETHUSDT","BNBUSDT","SOLUSDT","XRPUSDT","DOGEUSDT"]
MODELS = [
    "price_ema_momentum","rsi_momentum","roc_momentum","higher_high_lower_low",
    "volume_trend","bollinger_breakout","ema_slope","donchian_breakout",
    "volume_breakout","volatility_regime_trend","trend_breakout","macd_trend",
]
EXPECTED = {(m,s) for m in MODELS for s in SYMBOLS}

# Predeclared portfolio risk policy for this stage.
INITIAL_EQUITY = 10000.0
RISK_PER_ENTRY = 0.01
MAX_TOTAL_RISK = 0.04
MAX_SAME_DIRECTION_RISK = 0.03
MAX_POSITIONS = 4
MAX_POSITION_FRACTION = 0.25
MAX_TOTAL_CAPITAL_FRACTION = 0.80
FEE_RATE = 0.0004
SLIPPAGE_BPS = 2.0
FUNDING_RATE_PER_8H = 0.0

@dataclass
class Position:
    symbol: str
    side: str
    qty: float
    entry_price: float
    entry_reference: float
    entry_time: pd.Timestamp
    entry_bar_index: int
    stop_price: float
    take_profit: float | None
    tag: str
    entry_fee: float
    risk_amount: float
    sleeve_key: tuple[str,str]
    entry_equity: float = 0.0
    risk_fraction: float = 0.0

@dataclass
class Trade:
    symbol: str
    side: str
    entry_time: str
    exit_time: str
    qty: float
    entry_price: float
    exit_price: float
    gross_pnl: float
    fees: float
    slippage_cost: float
    net_pnl: float
    exit_reason: str
    tag: str
    sleeve_key: list[str]
    entry_equity: float = 0.0
    risk_amount: float = 0.0
    risk_fraction: float = 0.0

def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))

def utc(v):
    t = pd.Timestamp(v)
    return t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")

def register_all_models():
    from quantbot.research.model_registry import list_models, register_existing_models
    if not list_models():
        register_existing_models()
        from quantbot.strategies.model_pool import register_model_pool
        register_model_pool()

def gap_first_actual(boundary, symbol):
    """Return a set of first-actual timestamps after every locked gap for symbol.

    Boundary representations may expose ``gaps`` directly, via ``metadata``,
    or as None. Individual gap records may also have None values. Returning a
    set makes membership checks safe for both zero-gap and multi-gap symbols.
    """
    if isinstance(boundary, dict):
        gaps = boundary.get("gaps")
        if gaps is None:
            metadata = boundary.get("metadata")
            gaps = metadata.get("gaps") if isinstance(metadata, dict) else []
    else:
        gaps = getattr(boundary, "gaps", None)
        if gaps is None:
            metadata = getattr(boundary, "metadata", None)
            gaps = metadata.get("gaps", []) if isinstance(metadata, dict) else []
    if gaps is None:
        return set()
    symbol_mapped = False
    if isinstance(gaps, dict) and symbol in gaps:
        gaps = gaps.get(symbol, []) or []
        symbol_mapped = True
    elif isinstance(gaps, dict):
        gaps = [gaps]
    result = set()
    for g in gaps:
        if g is None:
            continue
        if isinstance(g, dict):
            gs = symbol if symbol_mapped else g.get("symbol")
            end = g.get("end") or g.get("gap_end")
            if end is None and gs is None and symbol in g:
                value = g.get(symbol)
                if isinstance(value, dict):
                    end = value.get("end") or value.get("gap_end")
                    gs = symbol
        else:
            gs = getattr(g, "symbol", None)
            end = getattr(g, "end", None) or getattr(g, "gap_end", None)
        if gs == symbol and end is not None:
            result.add(utc(end) + pd.Timedelta(hours=1))
    return result

def validate_freeze(freeze, dataset_id):
    if freeze.get("phase") != "2.3.5-D-1":
        raise ValueError("freeze phase must be 2.3.5-D-1")
    recs = freeze.get("records", [])
    if len(recs) != 72:
        raise ValueError(f"freeze must contain 72 records, got {len(recs)}")
    keys = {(r.get("model"),r.get("symbol")) for r in recs}
    if keys != EXPECTED:
        raise ValueError("freeze is not the locked 12x6 matrix")
    if any(r.get("status") != "FROZEN" or not r.get("oos_authorized") for r in recs):
        raise ValueError("all freeze records must be FROZEN and OOS-authorized")
    if freeze.get("dataset_id") != dataset_id:
        raise ValueError("freeze dataset_id mismatch")

def validate_recipes(recipe_doc, dataset_id):
    if recipe_doc.get("phase") != "2.4-A":
        raise ValueError("recipe report must be Phase 2.4-A")
    if recipe_doc.get("dataset_id") != dataset_id:
        raise ValueError("recipe dataset_id mismatch")
    if recipe_doc.get("research_contract", {}).get("oos_read") is not False:
        raise ValueError("Phase 2.4-A recipe contract must declare OOS read=false")
    recipes = recipe_doc.get("portfolio_candidates", [])
    names = {p.get("name") for p in recipes}
    required = {"P24A_TOP8_VALIDATION","P24A_DIVERSIFIED_8","P24A_DIVERSIFIED_12"}
    if not required.issubset(names):
        raise ValueError("Phase 2.4-A must contain TOP8, DIVERSIFIED_8 and DIVERSIFIED_12 recipes")
    for p in recipes:
        keys = {tuple(x) for x in p.get("sleeves", [])}
        if p["name"] in required:
            if not keys or not keys.issubset(EXPECTED):
                raise ValueError(f"invalid sleeves in {p['name']}")
    return [p for p in recipes if p["name"] in sorted(required)]

def load_symbol_frame(symbol, lock_path, raw_root, parquet_root):
    from quantbot.research.integration import load_boundary_lock
    from quantbot.research.runner import build_research_dataset, load_research_frames
    boundary = load_boundary_lock(lock_path)
    dataset = build_research_dataset(lock_path)
    frames, sources = load_research_frames(dataset, raw_root, parquet_root, [symbol])
    return boundary, dataset, frames[symbol], sources[symbol]

def split_by_window(dataset, full, window):
    from quantbot.research.runner import split_frame
    return split_frame(dataset, full, window)

def build_signal_map(frame, strategy, params, tag):
    """Causal signal map: strategy row T-1 becomes an entry signal at T OPEN."""
    evaluated = strategy(frame.copy(), **dict(params))
    if not isinstance(evaluated, pd.DataFrame) or len(evaluated) != len(frame):
        raise ValueError("strategy output must be same-length DataFrame")
    required = {"signal","stop","target"}
    if not required.issubset(evaluated.columns):
        raise ValueError("strategy output missing signal/stop/target")
    out = {}
    idx = frame.index
    for i in range(1, len(idx)):
        row = evaluated.iloc[i-1]
        side = int(row["signal"])
        if side == 0:
            continue
        if side not in (-1,1):
            raise ValueError(f"invalid signal {side}")
        stop = None if pd.isna(row["stop"]) else float(row["stop"])
        target = None if pd.isna(row["target"]) else float(row["target"])
        if stop is None:
            continue
        ts = idx[i]
        out[ts] = {
            "timestamp": ts, "side": "buy" if side == 1 else "sell",
            "stop_price": stop, "take_profit": target, "tag": tag
        }
    return out

def execution_price(reference, side):
    # Positive slippage against the trader.
    factor = 1.0 + SLIPPAGE_BPS / 10000.0
    return reference * factor if side == "buy" else reference / factor

def fee(notional):
    return abs(notional) * FEE_RATE

def mark_equity(cash_equity, positions, current):
    mtm = float(cash_equity)
    for pos in positions.values():
        bar = current.get(pos.symbol)
        if bar is None:
            continue
        close = float(bar["close"])
        unreal = ((close-pos.entry_price)*pos.qty if pos.side=="buy"
                  else (pos.entry_price-close)*pos.qty)
        mtm += unreal - pos.entry_fee
    return mtm

def close_position(pos, ts, reference_price, reason):
    exit_side = "sell" if pos.side == "buy" else "buy"
    exit_price = execution_price(reference_price, exit_side)
    gross = ((exit_price-pos.entry_price)*pos.qty if pos.side=="buy"
             else (pos.entry_price-exit_price)*pos.qty)
    exit_fee = fee(pos.qty * exit_price)
    slippage_cost = abs(exit_price-reference_price)*pos.qty
    return Trade(
        symbol=pos.symbol, side=pos.side, entry_time=pos.entry_time.isoformat(),
        exit_time=utc(ts).isoformat(), qty=pos.qty, entry_price=pos.entry_price,
        exit_price=exit_price, gross_pnl=gross, fees=pos.entry_fee+exit_fee,
        slippage_cost=slippage_cost, net_pnl=gross-pos.entry_fee-exit_fee,
        exit_reason=reason, tag=pos.tag, sleeve_key=list(pos.sleeve_key),
        entry_equity=float(pos.entry_equity), risk_amount=float(pos.risk_amount),
        risk_fraction=float(pos.risk_fraction)
    )

def shared_backtest(frames, signal_maps, recipe_keys, boundary, initial=INITIAL_EQUITY):
    timeline = sorted(set().union(*(set(df.index) for df in frames.values())))
    if not timeline:
        raise ValueError("empty portfolio timeline")
    gaps = {s: gap_first_actual(boundary, s) for s in frames}
    # Deterministic recipe order; no hidden score sorting inside B.
    recipe_keys = [tuple(k) for k in recipe_keys]
    positions = {}
    equity = float(initial)
    trades = []
    rejected = 0
    skipped_gap = 0
    curve = []
    entry_count = 0

    for ts in timeline:
        current = {s: df.loc[ts] for s,df in frames.items() if ts in df.index}

        # 1) Existing SL/TP checks first.
        for symbol, pos in list(positions.items()):
            bar = current.get(symbol)
            if bar is None:
                continue
            df = frames[symbol]
            i = df.index.get_loc(ts)
            if not isinstance(i, Integral) or int(i) <= pos.entry_bar_index:
                continue
            if pos.side == "buy":
                stop_hit = float(bar["low"]) <= pos.stop_price
                target_hit = pos.take_profit is not None and float(bar["high"]) >= pos.take_profit
            else:
                stop_hit = float(bar["high"]) >= pos.stop_price
                target_hit = pos.take_profit is not None and float(bar["low"]) <= pos.take_profit
            if stop_hit or target_hit:
                reason = "stop" if stop_hit else "take_profit"
                ref = pos.stop_price if stop_hit else pos.take_profit
                tr = close_position(pos, ts, float(ref), reason)
                equity += tr.net_pnl
                trades.append(tr)
                del positions[symbol]

        # 2) Entries. One sleeve per symbol; recipe order is deterministic.
        for model, symbol in recipe_keys:
            if ts not in frames[symbol].index:
                continue
            if symbol in positions:
                continue
            if ts in gaps.get(symbol,set()):
                skipped_gap += 1
                continue
            sig = signal_maps[(model,symbol)].get(ts)
            if sig is None:
                continue
            if len(positions) >= MAX_POSITIONS:
                rejected += 1
                continue

            # Portfolio risk accounting uses intended stop distance and current equity.
            ref = float(frames[symbol].loc[ts]["open"])
            stop = float(sig["stop_price"])
            risk_per_unit = abs(ref-stop)
            if risk_per_unit <= 0 or not np.isfinite(risk_per_unit):
                rejected += 1
                continue
            risk_budget = equity * RISK_PER_ENTRY
            used_risk = sum(p.risk_amount for p in positions.values())
            direction_risk = sum(p.risk_amount for p in positions.values() if p.side == sig["side"])
            if used_risk + risk_budget > equity * MAX_TOTAL_RISK + 1e-12:
                rejected += 1
                continue
            if direction_risk + risk_budget > equity * MAX_SAME_DIRECTION_RISK + 1e-12:
                rejected += 1
                continue

            entry_price = execution_price(ref, sig["side"])
            qty_risk = risk_budget / risk_per_unit
            qty_notional = equity * MAX_POSITION_FRACTION / entry_price
            qty = min(qty_risk, qty_notional)
            if qty <= 0 or not np.isfinite(qty):
                rejected += 1
                continue
            notional = qty * entry_price
            existing_notional = sum(p.qty*p.entry_price for p in positions.values())
            if existing_notional + notional > equity * MAX_TOTAL_CAPITAL_FRACTION + 1e-9:
                allowed = max(0.0, equity*MAX_TOTAL_CAPITAL_FRACTION-existing_notional)
                qty = min(qty, allowed/entry_price)
                notional = qty*entry_price
            if qty <= 0:
                rejected += 1
                continue

            entry_fee = fee(notional)
            risk_amount = risk_per_unit * qty
            positions[symbol] = Position(
                symbol=symbol, side=sig["side"], qty=qty,
                entry_price=entry_price, entry_reference=ref, entry_time=ts,
                entry_bar_index=frames[symbol].index.get_loc(ts),
                stop_price=stop, take_profit=sig["take_profit"], tag=sig["tag"],
                entry_fee=entry_fee, risk_amount=risk_amount,
                sleeve_key=(model,symbol), entry_equity=float(equity),
                risk_fraction=float(risk_amount/equity) if equity else 0.0
            )
            entry_count += 1

        curve.append((utc(ts), mark_equity(equity, positions, current)))

    # Close all remaining positions at each symbol's final actual close.
    for symbol, pos in list(positions.items()):
        df = frames[symbol]
        ts = utc(df.index[-1])
        ref = float(df.iloc[-1]["close"])
        tr = close_position(pos, ts, ref, "end_of_data")
        equity += tr.net_pnl
        trades.append(tr)
        del positions[symbol]

    curve.append((utc(timeline[-1]), equity))
    vals = np.asarray([v for _,v in curve],dtype=float)
    peak=np.maximum.accumulate(vals)
    dd=np.abs(np.min(vals/peak-1.0)) if len(vals) else 0.0
    net=[t.net_pnl for t in trades]
    wins=[x for x in net if x>0]; losses=[-x for x in net if x<0]
    pf=sum(wins)/sum(losses) if losses else math.inf
    return {
        "initial": initial, "final_equity": float(equity),
        "total_return": float(equity/initial-1.0),
        "max_drawdown": float(dd), "trades": len(trades),
        "win_rate": len(wins)/len(net) if net else 0.0,
        "profit_factor": float(pf), "rejected_entries": rejected,
        "skipped_gap_entries": skipped_gap, "entry_count": entry_count,
        "curve": [(ts.isoformat(),float(v)) for ts,v in curve],
        "trades": trades,
    }

def worker(payload):
    if str(ROOT) not in sys.path:
        sys.path.insert(0,str(ROOT))
    symbol, freeze_records, lock_path, raw_root, parquet_root, recipe_keys = payload
    from quantbot.research.model_registry import get_model
    register_all_models()
    boundary, dataset, full, source = load_symbol_frame(symbol, lock_path, raw_root, parquet_root)
    local = {}
    for window in ("TRAIN","VALIDATION"):
        frame = split_by_window(dataset, full, window)
        local[window] = {"frame": frame, "source": source, "signals": {}}
        by_model = {r["model"]:r for r in freeze_records}
        for model in sorted({m for m,s in recipe_keys if s==symbol}):
            rec = by_model[model]
            spec = get_model(model)
            local[window]["signals"][(model,symbol)] = build_signal_map(
                frame, spec.strategy, rec["params"], f"P24B:{model}:{symbol}:{window}"
            )
    return symbol, boundary, dataset.boundary.dataset_id, local

def dataset_id_of(dataset):
    return getattr(dataset,"dataset_id",None) or dataset.get("dataset_id")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--lock",default=str(DEFAULT_LOCK))
    ap.add_argument("--freeze",default=str(DEFAULT_FREEZE))
    ap.add_argument("--recipe",default=str(DEFAULT_RECIPE))
    ap.add_argument("--raw-root",default=str(ROOT/"data/raw"))
    ap.add_argument("--parquet-root",default=str(ROOT/"data/parquet"))
    ap.add_argument("--workers",type=int,default=6)
    ap.add_argument("--output",default=str(DEFAULT_OUT))
    ap.add_argument("--curves-output",default=str(DEFAULT_CURVES))
    ap.add_argument("--trades-output",default=str(DEFAULT_TRADES))
    args=ap.parse_args()

    lock=load_json(args.lock)
    dataset_id=lock.get("dataset_id")
    freeze=load_json(args.freeze); validate_freeze(freeze,dataset_id)
    recipe_doc=load_json(args.recipe); recipes=validate_recipes(recipe_doc,dataset_id)
    by_symbol=defaultdict(list)
    for r in freeze["records"]:
        by_symbol[r["symbol"]].append(r)

    recipe_keys_all=[]
    for p in recipes:
        for x in p["sleeves"]:
            recipe_keys_all.append((p["name"],tuple(x)))
    # Only freeze-recipe Model×Symbol keys are used.
    all_keys=sorted({k for _,k in recipe_keys_all})
    payloads=[(s,by_symbol[s],args.lock,args.raw_root,args.parquet_root,all_keys) for s in SYMBOLS]
    ctx=mp.get_context("spawn")
    with ctx.Pool(processes=max(1,min(args.workers,len(SYMBOLS)))) as pool:
        chunks=pool.map(worker,payloads)

    boundaries=[x[1] for x in chunks]
    locals_by_symbol={x[0]:x[3] for x in chunks}
    if len(locals_by_symbol)!=6:
        raise RuntimeError("expected six symbol workers")

    # Run every A recipe on TRAIN and VALIDATION using one shared account.
    outputs=[]
    for recipe in recipes:
        keys=[tuple(x) for x in recipe["sleeves"]]
        for window in ("TRAIN","VALIDATION"):
            frames={s:locals_by_symbol[s][window]["frame"] for s in {k[1] for k in keys}}
            sigs={}
            for k in keys:
                sigs[k]=locals_by_symbol[k[1]][window]["signals"][k]
            result=shared_backtest(frames,sigs,keys,boundaries[0],INITIAL_EQUITY)
            outputs.append({
                "recipe":recipe["name"], "window":window,
                "sleeves":[list(k) for k in keys],
                "risk_policy":{
                    "initial_equity":INITIAL_EQUITY,"risk_per_entry":RISK_PER_ENTRY,
                    "max_total_risk":MAX_TOTAL_RISK,"max_same_direction_risk":MAX_SAME_DIRECTION_RISK,
                    "max_positions":MAX_POSITIONS,"max_position_fraction":MAX_POSITION_FRACTION,
                    "max_total_capital_fraction":MAX_TOTAL_CAPITAL_FRACTION,
                    "fee_rate":FEE_RATE,"slippage_bps":SLIPPAGE_BPS
                },
                "metrics":{**{k:v for k,v in result.items() if k not in ("curve","trades")}, "trades": len(result["trades"])},
                "curve":result["curve"], "trades":result["trades"]
            })

    if len(outputs)!=6:
        raise RuntimeError("expected 6 recipe/window results")

    # Persist compact audit files.
    cp=Path(args.curves_output); cp.parent.mkdir(parents=True,exist_ok=True)
    with cp.open("w",encoding="utf-8") as f:
        for o in outputs:
            for ts,eq in o["curve"]:
                f.write(json.dumps({"recipe":o["recipe"],"window":o["window"],"timestamp":ts,"equity":eq},ensure_ascii=False)+"\n")
    tp=Path(args.trades_output)
    with tp.open("w",encoding="utf-8") as f:
        for o in outputs:
            for t in o["trades"]:
                f.write(json.dumps({
                    "recipe":o["recipe"],"window":o["window"],"symbol":t.symbol,
                    "side":t.side,"entry_time":t.entry_time,"exit_time":t.exit_time,
                    "qty":t.qty,"entry_price":t.entry_price,"exit_price":t.exit_price,
                    "gross_pnl":t.gross_pnl,"fees":t.fees,"slippage_cost":t.slippage_cost,
                    "net_pnl":t.net_pnl,"exit_reason":t.exit_reason,"tag":t.tag,
                    "sleeve_key":t.sleeve_key,"entry_equity":t.entry_equity,
                    "risk_amount":t.risk_amount,"risk_fraction":t.risk_fraction,
                    "return_on_entry_equity":(t.net_pnl/t.entry_equity if t.entry_equity else 0.0)
                },ensure_ascii=False)+"\n")

    summary={}
    for o in outputs:
        summary.setdefault(o["recipe"],{})[o["window"]]=o["metrics"]
    out={
        "phase":"2.4-B","version":"1.0.3-audit","status":"PASS","dataset_id":dataset_id,
        "purpose":"冻结Sleeve组合的真实共享资金多仓/风险引擎回测；仅TRAIN/VALIDATION。",
        "inputs":{"freeze_manifest":args.freeze,"phase2_4_a_recipe_report":args.recipe,"boundary_lock":args.lock},
        "research_contract":{
            "windows":["TRAIN","VALIDATION"],"oos_read":False,
            "parameters_modified":False,"d1_freeze_modified":False,
            "recipe_source":"Phase 2.4-A Validation recipes; this stage compares them under shared capital.",
            "execution":"entries at current OPEN; entry candle cannot trigger new SL/TP; STOP wins tie; EOD close",
            "gap_policy":"no synthetic candles; first actual bar after configured gap is non-tradable"
        },
        "risk_policy":{
            "initial_equity":INITIAL_EQUITY,"risk_per_entry":RISK_PER_ENTRY,
            "max_total_risk":MAX_TOTAL_RISK,"max_same_direction_risk":MAX_SAME_DIRECTION_RISK,
            "max_positions":MAX_POSITIONS,"max_position_fraction":MAX_POSITION_FRACTION,
            "max_total_capital_fraction":MAX_TOTAL_CAPITAL_FRACTION,
            "fee_rate":FEE_RATE,"slippage_bps":SLIPPAGE_BPS,"funding_rate_per_8h":FUNDING_RATE_PER_8H,
            "one_position_per_symbol":True
        },
        "counts":{"recipes":len(recipes),"recipe_window_runs":len(outputs),"frozen_sleeves":72},
        "results":outputs,
        "summary":summary,
        "next_stage":"Freeze one portfolio recipe and its risk policy using predeclared Validation rules; then run one OOS portfolio validation. Do not tune from OOS."
    }
    op=Path(args.output); op.parent.mkdir(parents=True,exist_ok=True)
    # Don't include raw duplicate curves/trades in main JSON.
    compact=dict(out)
    compact["results"]=[]
    for o in outputs:
        compact["results"].append({k:v for k,v in o.items() if k not in ("curve","trades")})
    op.write_text(json.dumps(compact,ensure_ascii=False,indent=2,default=str),encoding="utf-8")
    md=op.with_name("phase2_4_b_summary.md")
    lines=["# Phase 2.4-B 共享资金Portfolio回测","","状态：通过","",
           "## 固定风险政策","","- 单笔风险：1%","- 组合总风险上限：4%",
           "- 同方向风险上限：3%","- 最大同时持仓：4","- 单仓最大名义占比：25%",
           "- 总资金使用上限：80%","- 每个币最多1个Sleeve持仓","- Fee：0.04%","- Slippage：2bps",
           "","## 结果","","|Recipe|Window|Return|Max DD|PF|Trades|Rejected|",
           "|---|---|---:|---:|---:|---:|---:|"]
    for o in outputs:
        m=o["metrics"]
        lines.append(f"|{o['recipe']}|{o['window']}|{m['total_return']:+.2%}|{m['max_drawdown']:.2%}|{m['profit_factor']:.3f}|{m.get('trades', m.get('entry_count', 0))}|{m['rejected_entries']}|")
    lines += ["","**纪律：本阶段完全不读取D-2/D-3/OOS；参数不修改。2.4-A配方仍需在组合层冻结后，才能授权下一次OOS。**"]
    md.write_text("\n".join(lines)+"\n",encoding="utf-8")

    print("="*72); print("Phase 2.4-B 共享资金Portfolio回测"); print("="*72)
    print("状态：通过")
    print(f"Recipe×Window：{len(outputs)}/6")
    for o in outputs:
        m=o["metrics"]
        print(f"{o['recipe']} / {o['window']}：Return={m['total_return']:+.2%}，DD={m['max_drawdown']:.2%}，PF={m['profit_factor']:.3f}，Trades={m.get('trades', m.get('entry_count', 0))}")
    print(f"报告：{op}"); print(f"曲线：{cp}"); print(f"交易：{tp}"); print(f"总结：{md}")
    print("PHASE2_4_B_SHARED_CAPITAL_BACKTEST_OK")

if __name__=="__main__":
    main()
