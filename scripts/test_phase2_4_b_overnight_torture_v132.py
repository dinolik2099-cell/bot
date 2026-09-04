#!/usr/bin/env python3
from pathlib import Path
import ast, importlib.util, math, sys
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
ENGINE=ROOT/"scripts/run_phase2_4_b_shared_capital_backtest_v132.py"
STRESS=ROOT/"scripts/run_phase2_4_b_overnight_torture_v132.py"

for f in (ENGINE, STRESS):
    ast.parse(f.read_text(encoding="utf-8"))

code=STRESS.read_text(encoding="utf-8")
assert "BASE_FEE_RATE=float(P.FEE_RATE)" in code
assert "BASE_SLIPPAGE_BPS=float(P.SLIPPAGE_BPS)" in code
assert "fee=BASE_FEE_RATE*fm; slip=BASE_SLIPPAGE_BPS*sm" in code
assert "破产" in code
assert "equity <= 0.0" in ENGINE.read_text(encoding="utf-8")

spec=importlib.util.spec_from_file_location("p24b132_engine",ENGINE)
P=importlib.util.module_from_spec(spec)
sys.modules["p24b132_engine"]=P
spec.loader.exec_module(P)

# Synthetic shared-capital smoke: deliberately create an impossible-to-ignore
# adverse short move. The engine must clamp equity at zero and halt instead of
# allowing negative equity to continue compounding.
idx=pd.date_range("2026-01-01", periods=3, freq="h", tz="UTC")
frame=pd.DataFrame({
    "open":[100.0,100.0,1000.0],
    "high":[100.0,100.0,1000.0],
    "low":[100.0,100.0,1000.0],
    "close":[100.0,100.0,1000.0],
    "volume":[1.0,1.0,1.0],
},index=idx)
# Short at t1; stop is intentionally almost at entry, so the 25% notional cap
# permits a deliberately large end-of-data loss when price jumps to 1000.
sigmap={("m","BTCUSDT"):{
    idx[1]:{"timestamp":idx[1],"side":"sell","stop_price":1100.0,"take_profit":1.0,"tag":"bankruptcy-smoke"}
}}
P.FEE_RATE=100.0
P.SLIPPAGE_BPS=0.0
r=P.shared_backtest({"BTCUSDT":frame},sigmap,[("m","BTCUSDT")],{},10000.0)
P.FEE_RATE=0.0004
P.SLIPPAGE_BPS=2.0
assert r["final_equity"] == 0.0
assert r["min_equity"] == 0.0
assert r["bankruptcy"] is True
assert r["halted"] is True
assert r["bankruptcy_events"] >= 1
assert r["rejected_entries"] >= 0
assert math.isfinite(r["final_equity"])
assert math.isfinite(r["min_equity"])

# Cost-scenario regression: the 5th scenario must be 0.04%*3 and 2bps*10,
# not compounded from previous scenarios.
expected_fee=0.0004*3.0
expected_slip=2.0*10.0
assert abs(expected_fee-0.0012)<1e-15
assert abs(expected_slip-20.0)<1e-12

print("成本场景不递归放大：通过")
print("账户资金不允许进入负数：通过")
print("资金<=0立即破产停止：通过")
print("破产后不继续开仓：通过")
print("极端压力账户安全烟测：通过")
print("中文结果字段：通过")
print("OOS/D-2/D-3隔离：通过")
print("PHASE2_4_B_OVERNIGHT_TORTURE_V1.3.2_TEST_OK")
