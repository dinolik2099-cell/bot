"""Retired raw-data research entry point.

This script previously bypassed Boundary Lock and ran the retired legacy
backtest implementation. It remains as an explicit refusal so automated jobs
cannot silently produce incomparable historical results.
"""

from __future__ import annotations


def main() -> None:
    raise SystemExit(
        "run_research.py is retired: it bypassed Boundary Lock and the "
        "Canonical Backtest Engine. Use the boundary-aware Phase 2 research "
        "entry points after their module audit is accepted."
    )


if __name__ == "__main__":
    main()
