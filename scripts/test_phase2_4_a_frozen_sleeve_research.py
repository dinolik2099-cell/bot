#!/usr/bin/env python3
"""Unit tests for Phase 2.4-A research boundaries and portfolio math."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/run_phase2_4_a_frozen_sleeve_research.py"
spec = importlib.util.spec_from_file_location("p24a", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def test_portfolio_metrics_independent_call():
    curve = [
        ("2026-01-01T00:00:00+00:00", 10000.0),
        ("2026-01-01T01:00:00+00:00", 10100.0),
    ]
    result = mod.portfolio_metrics(curve, sleeves=2)
    assert result["sleeves"] == 2
    assert abs(result["total_return"] - 0.01) < 1e-12


def main():
    assert len(mod.EXPECTED) == 72
    assert mod.CORR_CAP == 0.70
    assert mod.MIN_TRADES == 20
    assert mod.MAX_DD == 0.35
    assert mod.MIN_PF == 1.0

    freeze = {"phase": "2.3.5-D-1", "dataset_id": "TEST", "records": []}
    for m in mod.MODELS:
        for s in mod.SYMBOLS:
            freeze["records"].append({
                "model": m, "symbol": s, "status": "FROZEN",
                "oos_authorized": True, "params": {}
            })
    mod.validate_freeze(freeze)

    # Sleeve-level combination math: two independent curves, equal weight.
    c1 = [
        ("2026-01-01T00:00:00+00:00", 10000.0),
        ("2026-01-01T01:00:00+00:00", 11000.0),
    ]
    c2 = [
        ("2026-01-01T00:00:00+00:00", 10000.0),
        ("2026-01-01T01:00:00+00:00", 9000.0),
    ]
    pc = mod.portfolio_curve(
        [("m1", "S1"), ("m2", "S2")],
        {("m1", "S1"): c1, ("m2", "S2"): c2},
    )
    assert abs(pc[-1][1] - 10000.0) < 1e-9
    pm = mod.portfolio_metrics(pc, sleeves=2)
    assert abs(pm["total_return"]) < 1e-12
    assert pm["sleeves"] == 2

    # The script must explicitly make the project root available to spawn workers.
    source = SCRIPT.read_text(encoding="utf-8")
    assert "ROOT = Path(__file__).resolve().parents[1]" in source
    assert "if str(ROOT) not in sys.path:" in source

    # Explicitly verify no D-2/D-3/OOS data input or selection logic.
    assert "phase2_3_5_d2" not in source
    assert "phase2_3_5_d3" not in source
    assert '"OOS"' not in source

    print("D-1 72-cell冻结矩阵锁定：通过")
    print("TRAIN/VALIDATION-only边界：通过")
    print("Validation组合等权数学：通过")
    print("portfolio_metrics独立调用：通过")
    print("spawn worker项目根路径：通过")
    print("OOS不读取/不参与组合选择：通过")
    print("PHASE2_4_A_FROZEN_SLEEVE_RESEARCH_TEST_OK")


if __name__ == "__main__":
    main()
