from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from quantbot.research.splits import build_splits
from quantbot.research.manifest import build_research_manifest, write_json


def main():
    p = argparse.ArgumentParser(description="Build an immutable research manifest from Dataset Audit output.")
    p.add_argument("--audit", default=str(ROOT / "data/reports/dataset_audit.jsonl"))
    p.add_argument("--symbols", nargs="+", required=True)
    p.add_argument("--interval", required=True)
    p.add_argument("--train-end", default="2024-12-31T23:59:59Z")
    p.add_argument("--validation-end", default="2025-12-31T23:59:59Z")
    p.add_argument("--oos-end", default="2026-08-31T23:59:59Z")
    p.add_argument("--dataset-start", default="2021-01-01T00:00:00Z")
    p.add_argument("--output", default=str(ROOT / "data/reports/research_manifest.json"))

    args = p.parse_args()

    splits = build_splits(args.train_end, args.validation_end, args.oos_end, args.dataset_start)
    manifest = build_research_manifest(
        args.audit,
        args.symbols,
        args.interval,
        [s.describe() for s in splits],
    )
    out = write_json(manifest, args.output)
    print(f"RESEARCH_MANIFEST_OK: {out}")
    print(f"splits={len(splits)} datasets={len(manifest['datasets'])}")


if __name__ == "__main__":
    raise SystemExit(main())
