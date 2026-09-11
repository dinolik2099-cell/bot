"""Completed-candle-only Forward Shadow pipeline.

This module is intentionally an event router, not a research runner: it uses
pre-validated declarations and persists observation evidence only.
"""
from __future__ import annotations

from typing import Mapping, Sequence

from .core import ForwardResearchError, assert_shadow_only
from .frozen_declarations import validate_forward_declarations


class ForwardPipeline:
    def __init__(self, *, orchestrator, plan: Mapping, declarations: Sequence[Mapping]):
        assert_shadow_only()
        self.orchestrator = orchestrator
        self.plan = dict(plan)
        self.declarations = validate_forward_declarations(self.plan, declarations)
        self.by_model = {row["model_id"]: row for row in self.declarations}

    def on_completed_candle(self, *, date: str, symbol: str, interval: str) -> dict:
        """Run declared models only after the collector has committed a closed candle."""
        assert_shadow_only()
        if interval != self.plan.get("protocol_scope", {}).get("timeframe"):
            raise ForwardResearchError("forward_pipeline_interval_not_frozen")
        rows = self.orchestrator.candles.history(symbol, interval)
        if not rows or not all(row.get("closed") for row in rows):
            raise ForwardResearchError("forward_pipeline_completed_history_required")
        result = self.orchestrator.run_completed_models(date, symbol, interval, self.declarations)
        # Signal persistence occurs in the orchestrator.  No positions, orders,
        # formal scores, validation, or OOS path is introduced here.
        return {**result, "symbol": symbol, "interval": interval,
                "research_freeze_identity": self.plan["research_freeze_identity"],
                "research_plan_identity": self.plan["research_plan_identity"],
                "forward_research_only": True}
