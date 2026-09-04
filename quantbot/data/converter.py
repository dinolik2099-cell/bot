from __future__ import annotations

from pathlib import Path
import pandas as pd

from .load import normalize_kline_frame
from .validator import validate_frame


def convert_symbol_csv_to_parquet(raw_root: str | Path, parquet_root: str | Path,
                                  market: str, symbol: str, interval: str) -> dict:
    src = Path(raw_root) / market / interval / symbol.upper()
    files = sorted(src.glob("*.csv"))
    if not files:
        raise FileNotFoundError(src)

    frames = [normalize_kline_frame(pd.read_csv(f, header=None)) for f in files]
    df = pd.concat(frames).sort_index()
    df = df[~df.index.duplicated(keep="first")]

    report = validate_frame(df, interval)
    out = Path(parquet_root) / market / interval / f"{symbol.upper()}.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)

    if report.ok:
        tmp = out.with_suffix(".parquet.part")
        df.to_parquet(tmp, compression="zstd")
        tmp.replace(out)

    return {
        "market": market, "symbol": symbol.upper(), "interval": interval,
        "output": str(out) if report.ok else None,
        "quality": report.to_dict(),
    }
