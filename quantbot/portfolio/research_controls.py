"""P1 portfolio-research controls; reuse the existing shared-capital engine."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping


@dataclass(frozen=True)
class PortfolioResearchRequest:
    recipe_ids: tuple[str, ...]
    shared_capital_component: str = "quantbot.portfolio.shared_capital.shared_backtest"
    status: str = "BUILT_LOCKED"


def validate_portfolio_request(request: PortfolioResearchRequest, available_recipe_ids: Iterable[str]) -> bool:
    if request.status != "BUILT_LOCKED" or not request.recipe_ids:
        raise ValueError("portfolio_research_not_ready")
    if not set(request.recipe_ids).issubset(set(available_recipe_ids)):
        raise ValueError("portfolio_recipe_not_frozen")
    # Import is intentional proof of reuse, not a second capital allocator.
    from .shared_capital import shared_backtest
    if not callable(shared_backtest):
        raise ValueError("shared_capital_component_unavailable")
    return True


def fixed_weight_vector(scores: Mapping[str, float], *, maximum_weight: float = 0.35) -> dict[str, float]:
    if not scores or not 0 < maximum_weight <= 1:
        raise ValueError("invalid_weight_policy")
    positive = {key: max(0.0, float(value)) for key, value in scores.items()}
    total = sum(positive.values())
    if total == 0:
        return {key: 0.0 for key in sorted(positive)}
    weights = {key: min(maximum_weight, value / total) for key, value in positive.items()}
    return {key: weights[key] for key in sorted(weights)}
