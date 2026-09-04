#!/usr/bin/env python3
"""Compatibility launcher for the canonical shared-capital portfolio layer.

Portfolio execution belongs in :mod:`quantbot.portfolio.shared_capital`; this
script stays only for historical CLI and test compatibility.
"""

from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quantbot.portfolio.shared_capital import *  # noqa: F401,F403
from quantbot.portfolio.shared_capital import main


if __name__ == "__main__":
    main()
