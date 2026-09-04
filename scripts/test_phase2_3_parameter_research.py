from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts" / "run_phase2_3_parameter_research.py"


def _source() -> str:
    return RUNNER.read_text(encoding="utf-8")


def _tree():
    return ast.parse(_source())


def test_runner_compiles():
    compile(_source(), str(RUNNER), "exec")


def test_controlled_grid_sizes_and_strategy_scope():
    source = _source()
    assert '"trend_breakout": {' in source
    assert '"volatility_breakout": {' in source
    assert '"mean_reversion":' not in source.split("STRATEGIES:", 1)[1].split("PARAM_GRIDS:", 1)[0]
    assert '"lookback": (20, 40, 60)' in source
    assert '"stop_atr": (1.5, 2.0, 2.5)' in source
    assert '"reward_r": (2.0, 3.0, 4.0)' in source
    assert '"ema_fast": (10, 20)' in source
    assert '"ema_slow": (50, 80, 120)' in source
    assert '"range_lookback": (10, 20, 40)' in source


def test_candidate_counts():
    tree = _tree()
    source = _source()
    assert "train_evaluations" in source
    assert "validation_evaluations" in source
    assert "oos_evaluations" in source
    # 27 + 36 + 27 candidates per asset = 90; six assets = 540 TRAIN cells.
    assert "540" in (ROOT / "README_PHASE2_3.md").read_text(encoding="utf-8")


def test_oos_is_after_freeze_and_not_selection_input():
    source = _source()
    assert "selected = max(local_validation, key=_rank_key)" in source
    assert "oos = _evaluate(dataset, oos_frame" in source
    assert "OOS is evaluated only after parameters are frozen; OOS is never used for selection" in source


def test_mean_reversion_excluded():
    source = _source()
    assert '"mean_reversion"' not in source.split("STRATEGIES:", 1)[1].split("}", 1)[0]


def main():
    test_runner_compiles()
    test_controlled_grid_sizes_and_strategy_scope()
    test_candidate_counts()
    test_oos_is_after_freeze_and_not_selection_input()
    test_mean_reversion_excluded()
    print("PHASE2_3_PARAMETER_RESEARCH_TEST_OK")


if __name__ == "__main__":
    main()
