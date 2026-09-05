"""One-shot, in-memory paper decision orchestration; never polls or sends orders."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Iterable, Mapping
from quantbot.analytics import DecisionAuditTrail, correlation_id
from quantbot.backtest import CostModel
from quantbot.execution.paper import build_paper_order
from quantbot.execution.paper_ledger import PaperLedger
from quantbot.execution.runtime_config import RuntimeConfig, validate_runtime_config
from quantbot.portfolio import select_candidates
from quantbot.risk import PositionExposure, RiskPolicy, approve_candidate, size_approved_candidate
from quantbot.signals import SignalIntent
from quantbot.research.provenance import RunProvenance, validate_non_oos_provenance

@dataclass(frozen=True)
class PaperRuntimeResult:
    requested_order_ids: tuple[str, ...]
    rejected: tuple[tuple[str, str], ...]
    audit: DecisionAuditTrail
    ledger: PaperLedger

def run_once(intents: Iterable[SignalIntent], prices: Mapping[str, float], equity: float, provenance: RunProvenance, positions: Iterable[PositionExposure] = (), policy: RiskPolicy = RiskPolicy(), cost_model: CostModel = CostModel(), runtime_config: RuntimeConfig = RuntimeConfig()) -> PaperRuntimeResult:
    """Explicit inputs only; returns in-memory objects and has no side effects."""
    validate_runtime_config(runtime_config)
    validate_non_oos_provenance(provenance)
    trail=DecisionAuditTrail(); ledger=PaperLedger(); rejected=[]; requested=[]
    candidates=select_candidates(intents,max_candidates=policy.max_positions)
    for candidate in candidates:
        key=correlation_id(candidate.intent.symbol,candidate.intent.model,candidate.intent.timestamp.isoformat())
        trail.append("signal_created",key); trail.append("portfolio_selected",key)
        price=prices.get(candidate.intent.symbol)
        if price is None:
            trail.append("risk_rejected",key,{"reason":"missing_reference_price"}); rejected.append((key,"missing_reference_price")); continue
        decision=approve_candidate(candidate,reference_price=float(price),equity=equity,positions=positions,policy=policy)
        if not decision.accepted:
            trail.append("risk_rejected",key,{"reason":decision.reason}); rejected.append((key,decision.reason)); continue
        trail.append("risk_approved",key,{"risk_amount":decision.risk_amount})
        order=build_paper_order(size_approved_candidate(candidate,decision,reference_price=float(price),cost_model=cost_model))
        ledger.request(order); trail.append("paper_requested",key,{"client_order_id":order.client_order_id}); requested.append(order.client_order_id)
    return PaperRuntimeResult(tuple(requested),tuple(rejected),trail,ledger)
