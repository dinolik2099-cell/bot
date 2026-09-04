from __future__ import annotations

import tempfile
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import pandas as pd

from quantbot.data.audit import audit_symbol


def make_csv(path: Path, timestamps):
    rows = []
    for i, ts in enumerate(timestamps):
        ms = int(pd.Timestamp(ts, tz="UTC").timestamp() * 1000)
        close = 100 + i
        rows.append([ms, close, close + 1, close - 1, close, 10, ms + 3599999, 1000, 1, 5, 500, 0])
    pd.DataFrame(rows).to_csv(path, header=False, index=False)


def main():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        d = root / "um" / "1h" / "TESTUSDT"
        d.mkdir(parents=True)

        make_csv(
            d / "part.csv",
            ["2025-01-01 00:00", "2025-01-01 01:00", "2025-01-01 03:00"],
        )
        r = audit_symbol(root, "um", "TESTUSDT", "1h")
        assert r.status == "PARTIAL"
        assert r.gap_count == 1
        assert r.missing_bars == 1
        assert r.rows == 3

        d2 = root / "um" / "1h" / "READYUSDT"
        d2.mkdir(parents=True)
        make_csv(d2 / "part.csv", ["2025-01-01 00:00", "2025-01-01 01:00"])
        r2 = audit_symbol(root, "um", "READYUSDT", "1h")
        assert r2.status == "READY"
        assert r2.gap_count == 0

    print("AUDIT_ENGINE_TEST_OK")


if __name__ == "__main__":
    main()
