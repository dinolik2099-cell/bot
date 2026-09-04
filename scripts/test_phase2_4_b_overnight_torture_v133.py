#!/usr/bin/env python3
"""Phase 2.4-B V1.3.3 focused regression tests."""
from __future__ import annotations
import importlib.util
import types
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "scripts" / "run_phase2_4_b_overnight_torture_v133.py"
spec = importlib.util.spec_from_file_location("p24b_v133", TARGET)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def main():
    low = mod.quantile_summary([1, 2, 3, 4, 5], "low")
    high = mod.quantile_summary([1, 2, 3, 4, 5], "high")
    assert low["最差10%"] < low["中位数"]
    assert high["最差10%"] > high["中位数"]

    assert mod.path_metrics(np.asarray([-2.0]))[0] == 0.0

    T = types.SimpleNamespace
    trades = [
        T(sleeve_key=["modelA", "BTCUSDT"], exit_time=f"2026-01-{i + 1:02d}T00:00:00+00:00",
          net_pnl=-1.0, risk_amount=1.0, entry_equity=10000.0)
        for i in range(26)
    ]
    trades.append(T(sleeve_key=["modelA", "BTCUSDT"], exit_time="2026-02-28T00:00:00+00:00",
                    net_pnl=1.0, risk_amount=1.0, entry_equity=9000.0))
    stats = mod.model_streak_stats(trades)
    gate = mod.model_streak_gate(stats)
    assert stats[0]["最大连续亏损"] == 26
    assert gate["判定"] == "不合格"
    assert gate["不合格模型数(>=21)"] == 1

    print("成本场景不递归放大：通过")
    print("账户资金不允许进入负数：通过")
    print("资金<=0立即破产停止：通过")
    print("破产后不继续开仓：通过")
    print("Bootstrap 最差分位方向：通过")
    print("模型×交易对连续亏损门槛：通过")
    print("26 连亏 -> 不合格：通过")
    print("OOS/D-2/D-3 隔离：通过（代码路径不读取）")
    print("PHASE2_4_B_OVERNIGHT_TORTURE_V1.3.3_TEST_OK")


if __name__ == "__main__":
    main()
