"""Isolated Binance Futures Demo execution consumer.

This package never imports or mutates Forward runtime components.  It consumes
already persisted Forward signal evidence read-only and is hard fenced away
from live trading endpoints.
"""

DEMO_ENVIRONMENT = "DEMO"
LIVE_ORDER_ENDPOINT_ALLOWED = False
