"""N12 deterministic, non-OOS diagnostic summaries over supplied artifacts."""
from __future__ import annotations

from collections import Counter, defaultdict
import math
from dataclasses import dataclass, asdict
from typing import Mapping, Sequence
from .artifact_store import seal, validate_seal
from .result_package import (
    SCHEMA_VERSION as N11_V1_SCHEMA_VERSION,
    EVIDENCE_SCHEMA_VERSION as N11_V2_SCHEMA_VERSION,
    validate_result_package,
    validate_evidence_package,
)

def _validate_supported_n11_package(package: Mapping[str, object]) -> bool:
    schema = package.get("schema_version")
    if schema == N11_V1_SCHEMA_VERSION:
        return validate_result_package(package)
    if schema == N11_V2_SCHEMA_VERSION:
        return validate_evidence_package(package)
    raise ValueError("diagnostics_input_schema_invalid")



@dataclass(frozen=True)
class DiagnosticsPolicy:
    min_trade_count: int = 10
    minimum_validation_survival: float = 0.5
    maximum_family_concentration: float = 0.60
    policy_version: str = "quantbot-n12-policy-v1"

    def validate(self) -> None:
        if self.min_trade_count < 1 or not 0 <= self.minimum_validation_survival <= 1 or not 0 < self.maximum_family_concentration <= 1:
            raise ValueError("diagnostics_policy_invalid")


def summarize_stability(tasks: Sequence[Mapping[str, object]]) -> dict[str, object]:
    """No loader or evaluator: summarize only supplied, already packaged records."""
    by_model: dict[str, list[float]] = defaultdict(list)
    failures: Counter[str] = Counter()
    for task in tasks:
        model = str(task.get("model_id", ""))
        if task.get("status") != "COMPLETED":
            failures[str(task.get("error_type", "unknown"))] += 1
            continue
        for row in task.get("validation_results", task.get("validation", [])):
            if isinstance(row, Mapping):
                by_model[model].append(float(row.get("total_return", 0.0)))
    return {"schema_version": "quantbot-stability-diagnostics-n12-v1",
            "models": {name: {"observations": len(values), "mean_total_return": sum(values) / len(values) if values else 0.0,
                              "worst_total_return": min(values) if values else 0.0}
                       for name, values in sorted(by_model.items())},
            "failure_types": dict(sorted(failures.items())), "oos_read": False}


def build_diagnostics(package: Mapping[str, object], *, policy: DiagnosticsPolicy = DiagnosticsPolicy()) -> dict[str, object]:
    """Derive deterministic diagnostics from a validated N11 package only."""
    _validate_supported_n11_package(package)
    policy.validate()
    tasks = package["tasks"]
    by_model: dict[str, list[Mapping[str, object]]] = defaultdict(list)
    by_family: Counter[str] = Counter()
    cross_symbol: dict[str, set[str]] = defaultdict(set)
    rows = []
    for task in tasks:
        model = str(task.get("model_id")); family = str(task.get("family", "UNSPECIFIED"))
        validations = task.get("validation_results", task.get("validation", []))
        trains = task.get("train_results", task.get("train", []))
        if not isinstance(validations, list) or not isinstance(trains, list):
            raise ValueError("diagnostic_result_shape_invalid")
        by_model[model].append(task); by_family[family] += 1; cross_symbol[model].add(str(task.get("symbol")))
        returns = [float(row.get("total_return", 0.0)) for row in validations if isinstance(row, Mapping)]
        trades = [int(row.get("trades", 0)) for row in validations if isinstance(row, Mapping)]
        pfs = [float(row.get("profit_factor", 0.0)) for row in validations if isinstance(row, Mapping)]
        finite_pfs = [value for value in pfs if math.isfinite(value)]
        dds = [float(row.get("max_drawdown", 0.0)) for row in validations if isinstance(row, Mapping)]
        train_params = {str(row.get("params")) for row in trains if isinstance(row, Mapping)}
        validation_params = {str(row.get("params")) for row in validations if isinstance(row, Mapping)}
        rows.append({"task_identity": task.get("task_identity"), "model_id": model, "symbol": task.get("symbol"),
                     "parameter_neighborhood_size": len(train_params), "rank_stability": len(validation_params) / max(1, len(train_params)),
                     "validation_survival": sum(value > 0 for value in returns) / max(1, len(returns)),
                     "trade_count_adequate": sum(trades) >= policy.min_trade_count,
                     "turnover": sum(trades), "return": sum(returns) / max(1, len(returns)),
                     "profit_factor": sum(pfs) / max(1, len(pfs)),
                   "profit_factor_finite_mean": sum(finite_pfs) / len(finite_pfs) if finite_pfs else None,
                   "profit_factor_finite_count": len(finite_pfs),
                   "profit_factor_nonfinite_count": len(pfs) - len(finite_pfs),
                   "max_drawdown": max(dds, default=0.0),
                     "degenerate": len(train_params) < 2 or not returns,
                     "insufficient_sample": sum(trades) < policy.min_trade_count})
    total = len(tasks)
    payload = {"schema_version": "quantbot-diagnostics-n12-v2", "research_freeze_identity": package["research_freeze_identity"],
               "research_plan_identity": package["research_plan_identity"], "result_package_identity": package["artifact_identity"],
               "policy": asdict(policy), "task_diagnostics": sorted(rows, key=lambda row: row["task_identity"]),
               "cross_symbol_consistency": {model: len(symbols) for model, symbols in sorted(cross_symbol.items())},
               "family_concentration": {family: count / max(1, total) for family, count in sorted(by_family.items())},
               "model_concentration": {model: len(items) / max(1, total) for model, items in sorted(by_model.items())},
               "oos_read": False, "oos_status": "SEALED", "oos_authorization": "NOT_AUTHORIZED"}
    return seal(payload)


def validate_diagnostics(artifact: Mapping[str, object], package: Mapping[str, object]) -> bool:
    _validate_supported_n11_package(package); validate_seal(artifact)
    if artifact.get("schema_version") != "quantbot-diagnostics-n12-v2": raise ValueError("diagnostics_schema_invalid")
    for key in ("research_freeze_identity", "research_plan_identity"):
        if artifact.get(key) != package.get(key): raise ValueError("diagnostics_binding_mismatch")
    if artifact.get("result_package_identity") != package.get("artifact_identity"): raise ValueError("diagnostics_package_mismatch")
    if artifact.get("oos_read") is not False or artifact.get("oos_status") != "SEALED" or artifact.get("oos_authorization") != "NOT_AUTHORIZED": raise ValueError("diagnostics_oos_violation")
    try: policy=DiagnosticsPolicy(**artifact.get("policy", {}))
    except (TypeError,ValueError) as exc: raise ValueError("diagnostics_policy_invalid") from exc
    policy.validate()
    expected=build_diagnostics(package,policy=policy)
    claimed={key:value for key,value in artifact.items() if key!="artifact_identity"}
    rebuilt={key:value for key,value in expected.items() if key!="artifact_identity"}
    if claimed != rebuilt: raise ValueError("diagnostics_semantic_mismatch")
    return True
