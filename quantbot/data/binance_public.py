from __future__ import annotations

import hashlib
import io
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


BASE = "https://data.binance.vision"

COLUMNS = [
    "open_time", "open", "high", "low", "close", "volume", "close_time",
    "quote_volume", "trade_count", "taker_buy_volume",
    "taker_buy_quote_volume", "ignore",
]

MARKET_PATHS = {
    "spot": "data/spot/monthly/klines",
    "um": "data/futures/um/monthly/klines",
    "cm": "data/futures/cm/monthly/klines",
}


@dataclass
class DownloadResult:
    status: str
    market: str
    symbol: str
    interval: str
    year: int
    month: int
    path: str | None = None
    http_status: int | None = None
    error: str | None = None
    attempts: int = 0
    bytes_downloaded: int = 0


def monthly_url(market: str, symbol: str, interval: str, year: int, month: int) -> str:
    if market not in MARKET_PATHS:
        raise ValueError(f"Unsupported market: {market}")
    symbol = symbol.upper()
    filename = f"{symbol}-{interval}-{year}-{month:02d}.zip"
    return f"{BASE}/{MARKET_PATHS[market]}/{symbol}/{interval}/{filename}"


def checksum_url(market: str, symbol: str, interval: str, year: int, month: int) -> str:
    return monthly_url(market, symbol, interval, year, month) + ".CHECKSUM"


def _download(url: str, timeout: int, attempts: int, backoff: float) -> tuple[bytes, int, int]:
    last_error = None
    for attempt in range(1, attempts + 1):
        try:
            req = Request(url, headers={"User-Agent": "QuantBot/1.1"})
            with urlopen(req, timeout=timeout) as response:
                return response.read(), int(getattr(response, "status", 200)), attempt
        except HTTPError as exc:
            if exc.code == 404:
                raise
            last_error = exc
        except (URLError, TimeoutError, OSError) as exc:
            last_error = exc
        if attempt < attempts:
            time.sleep(backoff * (2 ** (attempt - 1)))
    raise RuntimeError(f"download failed after {attempts} attempts: {last_error}")


def _verify_zip_bytes(data: bytes) -> str:
    if len(data) < 100:
        raise ValueError("downloaded file is unexpectedly small")
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        bad = zf.testzip()
        if bad is not None:
            raise ValueError(f"corrupt zip member: {bad}")
        csvs = [n for n in zf.namelist() if n.lower().endswith(".csv")]
        if not csvs:
            raise ValueError("zip contains no CSV")
        return csvs[0]


def download_month(
    market: str,
    symbol: str,
    interval: str,
    year: int,
    month: int,
    out_dir: str | Path,
    *,
    timeout: int = 60,
    attempts: int = 4,
    backoff: float = 1.5,
    verify_checksum: bool = False,
) -> DownloadResult:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{symbol.upper()}-{interval}-{year}-{month:02d}.csv"
    if out.exists() and out.stat().st_size > 100:
        return DownloadResult("EXISTS", market, symbol.upper(), interval, year, month, str(out), attempts=0)

    url = monthly_url(market, symbol, interval, year, month)
    try:
        data, status, used_attempts = _download(url, timeout, attempts, backoff)
    except HTTPError as exc:
        if exc.code == 404:
            return DownloadResult("NOT_FOUND", market, symbol.upper(), interval, year, month, http_status=404, error="404")
        return DownloadResult("HTTP_ERROR", market, symbol.upper(), interval, year, month, http_status=exc.code, error=str(exc))
    except Exception as exc:
        return DownloadResult("NETWORK_ERROR", market, symbol.upper(), interval, year, month, error=str(exc), attempts=attempts)

    try:
        csv_name = _verify_zip_bytes(data)
        if verify_checksum:
            checksum_data, _, _ = _download(checksum_url(market, symbol, interval, year, month), timeout, attempts, backoff)
            expected = checksum_data.decode("utf-8", errors="replace").split()[0].strip()
            actual = hashlib.sha256(data).hexdigest()
            if expected and expected != actual:
                raise ValueError(f"SHA256 mismatch: expected {expected}, got {actual}")
        tmp = out.with_suffix(".csv.part")
        with zipfile.ZipFile(io.BytesIO(data)) as zf, zf.open(csv_name) as src, tmp.open("wb") as dst:
            shutil_copy = 1024 * 1024
            while True:
                chunk = src.read(shutil_copy)
                if not chunk:
                    break
                dst.write(chunk)
        if tmp.stat().st_size <= 100:
            tmp.unlink(missing_ok=True)
            raise ValueError("extracted CSV is unexpectedly small")
        tmp.replace(out)
    except Exception as exc:
        out.with_suffix(".csv.part").unlink(missing_ok=True)
        return DownloadResult("CORRUPTED", market, symbol.upper(), interval, year, month, error=str(exc), attempts=used_attempts, bytes_downloaded=len(data))

    return DownloadResult("SUCCESS", market, symbol.upper(), interval, year, month, str(out), http_status=status, attempts=used_attempts, bytes_downloaded=len(data))
