from __future__ import annotations

import argparse
import json
from pathlib import Path

SYMBOLS = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT"]


def main() -> int:
    p = argparse.ArgumentParser(description="合并 Phase 2.3.5-B 六币种预检结果")
    p.add_argument("--input-dir", default="data/reports")
    p.add_argument("--output", default="data/reports/phase2_3_5_real_data_preflight_6symbols.json")
    args = p.parse_args()

    input_dir = Path(args.input_dir)
    reports = []
    missing = []
    for symbol in SYMBOLS:
        path = input_dir / f"phase2_3_5_real_data_preflight_{symbol}.json"
        if not path.exists():
            missing.append(symbol)
            continue
        reports.append(json.loads(path.read_text(encoding="utf-8")))

    results = []
    errors = []
    summaries = {}
    for report in reports:
        symbol = report.get("symbol")
        if symbol not in SYMBOLS:
            errors.append({"symbol": symbol, "model": "<report>", "error": "未知币种报告"})
            continue
        rows = report.get("results", [])
        results.extend(rows)
        summaries[symbol] = report.get("symbol_summary", {})
        errors.extend({"symbol": symbol, **e} for e in report.get("errors", []))

    passed = sum(1 for r in results if r.get("status") == "通过")
    failed = 216 - passed
    for symbol in missing:
        errors.append({"symbol": symbol, "model": "<report>", "error": "缺少该币种预检报告"})

    dataset_ids = {r.get("dataset_id") for r in reports}
    intervals = {r.get("interval") for r in reports}
    windows = {r.get("window") for r in reports}
    if len(dataset_ids) != 1 or len(intervals) != 1 or len(windows) != 1:
        errors.append({"symbol": "<global>", "model": "<report>", "error": "六个子报告的数据集/周期/窗口不一致"})

    report = {
        "status": "通过" if len(reports) == 6 and len(results) == 216 and failed == 0 and not errors else "失败",
        "phase": "2.3.5-B",
        "dataset_id": next(iter(dataset_ids), None),
        "market": reports[0].get("market") if reports else None,
        "interval": next(iter(intervals), None),
        "window": next(iter(windows), None),
        "symbols": SYMBOLS,
        "model_count": 36,
        "expected_cells": 216,
        "completed_cells": len(results),
        "passed": passed,
        "failed": failed,
        "symbol_summary": dict(sorted(summaries.items())),
        "errors": errors,
        "source_reports": [str(input_dir / f"phase2_3_5_real_data_preflight_{s}.json") for s in SYMBOLS],
        "policies": {
            "lookahead": "future_sensitivity + existing pre-T strategy adapter",
            "execution": "T OPEN",
            "cost": "fee 0.04%, slippage 2bps",
            "gaps": "不补K线；缺口时间不存在可交易bar；缺口前后额外做局部执行链预检",
            "oos_used_for_selection": False,
            "parameter_search": False,
            "parameter_selection": False,
            "purpose": "六币种×36模型真实数据接口/因果/执行链预检，不代表正式研究结果",
        },
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=" * 72)
    print("Phase 2.3.5-B 六币种×36模型预检合并结果")
    print("=" * 72)
    print(f"数据集：{report['dataset_id']}")
    print(f"组合：{len(results)}/216")
    print(f"通过：{passed}")
    print(f"失败：{failed}")
    print(f"报告：{output.resolve()}")
    if report["status"] != "通过":
        print("PHASE2_3_5_REAL_DATA_PREFLIGHT_6SYMBOLS_MERGE_FAILED")
        return 1
    print("216个组合全部通过")
    print("PHASE2_3_5_REAL_DATA_PREFLIGHT_6SYMBOLS_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
