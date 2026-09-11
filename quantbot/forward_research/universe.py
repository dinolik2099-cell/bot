"""Point-in-time public universe refresh and append-only snapshot persistence."""
from __future__ import annotations
from .binance_public import parse_exchange_info,apply_ticker_volumes
from .core import universe_snapshot,assert_shadow_only
def refresh_universe(exchange_info,tickers,timestamp,persistence=None,date=None):
 assert_shadow_only();snapshot=universe_snapshot(apply_ticker_volumes(parse_exchange_info(exchange_info),tickers),timestamp)
 if persistence is not None:
  if not date:raise ValueError('universe_partition_date_required')
  persistence.append('universe',date,snapshot)
 return snapshot
