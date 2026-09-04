"""Guard that V1.3.2 cannot reintroduce a second execution engine."""

from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]

for name in (
    "run_phase2_4_b_shared_capital_backtest_v132.py",
    "run_phase2_4_b_overnight_torture_v132.py",
):
    completed = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / name)],
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode != 0
    assert "retired" in (completed.stdout + completed.stderr)

print("PHASE2_4_B_V132_RETIREMENT_TEST_OK")
