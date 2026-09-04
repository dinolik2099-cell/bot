from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from quantbot.research.model_registry import list_models, register_existing_models, validate_registry
from quantbot.strategies.model_pool import register_model_pool
from scripts.run_phase2_3_5_model_discovery_baseline import _aggregate, SYMBOLS, WINDOWS


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--reports", nargs="+", required=True)
    p.add_argument("--output", default=str(ROOT / "data/reports/phase2_3_5_model_discovery_baseline.json"))
    args = p.parse_args()

    register_existing_models(); register_model_pool(); validate_registry()
    if len(list_models()) != 36:
        raise SystemExit("模型池数量异常，不是36个")

    reports = [json.loads(Path(x).read_text(encoding="utf-8")) for x in args.reports]
    symbols = [r["symbols"][0] for r in reports]
    if set(symbols) != set(SYMBOLS) or len(symbols) != len(SYMBOLS):
        raise SystemExit(f"六币种报告不完整或重复：{symbols}")
    if any(r.get("status") != "PASS" for r in reports):
        raise SystemExit("至少一个币种基线报告失败")

    records = [x for r in reports for x in r["raw_records"]]
    errors = [x for r in reports for x in r.get("errors", [])]
    expected = len(SYMBOLS) * 36 * len(WINDOWS)
    if len(records) != expected or errors:
        raise SystemExit(f"合并数量异常：records={len(records)}, expected={expected}, errors={len(errors)}")

    summary = _aggregate(records)
    gated = [x for x in summary if (
        x["validation_positive_symbols"] >= 3
        and x["validation_pf_ge_1_symbols"] >= 3
        and x["both_train_validation_positive_symbols"] >= 2
        and x["validation_median_pf"] >= 1.0
    )]
    shortlist = gated[:12]

    dataset_ids = {r["dataset_id"] for r in reports}
    if len(dataset_ids) != 1:
        raise SystemExit(f"数据集ID不一致：{sorted(dataset_ids)}")

    report = {
        "phase": "2.3.5-C",
        "version": "1.0",
        "status": "PASS",
        "dataset_id": reports[0]["dataset_id"],
        "market": reports[0]["market"],
        "interval": reports[0]["interval"],
        "symbols": list(SYMBOLS),
        "models": 36,
        "windows": list(WINDOWS),
        "purpose": "36模型×6币种默认参数真实数据基线筛选；不进行参数优化；不读取或使用OOS",
        "parameter_policy": "使用每个策略函数的代码默认参数；参数网格保留到下一阶段",
        "costs": reports[0]["costs"],
        "risk": reports[0]["risk"],
        "counts": {
            "expected_evaluations": expected,
            "completed_evaluations": len(records),
            "errors": len(errors),
            "shortlist_gate_passed": len(gated),
            "shortlist_selected": len(shortlist),
        },
        "screening_gate": reports[0]["screening_gate"],
        "data_sources": {r["symbols"][0]: r["data_sources"][r["symbols"][0]] for r in reports},
        "symbol_reports": {r["symbols"][0]: str(Path(x).resolve()) for r, x in zip(reports, args.reports)},
        "errors": errors,
        "model_summary": summary,
        "shortlist": shortlist,
        "raw_records": records,
    }
    out = Path(args.output); out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    print("=" * 72)
    print("Phase 2.3.5-C 六币种模型池真实数据基线筛选")
    print("=" * 72)
    print("状态：通过")
    print(f"数据集：{report['dataset_id']}")
    print("模型：36")
    print("币种：6")
    print("窗口：TRAIN + VALIDATION（不读取 OOS）")
    print(f"评估：{len(records)}/{expected}")
    print(f"错误：{len(errors)}")
    print(f"通过筛选门槛：{len(gated)}")
    print(f"进入下一阶段：{len(shortlist)}")
    print("-" * 72)
    for i, x in enumerate(shortlist, 1):
        print(f"{i:02d}. {x['model']:28s}  验证正收益 {x['validation_positive_symbols']}/6  PF≥1 {x['validation_pf_ge_1_symbols']}/6  中位PF {x['validation_median_pf']:.3f}  中位收益 {x['validation_median_return']:+.2%}  中位DD {x['validation_median_drawdown']:.2%}")
    print("-" * 72)
    print(f"报告：{out}")
    print("PHASE2_3_5_MODEL_DISCOVERY_BASELINE_6SYMBOLS_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
