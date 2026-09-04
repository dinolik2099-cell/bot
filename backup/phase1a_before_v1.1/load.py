from __future__ import annotations
from pathlib import Path
import pandas as pd

COLS = [
    "open_time","open","high","low","close","volume","close_time",
    "quote_volume","trade_count","taker_buy_volume","taker_buy_quote_volume","ignore"
]


def load_symbol(root: str | Path, symbol: str, interval: str) -> pd.DataFrame:
    root = Path(root) / interval / symbol
    files = sorted(root.glob("*.csv"))
    if not files:
        raise FileNotFoundError(f"No data: {root}")
    frames = []
    for f in files:
        df = pd.read_csv(f, header=None)
        if df.shape[1] >= 12:
            df = df.iloc[:, :12]
            df.columns = COLS
            frames.append(df)
    if not frames:
        raise ValueError(f"No valid CSV files: {root}")
    df = pd.concat(frames, ignore_index=True)
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    for c in ["open","high","low","close","volume","quote_volume"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["open_time","open","high","low","close"]).drop_duplicates("open_time")
    return df.sort_values("open_time").set_index("open_time")
