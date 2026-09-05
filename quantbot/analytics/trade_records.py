"""Immutable research records and transparent failure summaries for completed trades."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable, Mapping


@dataclass(frozen=True)
class TradeRecord:
    """A research/audit record. It never changes execution outcomes."""
    symbol: str
    model: str
    model_family: str
    entry_time: str
    exit_time: str
    side: str
    entry_price: float
    stop_price: float | None
    take_profit: float | None
    exit_price: float
    exit_reason: str
    gross_pnl: float
    net_pnl: float
    fees: float
    slippage_cost: float
    quantity: float
    holding_seconds: float | None
    r_multiple: float | None
    regime: str | None = None
    volatility: float | None = None
    trend_strength: float | None = None
    volume_state: str | None = None
    signal_score: float | None = None
    metadata: Mapping[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def summarize_failures(records: Iterable[TradeRecord]) -> dict[str, Any]:
    """Describe losses; do not rank models or alter selection decisions."""
    rows = tuple(records)
    losses = tuple(row for row in rows if row.net_pnl < 0)
    by_reason: dict[str, int] = {}
    by_regime: dict[str, int] = {}
    for row in losses:
        by_reason[row.exit_reason] = by_reason.get(row.exit_reason, 0) + 1
        key = row.regime or "unclassified"
        by_regime[key] = by_regime.get(key, 0) + 1
    return {
        "record_count": len(rows), "loss_count": len(losses),
        "loss_rate": len(losses) / len(rows) if rows else 0.0,
        "net_pnl": sum(row.net_pnl for row in rows),
        "loss_net_pnl": sum(row.net_pnl for row in losses),
        "losses_by_exit_reason": dict(sorted(by_reason.items())),
        "losses_by_regime": dict(sorted(by_regime.items())),
        "note": "Descriptive failure analysis only; no model ranking or execution decision is made here.",
    }
