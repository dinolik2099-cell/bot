#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path

from quantbot.research.non_oos_series import (
    NonOOSSeriesError,
    validate_external_n12_anchor,
)

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Read-only audit of externally anchored N12 artifacts."
    )
    parser.add_argument("--diagnostic", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--n11-identity", required=True)
    parser.add_argument("--count", required=True, type=int)
    parser.add_argument("--correlation-sha256", required=True)
    args = parser.parse_args()

    try:
        diagnostic = json.loads(
            Path(args.diagnostic).read_text(encoding="utf-8")
        )
        manifest = json.loads(
            Path(args.manifest).read_text(encoding="utf-8")
        )

        validate_external_n12_anchor(
            diagnostic,
            manifest,
            expected_n11_identity=args.n11_identity,
            expected_candidate_count=args.count,
            actual_correlation_sha256=args.correlation_sha256,
        )
    except (OSError, json.JSONDecodeError, NonOOSSeriesError, ValueError) as exc:
        print(f"N12_EXTERNAL_ANCHOR_AUDIT_REJECTED: {exc}", file=sys.stderr)
        return 1

    print("N12_EXTERNAL_ANCHOR_AUDIT_OK")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
