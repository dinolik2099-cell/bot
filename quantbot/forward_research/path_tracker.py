"""Append-only close-to-close tracking for Forward Shadow signal evidence."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Mapping

from .core import ForwardResearchError, assert_shadow_only
from .observations import HORIZONS, observation


def _utc_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset().total_seconds() != 0:
        raise ForwardResearchError("forward_path_timestamp_not_utc")
    return parsed


@dataclass
class ShadowPathTracker:
    """Tracks only post-signal completed closes; it owns no positions or orders."""
    interval_minutes: int = 1
    pending: dict[str, dict] = field(default_factory=dict)

    def register(self, signal: Mapping) -> bool:
        assert_shadow_only()
        if self.interval_minutes != 1:
            raise ForwardResearchError("forward_path_tracker_interval_not_supported")
        required = ("signal_identity", "symbol", "direction", "reference_price", "signal_timestamp")
        if any(not signal.get(key) for key in required):
            raise ForwardResearchError("forward_path_signal_incomplete")
        signal_id = signal["signal_identity"]
        if signal_id in self.pending:
            return False
        self.pending[signal_id] = {"signal": dict(signal), "opened_at": signal["signal_timestamp"], "prices": []}
        return True

    def on_completed_close(self, *, symbol: str, event_time: str, close: float) -> list[dict]:
        """Add one closed public candle and emit evidence only at the 24h horizon."""
        assert_shadow_only()
        timestamp = _utc_timestamp(event_time)
        completed: list[dict] = []
        for signal_id, state in list(self.pending.items()):
            signal = state["signal"]
            if signal["symbol"] != symbol or timestamp <= _utc_timestamp(signal["signal_timestamp"]):
                continue
            state["prices"].append(float(close))
            # HORIZONS are defined in minutes and the configured input is 1m.
            if len(state["prices"]) >= max(HORIZONS):
                evidence = observation(signal, state["prices"], HORIZONS)
                evidence["completion_timestamp"] = event_time
                evidence["path_status"] = "COMPLETED"
                completed.append(evidence)
                del self.pending[signal_id]
        return completed

    def status(self) -> dict:
        return {"open_observations": len(self.pending), "completed_only": True,
                "oos_allowed": False, "order_placement_allowed": False}
