"""Optional public websocket transport; no credentials or private endpoints."""
from __future__ import annotations

import json
import time

from .binance_public import websocket_url, parse_kline
from .collector import reconnect_delay
from .core import assert_shadow_only


class PublicWebsocketTransport:
    def __init__(self, symbols, on_event, clock=time.sleep):
        self.symbols = tuple(symbols)
        self.on_event = on_event
        self.clock = clock

    def shard_urls(self, max_per_shard=200):
        from .collector import shard_symbols
        return tuple(websocket_url(shard) for shard in shard_symbols(self.symbols, max_per_shard))

    def run_shard(self, url, connect, receive_time, should_stop=lambda: False):
        """Run one public shard with bounded reconnect/backoff and clean stop."""
        assert_shadow_only()
        attempt = 0
        while not should_stop():
            socket = None
            try:
                socket = connect(url)
                for raw in socket:
                    if should_stop():
                        return
                    self.on_event(parse_kline(json.loads(raw), receive_time()))
                attempt = 0
            except Exception:
                if should_stop():
                    return
                self.clock(reconnect_delay(attempt))
                attempt += 1
            finally:
                if socket is not None:
                    try:
                        socket.close()
                    except Exception:
                        pass
