from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from quantbot.research.boundary import lock_boundaries


def main():
    rows = [
        {
            "market": "um",
            "symbol": "AAAUSDT",
            "interval": "1h",
            "first_timestamp": "2021-01-01T00:00:00+00:00",
            "last_timestamp": "2026-07-31T23:00:00+00:00",
            "gaps": [],
        },
        {
            "market": "um",
            "symbol": "BBBUSDT",
            "interval": "1h",
            "first_timestamp": "2021-01-01T00:00:00+00:00",
            "last_timestamp": "2026-07-31T23:00:00+00:00",
            "gaps": [{"previous": "2022-02-25T23:00:00+00:00",
                      "next": "2022-03-01T00:00:00+00:00",
                      "missing_bars": 72}],
        },
    ]

    lock = lock_boundaries(
        rows, "TEST_1H", "1h",
        "2024-12-31T23:59:59Z",
        "2025-12-31T23:59:59Z",
        "2026-08-31T23:59:59Z",
    )

    assert lock.status == "LOCKED"
    assert lock.actual_end == "2026-07-31T23:00:00+00:00"
    assert lock.splits[0].end == "2024-12-31T23:00:00+00:00"
    assert lock.splits[1].start == "2025-01-01T00:00:00+00:00"
    assert lock.splits[1].end == "2025-12-31T23:00:00+00:00"
    assert lock.splits[2].start == "2026-01-01T00:00:00+00:00"
    assert lock.splits[2].end == "2026-07-31T23:00:00+00:00"
    assert len(lock.gaps) == 1
    assert lock.gaps[0]["missing_bars"] == 72

    print("BOUNDARY_LOCK_TEST_OK")


if __name__ == "__main__":
    main()
