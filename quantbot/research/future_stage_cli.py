"""Shared fail-closed command interface for future non-OOS formal stages."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .authorization import Capability, locked_evidence
from .future_data_plane import FutureRuntimeContext


def _load(path: str):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main_for_stage(stage: str) -> int:
    parser = argparse.ArgumentParser(description=f"QuantBot sealed {stage} TRAIN/VALIDATION stage")
    parser.add_argument("--protocol", required=True, help="sealed future-stage protocol JSON")
    parser.add_argument("--plan", required=True, help="sealed future-stage execution-plan JSON")
    parser.add_argument("--input-identity", required=True)
    parser.add_argument("--execute", action="store_true", help="attempt only with separately approved authority")
    args = parser.parse_args()
    runtime = FutureRuntimeContext(_load(args.protocol), _load(args.plan), args.input_identity)
    runtime.validate()
    if runtime.protocol.get("stage") != stage:
        raise SystemExit("future_stage_cli_stage_mismatch")
    print(f"STAGE={stage}")
    print(f"PROTOCOL_IDENTITY={runtime.protocol['artifact_identity']}")
    print(f"EXECUTION_PLAN_IDENTITY={runtime.plan['artifact_identity']}")
    print(f"CHUNKS={len(runtime.plan['chunks'])}")
    print("OOS_STATUS=SEALED")
    print("OOS_AUTHORIZATION=NOT_AUTHORIZED")
    if not args.execute:
        print("FORMAL_STAGE_NOT_STARTED")
        return 2
    # This is intentionally the last pre-loader guard.  Today's trusted policy
    # supplies locked evidence, so CLI execution cannot accidentally open data.
    capability = Capability.MONTE_CARLO if stage == "monte_carlo" else Capability.TRAIN_VALIDATION
    runtime.authorize(locked_evidence(capability), capability)
    raise SystemExit("future_stage_runtime_dependencies_required")
