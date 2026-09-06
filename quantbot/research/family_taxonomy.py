"""Controlled, model-family taxonomy for candidate metadata."""
from __future__ import annotations

CANONICAL_FAMILIES = frozenset({
    "trend", "momentum", "breakout", "mean_reversion", "volatility",
    "volume", "price_structure", "candlestick",
})

CANONICAL_SECONDARY_TRAITS = frozenset({
    "breakout", "momentum", "pullback", "retest", "reversal", "compression",
    "expansion", "regime", "ema", "macd", "range", "volume_confirmation",
})


def validate_taxonomy(family: str, secondary_traits: tuple[str, ...]) -> None:
    if family not in CANONICAL_FAMILIES:
        raise ValueError(f"unknown canonical family: {family}")
    if len(secondary_traits) != len(set(secondary_traits)):
        raise ValueError("duplicate secondary trait")
    unknown = set(secondary_traits) - CANONICAL_SECONDARY_TRAITS
    if unknown:
        raise ValueError(f"unknown secondary traits: {sorted(unknown)}")
