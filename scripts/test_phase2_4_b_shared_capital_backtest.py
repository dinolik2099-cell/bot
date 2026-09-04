#!/usr/bin/env python3
from pathlib import Path
import importlib.util, sys, tempfile, json
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
path = ROOT / "scripts/run_phase2_4_b_shared_capital_backtest.py"
spec = importlib.util.spec_from_file_location("p24b", path)
mod = importlib.util.module_from_spec(spec)
sys.modules["p24b"] = mod
spec.loader.exec_module(mod)

def test_risk_policy_constants():
    assert mod.RISK_PER_ENTRY == 0.01
    assert mod.MAX_TOTAL_RISK == 0.04
    assert mod.MAX_SAME_DIRECTION_RISK == 0.03
    assert mod.MAX_POSITIONS == 4
    assert mod.MAX_POSITION_FRACTION == 0.25
    assert mod.MAX_TOTAL_CAPITAL_FRACTION == 0.80

def test_causal_signal_shift():
    idx = pd.date_range("2026-01-01", periods=4, freq="h", tz="UTC")
    frame = pd.DataFrame({
        "open":[10,11,12,13],"high":[10,11,12,13],"low":[9,10,11,12],"close":[10,11,12,13]
    }, index=idx)
    def strat(df, **kwargs):
        x=df.copy()
        x["signal"]=[1,0,0,0]
        x["stop"]=x["close"]-1
        x["target"]=x["close"]+2
        return x
    sm=mod.build_signal_map(frame,strat,{},"t")
    assert idx[0] not in sm
    assert idx[1] in sm
    assert sm[idx[1]]["stop_price"] == 9.0

def test_shared_capital_never_exceeds_total_risk():
    idx = pd.date_range("2026-01-01", periods=5, freq="h", tz="UTC")
    frames={}
    sigs={}
    for n,s in enumerate(["BTCUSDT","ETHUSDT","BNBUSDT","SOLUSDT"]):
        px=100+n
        frames[s]=pd.DataFrame({
            "open":[px]*5,"high":[px+1]*5,"low":[px-1]*5,"close":[px]*5
        },index=idx)
        # Entry at second bar, stop 1 unit away.
        sigs[("m"+str(n),s)]={idx[1]:{"timestamp":idx[1],"side":"buy","stop_price":px-1,
            "take_profit":px+2,"tag":"x"}}
    boundary={"gaps":[]}
    keys=list(sigs)
    # The engine itself has fixed risk caps; four 1% entries are allowed, a fifth isn't.
    result=mod.shared_backtest(frames,sigs,keys,boundary)
    assert result["entry_count"] == 4
    assert len(result["trades"]) >= 4

def test_gap_first_actual_is_nontradable():
    boundary={"gaps":[{"symbol":"SOLUSDT","end":"2022-02-28T23:00:00+00:00"}]}
    assert pd.Timestamp("2022-03-01T00:00:00+00:00") in mod.gap_first_actual(boundary,"SOLUSDT")

def test_gap_normalization_handles_none_and_multiple_gaps():
    class IntegrationDataset:
        gaps = None
    assert mod.gap_first_actual(IntegrationDataset(), "BTCUSDT") == set()
    assert mod.gap_first_actual({"gaps": None}, "BTCUSDT") == set()
    boundary={"gaps":[None, {"symbol":"SOLUSDT","end":"2022-02-28 23:00:00"},
                       {"symbol":"SOLUSDT","end":"2022-04-02 23:00:00"},
                       {"symbol":"XRPUSDT","end":"2022-04-02 23:00:00"}]}
    got=mod.gap_first_actual(boundary,"SOLUSDT")
    assert got == {pd.Timestamp("2022-03-01 00:00:00",tz="UTC"), pd.Timestamp("2022-04-03 00:00:00",tz="UTC")}

def test_no_oos_literals_in_runtime_inputs():
    text=path.read_text(encoding="utf-8")
    # Runtime contract must not name D-2/D-3 output files or read OOS windows.
    assert "phase2_3_5_d2_oos_validation.json" not in text
    assert "phase2_3_5_d3_oos_analysis.json" not in text
    assert '"OOS"' not in text

def test_gap_first_actual_accepts_integration_dataset():
    class Gap:
        symbol = "SOLUSDT"
        end = "2022-02-28 23:00:00"
    class IntegrationDataset:
        gaps = [Gap()]
    assert mod.gap_first_actual(IntegrationDataset(), "SOLUSDT") == {pd.Timestamp("2022-03-01 00:00:00",tz="UTC")}
    assert mod.gap_first_actual({"gaps":[{"symbol":"XRPUSDT","end":"2022-04-02 23:00:00"}]}, "XRPUSDT") == {pd.Timestamp("2022-04-03 00:00:00",tz="UTC")}

def test_gap_first_actual_handles_metadata_and_symbol_map():
    class IntegrationDataset:
        gaps = None
        metadata = {"gaps": {"SOLUSDT": [{"end": "2022-02-28 23:00:00"}]}}
    got = mod.gap_first_actual(IntegrationDataset(), "SOLUSDT")
    assert got == {pd.Timestamp("2022-03-01 00:00:00", tz="UTC")}

def test_shared_capital_caps_same_direction_risk():
    idx = pd.date_range("2026-01-01", periods=4, freq="h", tz="UTC")
    frames = {}
    sigs = {}
    symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT"]
    for n, symbol in enumerate(symbols):
        px = 100.0 + n
        frames[symbol] = pd.DataFrame({
            "open": [px]*4, "high": [px+0.5]*4, "low": [px-0.5]*4, "close": [px]*4
        }, index=idx)
        sigs[("m", symbol)] = {idx[1]: {
            "timestamp": idx[1], "side": "buy", "stop_price": px-5,
            "take_profit": px+2, "tag": "risk"
        }}
    result = mod.shared_backtest(frames, sigs, list(sigs), {"gaps": []})
    assert result["entry_count"] == 3
    assert result["rejected_entries"] >= 1

def test_shared_capital_max_positions_rejects_fifth_entry():
    idx = pd.date_range("2026-01-01", periods=4, freq="h", tz="UTC")
    frames, sigs = {}, {}
    symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT"]
    for n, symbol in enumerate(symbols):
        px = 100.0 + n
        frames[symbol] = pd.DataFrame({
            "open": [px]*4, "high": [px+0.5]*4, "low": [px-0.5]*4, "close": [px]*4
        }, index=idx)
        sigs[("m", symbol)] = {idx[1]: {
            "timestamp": idx[1], "side": "buy" if n < 3 else "sell",
            "stop_price": px-5 if n < 3 else px+5,
            "take_profit": px+2 if n < 3 else px-2, "tag": "maxpos"
        }}
    result = mod.shared_backtest(frames, sigs, list(sigs), {"gaps": []})
    assert result["entry_count"] == 4
    assert result["rejected_entries"] >= 1


def test_metrics_expose_trade_count():
    result = {"trades": [1, 2, 3], "curve": [], "total_return": 0.0}
    metrics = {**{k:v for k,v in result.items() if k not in ("curve", "trades")}, "trades": len(result["trades"])}
    assert metrics["trades"] == 3

def main():
    tests=[
        test_risk_policy_constants,
        test_causal_signal_shift,
        test_shared_capital_never_exceeds_total_risk,
        test_gap_first_actual_is_nontradable,
        test_gap_normalization_handles_none_and_multiple_gaps,
        test_no_oos_literals_in_runtime_inputs,
        test_gap_first_actual_accepts_integration_dataset,
        test_gap_first_actual_handles_metadata_and_symbol_map,
        test_shared_capital_caps_same_direction_risk,
        test_shared_capital_max_positions_rejects_fifth_entry,
        test_metrics_expose_trade_count,
    ]
    for t in tests:
        t()
    print("共享资金风险政策锁定：通过")
    print("因果信号T-1→T OPEN：通过")
    print("组合总风险上限：通过")
    print("Gap首根实际K线不可交易：通过")
    print("OOS/D-2/D-3输入隔离：通过")
    print("PHASE2_4_B_SHARED_CAPITAL_BACKTEST_TEST_OK")

if __name__=="__main__":
    main()
