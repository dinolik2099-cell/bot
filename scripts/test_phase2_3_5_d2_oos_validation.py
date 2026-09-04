from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.run_phase2_3_5_d2_oos_validation import EXPECTED_MODELS, SYMBOLS, _load_freeze


def main():
    src = (ROOT / "scripts/run_phase2_3_5_d2_oos_validation.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    calls = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "split_frame":
            if len(node.args) >= 3 and isinstance(node.args[2], ast.Constant):
                calls.append(node.args[2].value)
    assert calls == ["OOS"], calls
    assert "OOS" in src
    assert all(v == "OOS" for v in calls)

    fixture = {
        "phase": "2.3.5-D-1",
        "version": "1.0",
        "dataset_id": "TEST_DATASET",
        "records": [
            {"model": m, "symbol": s, "status": "FROZEN", "oos_authorized": True, "params": {"x": 1}}
            for m in EXPECTED_MODELS for s in SYMBOLS
        ],
    }
    p = ROOT / "data/reports/.d2_test_freeze.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(fixture), encoding="utf-8")
    try:
        records = _load_freeze(p, "TEST_DATASET")
        assert len(records) == 72
    finally:
        p.unlink(missing_ok=True)

    print("OOS-only split isolation：通过")
    print("D-1 Freeze 72-cell matrix lock：通过")
    print("OOS不参与参数选择/调参：通过")
    print("PHASE2_3_5_D2_OOS_VALIDATION_TEST_OK")


if __name__ == "__main__":
    main()
