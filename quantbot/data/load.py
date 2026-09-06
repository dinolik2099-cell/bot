from __future__ import annotations

from pathlib import Path
import re
import pandas as pd

from .validator import expected_timestamp_unit, validate_frame

COLS = [
    "open_time", "open", "high", "low", "close", "volume", "close_time",
    "quote_volume", "trade_count", "taker_buy_volume",
    "taker_buy_quote_volume", "ignore",
]


def normalize_kline_frame(raw: pd.DataFrame) -> pd.DataFrame:
    if raw.shape[1] < 12:
        raise ValueError(f"Expected >=12 columns, got {raw.shape[1]}")
    df = raw.iloc[:, :12].copy()
    df.columns = COLS

    unit = expected_timestamp_unit(df["open_time"])
    close_unit = expected_timestamp_unit(df["close_time"])
    df["open_time"] = pd.to_datetime(pd.to_numeric(df["open_time"], errors="coerce"), unit=unit, utc=True)
    df["close_time"] = pd.to_datetime(pd.to_numeric(df["close_time"], errors="coerce"), unit=close_unit, utc=True)

    numeric = ["open", "high", "low", "close", "volume", "quote_volume", "trade_count",
               "taker_buy_volume", "taker_buy_quote_volume", "ignore"]
    for col in numeric:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=["open_time", "open", "high", "low", "close"])
    df = df.drop_duplicates("open_time").sort_values("open_time")
    return df.set_index("open_time")


def load_symbol(root: str | Path, symbol: str, interval: str, *, market: str = "spot", validate: bool = True) -> pd.DataFrame:
    root = Path(root) / market / interval / symbol.upper()
    files = sorted(root.glob("*.csv"))
    if not files:
        raise FileNotFoundError(f"No data: {root}")

    frames = [normalize_kline_frame(pd.read_csv(f, header=None)) for f in files]
    df = pd.concat(frames).sort_index()
    df = df[~df.index.duplicated(keep="first")]

    if validate:
        report = validate_frame(df, interval)
        if not report.ok:
            raise ValueError(f"Data quality failed for {market}/{symbol}/{interval}: {report.to_dict()}")
    return df


def load_symbol_window(root: str | Path, symbol: str, interval: str, *, market: str,
                       start, end) -> pd.DataFrame:
    """Read only canonical monthly raw shards overlapping the explicit UTC range.

    This is deliberately separate from ``load_symbol``: N8 must never load an
    entire symbol and slice afterward, because that could physically read OOS
    shards during a non-OOS request.
    """
    start_ts=pd.Timestamp(start);end_ts=pd.Timestamp(end)
    start_ts=start_ts.tz_localize('UTC') if start_ts.tzinfo is None else start_ts.tz_convert('UTC')
    end_ts=end_ts.tz_localize('UTC') if end_ts.tzinfo is None else end_ts.tz_convert('UTC')
    if start_ts>end_ts: raise ValueError('start must be <= end')
    directory=Path(root)/market/interval/symbol.upper()
    files=sorted(directory.glob('*.csv'))
    if not files: raise FileNotFoundError(f'No data: {directory}')
    pattern=re.compile(rf'^{re.escape(symbol.upper())}-{re.escape(interval)}-(\d{{4}})-(\d{{2}})\.csv$')
    selected=[]
    for path in files:
        match=pattern.fullmatch(path.name)
        if match is None: raise ValueError(f'Unrecognized canonical shard name: {path.name}')
        year,month=map(int,match.groups())
        month_start=pd.Timestamp(year=year,month=month,day=1,tz='UTC')
        month_end=(month_start+pd.offsets.MonthBegin(1))-pd.Timedelta(hours=1)
        if month_start<=end_ts and month_end>=start_ts: selected.append(path)
    if not selected: raise FileNotFoundError(f'No canonical shards overlap requested window: {directory}')
    frames=[normalize_kline_frame(pd.read_csv(path,header=None)) for path in selected]
    df=pd.concat(frames).sort_index();df=df[~df.index.duplicated(keep='first')]
    return df.loc[(df.index>=start_ts)&(df.index<=end_ts)].copy()


def save_parquet(df: pd.DataFrame, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".parquet.part")
    df.to_parquet(tmp, index=True, compression="zstd")
    tmp.replace(path)
    return path
