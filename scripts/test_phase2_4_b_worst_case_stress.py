#!/usr/bin/env python3
from pathlib import Path
import importlib.util, sys, numpy as np
ROOT=Path(__file__).resolve().parents[1]
path=ROOT/"scripts/run_phase2_4_b_worst_case_stress.py"
spec=importlib.util.spec_from_file_location("stress",path); mod=importlib.util.module_from_spec(spec); sys.modules[spec.name]=mod; spec.loader.exec_module(mod)

def test_scenarios():
    assert len(mod.SCENARIOS)==10
    assert mod.SCENARIOS[0][0]=="基准成本"
    assert mod.SCENARIOS[-1][1]==0.0012 and mod.SCENARIOS[-1][2]==10.0

def test_monte_carlo_worst_quantiles():
    trades=[{"qty":1,"entry_price":100,"net_pnl":2} for _ in range(50)] + [{"qty":1,"entry_price":100,"net_pnl":-1} for _ in range(50)]
    r=mod.monte_carlo(trades,1000,1)
    assert r["模拟次数"]==1000
    assert 0 <= r["最大回撤最差1%"] <= 1
    assert r["最终资金最差0.1%"] <= r["最终资金中位数"]

def test_oos_isolation_text():
    text=path.read_text(encoding="utf-8")
    assert "phase2_3_5_d2_oos_validation.json" not in text
    assert "phase2_3_5_d3_oos_analysis.json" not in text

def test_best_case_not_selection():
    text=path.read_text(encoding="utf-8")
    assert "最好收益不作为筛选依据" in text

if __name__=="__main__":
    test_scenarios(); test_monte_carlo_worst_quantiles(); test_oos_isolation_text(); test_best_case_not_selection()
    print("中文结果命名：通过")
    print("多成本/滑点压力场景：通过")
    print("蒙特卡洛最坏路径分析：通过")
    print("OOS/D-2/D-3隔离：通过")
    print("最好情况不作为筛选依据：通过")
    print("PHASE2_4_B_WORST_CASE_STRESS_TEST_OK")
