"""One-shot, in-memory paper decision orchestration; never polls or sends orders."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Iterable, Mapping
from quantbot.analytics import DecisionAuditTrail, correlation_id
from quantbot.backtest import CostModel
from quantbot.execution.paper import build_paper_order
from quantbot.execution.paper_ledger import PaperLedger
from quantbot.execution.runtime_config import RuntimeConfig
from quantbot.execution.preflight import preflight
from quantbot.portfolio import select_candidates
from quantbot.risk import PositionExposure, RiskPolicy, RiskSnapshot, emergency_stop_from_breaker, evaluate_circuit_breaker, approve_candidate, exposure_from_plan, size_approved_candidate
from quantbot.signals import SignalIntent
from quantbot.research.provenance import RunProvenance

@dataclass(frozen=True)
class PaperRuntimeResult:
    requested_order_ids: tuple[str, ...]
    rejected: tuple[tuple[str, str], ...]
    audit: DecisionAuditTrail
    ledger: PaperLedger
    new_exposures: tuple[PositionExposure, ...] = ()

def run_once(intents: Iterable[SignalIntent], prices: Mapping[str, float], equity: float, provenance: RunProvenance, risk_snapshot: RiskSnapshot, positions: Iterable[PositionExposure] = (), policy: RiskPolicy = RiskPolicy(), cost_model: CostModel = CostModel(), runtime_config: RuntimeConfig = RuntimeConfig()) -> PaperRuntimeResult:
    """Explicit inputs only; returns in-memory objects and has no side effects."""
    readiness = preflight(runtime_config, provenance, risk_snapshot)
    if not readiness.allowed and readiness.reason not in {"invalid_equity_snapshot", "max_daily_loss", "max_rolling_loss", "max_drawdown", "max_consecutive_losses"}:
        raise PermissionError(readiness.reason)
    trail=DecisionAuditTrail(); ledger=PaperLedger(); rejected=[]; requested=[]; new_exposures=[]
    provenance_payload = {
        "dataset_id": provenance.dataset_id,
        "research_version": provenance.research_version,
        "source_window": provenance.source_window,
        "engine_version": provenance.engine_version,
        "oos_read": provenance.oos_read,
    }
    breaker = evaluate_circuit_breaker(risk_snapshot)
    if not breaker.allowed:
        stop = emergency_stop_from_breaker(breaker, risk_snapshot)
        key = correlation_id("runtime", provenance.dataset_id, provenance.research_version)
        trail.append("signal_created", key, {"provenance": provenance_payload})
        trail.append("portfolio_selected", key, {"runtime_control": True})
        trail.append("risk_rejected", key, {"reason": breaker.reason, "circuit_breaker": True, "emergency_stop": stop.active, "equity": stop.equity})
        return PaperRuntimeResult((), ((key, breaker.reason),), trail, ledger, ())
    candidates=select_candidates(intents,max_candidates=policy.max_positions)
    for candidate in candidates:
        key=correlation_id(candidate.intent.symbol,candidate.intent.model,candidate.intent.timestamp.isoformat())
        trail.append("signal_created",key,{"provenance": provenance_payload}); trail.append("portfolio_selected",key)
        price=prices.get(candidate.intent.symbol)
        if price is None:
            trail.append("risk_rejected",key,{"reason":"missing_reference_price"}); rejected.append((key,"missing_reference_price")); continue
        decision=approve_candidate(candidate,reference_price=float(price),equity=equity,positions=positions,policy=policy)
        if not decision.accepted:
            trail.append("risk_rejected",key,{"reason":decision.reason}); rejected.append((key,decision.reason)); continue
        trail.append("risk_approved",key,{"risk_amount":decision.risk_amount})
        plan=size_approved_candidate(candidate,decision,reference_price=float(price),cost_model=cost_model)
        order=build_paper_order(plan); new_exposures.append(exposure_from_plan(plan))
        ledger.request(order); trail.append("paper_requested",key,{"client_order_id":order.client_order_id}); requested.append(order.client_order_id)
    return PaperRuntimeResult(tuple(requested),tuple(rejected),trail,ledger,tuple(new_exposures))
