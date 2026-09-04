from __future__ import annotations

import io
import zipfile
from pathlib import Path
from urllib.request import urlopen, Request

BASE = "https://data.binance.vision/data/spot/monthly/klines"

COLUMNS = [
    "open_time","open","high","low","close","volume","close_time",
    "quote_volume","trade_count","taker_buy_volume","taker_buy_quote_volume","ignore"
]


def monthly_url(symbol: str, interval: str, year: int, month: int) -> str:
    fn = f"{symbol}-{interval}-{year}-{month:02d}.zip"
    return f"{BASE}/{interval}/{symbol}/{fn}"


def download_month(symbol: str, interval: str, year: int, month: int, out_dir: str | Path) -> Path | None:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{symbol}-{interval}-{year}-{month:02d}.csv"
    if out.exists() and out.stat().st_size > 100:
        return out
    url = monthly_url(symbol, interval, year, month)
    try:
        req = Request(url, headers={"User-Agent": "QuantBot/1.0"})
        with urlopen(req, timeout=60) as r:
            data = r.read()
    except Exception:
        return None
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            names = z.namelist()
            csv_name = next(n for n in names if n.lower().endswith(".csv"))
            with z.open(csv_name) as src, open(out, "wb") as dst:
                dst.write(src.read())
    except Exception:
        if out.exists():
            out.unlink()
        return None
    return out
