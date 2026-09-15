"""Installable-template source for target-only Forward steady-state checks."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release", required=True)
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--target-commit", required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from forward_preflight import validate_watchdog
    value = validate_watchdog(release_root=args.release, checkpoint_path=args.checkpoint,
                              target_commit=args.target_commit)
    print(json.dumps({"FORWARD_RELEASE_WATCHDOG_OK": True, **value}, sort_keys=True))
    return 0


if __name__ == "__main__": raise SystemExit(main())
