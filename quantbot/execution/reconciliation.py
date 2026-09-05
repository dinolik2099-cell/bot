"""Pure reconciliation of expected and observed paper-order state."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Iterable
from .paper_ledger import PaperOrderState

@dataclass(frozen=True)
class ReconciliationReport:
    missing_expected_ids: tuple[str, ...]
    unexpected_observed_ids: tuple[str, ...]
    status_mismatches: tuple[str, ...]

    @property
    def clean(self) -> bool:
        return not (self.missing_expected_ids or self.unexpected_observed_ids or self.status_mismatches)

def reconcile(expected: Iterable[PaperOrderState], observed: Iterable[PaperOrderState]) -> ReconciliationReport:
    """Compare snapshots only; no mutation, persistence, or adapter access."""
    e={x.request.client_order_id:x for x in expected}; o={x.request.client_order_id:x for x in observed}
    return ReconciliationReport(
        tuple(sorted(set(e)-set(o))), tuple(sorted(set(o)-set(e))),
        tuple(sorted(key for key in set(e)&set(o) if e[key].status != o[key].status)),
    )
