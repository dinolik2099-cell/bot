from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from quantbot.data.binance_public import download_month


def months(start: str, end: str):
    sy, sm = map(int, start.split("-")); ey, em = map(int, end.split("-"))
    y, m = sy, sm
    while (y, m) <= (ey, em):
        yield y, m
        m += 1
        if m == 13: y, m = y + 1, 1

p = argparse.ArgumentParser()
p.add_argument("--symbols", nargs="+", required=True)
p.add_argument("--interval", default="1h")
p.add_argument("--start", default="2021-01")
p.add_argument("--end", default=f"{date.today().year}-{date.today().month:02d}")
p.add_argument("--out", default=str(ROOT / "data/raw"))
a = p.parse_args()

for s in a.symbols:
    for y, m in months(a.start, a.end):
        path = download_month(s, a.interval, y, m, Path(a.out) / a.interval / s)
        print(f"{s} {y}-{m:02d}: {'OK ' + str(path) if path else 'NOT_FOUND'}", flush=True)
