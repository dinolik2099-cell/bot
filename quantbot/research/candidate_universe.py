"""Machine-readable, deterministic candidate-universe specification.

This module only describes registered models. It never loads candles, reports,
TRAIN/VALIDATION/OOS results, or runs a backtest.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import inspect
import json
from typing import Any

from .model_registry import RegisteredModel, list_models


CANONICAL_SYMBOLS = ("BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT")
CANONICAL_TIMEFRAME = "1h"


@dataclass(frozen=True)
class CandidateUniverseEntry:
    model_id: str
    name: str
    family: str
    version: str
    implementation_module: str
    lifecycle_status: str
    causal_timing: str
    required_features: tuple[str, ...]
    parameter_grid: dict[str, tuple[Any, ...]]
    long_short_capable: bool
    warmup_bars: int
    supported_symbols: tuple[str, ...]
    timeframe: str
    execution_assumptions: str
    research_eligible: bool
    provenance: str
    rationale: str
    known_limitations: str
    parameter_grid_hash: str
    implementation_hash: str

    def canonical_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["required_features"] = list(self.required_features)
        data["supported_symbols"] = list(self.supported_symbols)
        data["parameter_grid"] = {key: list(value) for key, value in sorted(self.parameter_grid.items())}
        return data


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _grid_hash(model: RegisteredModel) -> str:
    value = {key: list(values) for key, values in sorted(model.spec.parameter_grid.items())}
    return _digest(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def _implementation_hash(model: RegisteredModel) -> str:
    return _digest(inspect.getsource(model.strategy).encode("utf-8"))


def _warmup_bars(model: RegisteredModel) -> int:
    values = []
    for key, options in model.spec.parameter_grid.items():
        if any(token in key for token in ("lookback", "period", "window", "slow", "long", "atr_window", "squeeze_window")):
            values.extend(value for value in options if isinstance(value, int))
    return max(values, default=1)


def candidate_entry(model: RegisteredModel) -> CandidateUniverseEntry:
    spec = model.spec
    return CandidateUniverseEntry(
        model_id=f"quantbot.{spec.name}.{spec.research_version}",
        name=spec.name, family=spec.family, version=spec.research_version,
        implementation_module=model.strategy.__module__, lifecycle_status=spec.status,
        causal_timing="strategy row T-1 produces intent eligible at T; execution is separately gated",
        required_features=spec.required_columns, parameter_grid={key: tuple(value) for key, value in spec.parameter_grid.items()},
        long_short_capable=True, warmup_bars=_warmup_bars(model), supported_symbols=CANONICAL_SYMBOLS,
        timeframe=CANONICAL_TIMEFRAME, execution_assumptions="canonical engine_v2 + CostModel; no model order authority",
        research_eligible=spec.status not in {"retired", "deferred"}, provenance=spec.source,
        rationale=spec.rationale, known_limitations="Candidate only; no OOS result is consumed by this specification.",
        parameter_grid_hash=_grid_hash(model), implementation_hash=_implementation_hash(model),
    )


def build_candidate_universe() -> tuple[CandidateUniverseEntry, ...]:
    entries = tuple(sorted((candidate_entry(model) for model in list_models()), key=lambda entry: entry.model_id))
    ids = [entry.model_id for entry in entries]
    if len(ids) != len(set(ids)):
        raise ValueError("candidate universe model_id collision")
    return entries


def candidate_universe_hash(entries: tuple[CandidateUniverseEntry, ...]) -> str:
    payload = [entry.canonical_dict() for entry in entries]
    return _digest(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"))
