"""Deterministic, non-executable portfolio candidate selection."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import pandas as pd

from quantbot.signals import SignalIntent


@dataclass(frozen=True)
class PortfolioCandidate:
    intent: SignalIntent
    selection_rank: int
    selection_reason: str


def select_candidates(intents: Iterable[SignalIntent], *, max_candidates: int) -> tuple[PortfolioCandidate, ...]:
    """Keep at most one opportunity per symbol and model family.

    This is a transparent pre-risk filter. It does not allocate capital, create
    positions, or override the Risk Engine.
    """
    if max_candidates < 1:
        raise ValueError("max_candidates must be positive")
    rows = tuple(intents)
    if not rows:
        return ()
    timestamps = {item.timestamp for item in rows}
    if len(timestamps) != 1:
        raise ValueError("candidate selection requires one decision timestamp")
    ordered = sorted(rows, key=lambda x: (-abs(x.score), -x.confidence, x.model, x.symbol))
    used_symbols: set[str] = set()
    used_families: set[str] = set()
    selected: list[PortfolioCandidate] = []
    for intent in ordered:
        if intent.symbol in used_symbols or intent.model_family in used_families:
            continue
        selected.append(PortfolioCandidate(intent, len(selected) + 1, "highest_score_unique_symbol_and_family"))
        used_symbols.add(intent.symbol)
        used_families.add(intent.model_family)
        if len(selected) == max_candidates:
            break
    return tuple(selected)
