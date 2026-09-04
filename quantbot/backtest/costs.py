from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CostModel:
    fee_rate: float = 0.0004
    slippage_bps: float = 2.0
    funding_rate_per_8h: float = 0.0

    @property
    def slippage_rate(self) -> float:
        return self.slippage_bps / 10_000.0

    def execution_price(self, reference_price: float, side: str) -> float:
        if reference_price <= 0:
            raise ValueError("reference_price must be positive")
        if side.lower() == "buy":
            return reference_price * (1.0 + self.slippage_rate)
        if side.lower() == "sell":
            return reference_price * (1.0 - self.slippage_rate)
        raise ValueError("side must be buy or sell")

    def trading_cost(self, notional: float) -> float:
        if notional < 0:
            raise ValueError("notional must be non-negative")
        return notional * self.fee_rate

    def funding_cost(self, notional: float, hours_held: float) -> float:
        if notional < 0 or hours_held < 0:
            raise ValueError("notional and hours_held must be non-negative")
        periods = hours_held / 8.0
        return notional * self.funding_rate_per_8h * periods
