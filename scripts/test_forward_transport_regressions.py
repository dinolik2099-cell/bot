from quantbot.forward_research.binance_public import parse_kline
from quantbot.forward_research.path_tracker import _utc_timestamp
from quantbot.forward_research.service_runtime import build_service


payload = {
    "data": {
        "e": "kline",
        "s": "BTCUSDT",
        "k": {
            "i": "1m",
            "t": 1789294140000,
            "o": "100",
            "h": "101",
            "l": "99",
            "c": "100.5",
            "v": "10",
            "x": True,
            "f": 1000,
            "L": 1010,
        },
    }
}

event = parse_kline(payload, "2026-09-13T10:10:00+00:00")
assert event.event_time == "2026-09-13T10:09:00+00:00"
assert _utc_timestamp(event.event_time).isoformat() == event.event_time
assert event.sequence == 1010
assert event.closed is True
print("FORWARD_EVENT_TIME_NORMALIZATION=PASS")


class Collector:
    def __init__(self):
        self.errors = {}
        self.reconnects = 0

    def record_error(self, source, exc):
        self.errors[source] = str(exc)
        self.reconnects += 1


class Runtime:
    def __init__(self):
        self.errors = 0
        self.reconnects = 0


class Orchestrator:
    def __init__(self):
        self.collector = Collector()
        self.runtime = Runtime()

    def ingest(self, event, date):
        return "INTRABAR"

    def checkpoint(self, path):
        return None


orchestrator = Orchestrator()

service = build_service(
    config_path="config/forward_research.yaml",
    symbols=["BTCUSDT"],
    orchestrator=orchestrator,
    date_provider=lambda value: value[:10],
)

service["transport"].on_error(
    "websocket_shard",
    RuntimeError("synthetic_transport_failure"),
)

assert orchestrator.collector.reconnects == 1
assert orchestrator.runtime.errors == 1
assert orchestrator.runtime.reconnects == 1
assert "websocket_shard" in orchestrator.collector.errors

print("FORWARD_TRANSPORT_ERROR_OBSERVABILITY=PASS")
print("FORWARD_TRANSPORT_REGRESSIONS=PASS")
