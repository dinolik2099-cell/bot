"""N12 deterministic, non-OOS diagnostic summaries over supplied artifacts."""
from __future__ import annotations

from collections import Counter, defaultdict
from typing import Mapping, Sequence


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
