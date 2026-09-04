from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from quantbot.research.model_registry import (
    model_inventory,
    register_existing_models,
    validate_registry,
)
from quantbot.strategies.model_pool import register_model_pool

OUT = ROOT / "data" / "reports" / "phase2_3_5_model_inventory.json"


def main() -> int:
    register_existing_models()
    register_model_pool()
    validate_registry()
    models = model_inventory()
    categories = {}
    for item in models:
        categories[item["category"]] = categories.get(item["category"], 0) + 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "phase": "2.3.5",
        "version": "1.1",
        "status": "PASS",
        "model_count": len(models),
        "categories": categories,
        "models": models,
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("=" * 72)
    print("QuantBot Phase 2.3.5 模型池预检")
    print("=" * 72)
    print(f"状态:       通过")
    print(f"候选模型数: {len(models)}")
    print(f"分类数:     {len(categories)}")
    print(f"输出:       {OUT}")
    for k, v in sorted(categories.items()):
        print(f"{k}: {v}")
    print("=" * 72)
    print("PHASE2_3_5_MODEL_INVENTORY_V1_1_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
