"""Pure fail-closed execution readiness report."""
from __future__ import annotations
from dataclasses import dataclass
from quantbot.research.provenance import RunProvenance, validate_non_oos_provenance
from quantbot.risk import RiskSnapshot, evaluate_circuit_breaker
from .runtime_config import RuntimeConfig, validate_runtime_config

@dataclass(frozen=True)
class ReadinessReport:
    allowed: bool
    reason: str
    mode: str
    source_window: str

def preflight(config: RuntimeConfig, provenance: RunProvenance, snapshot: RiskSnapshot) -> ReadinessReport:
    """Validate inputs without running Portfolio, Risk sizing, or Paper Ledger."""
    try:
        validate_runtime_config(config)
        validate_non_oos_provenance(provenance)
    except (PermissionError, ValueError) as exc:
        return ReadinessReport(False, str(exc), config.mode, provenance.source_window)
    breaker=evaluate_circuit_breaker(snapshot)
    return ReadinessReport(breaker.allowed, breaker.reason, config.mode, provenance.source_window)
