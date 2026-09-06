from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Callable, Mapping
import inspect

import pandas as pd


StrategyFn = Callable[..., pd.DataFrame]


@dataclass(frozen=True)
class ModelSpec:
    name: str
    category: str
    source: str
    rationale: str
    required_columns: tuple[str, ...]
    parameter_grid: Mapping[str, tuple[Any, ...]]
    market_regimes: tuple[str, ...]
    lookahead_policy: str = "strictly_causal"
    status: str = "candidate"
    family: str = "unclassified"
    description: str = ""
    future_data_risk: str = "unknown"
    train_status: str = "not_run"
    validation_status: str = "not_run"
    oos_status: str = "sealed"
    cost_sensitivity: str = "unassessed"
    max_drawdown: float | None = None
    research_version: str = "unversioned"
    # Unknown model attributes must remain unknown until explicitly declared.
    model_id: str = ""
    causal_timing: str = "unverified"
    long_short_capable: bool | None = None
    warmup_bars: int | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["required_columns"] = list(self.required_columns)
        data["parameter_grid"] = {k: list(v) for k, v in self.parameter_grid.items()}
        data["market_regimes"] = list(self.market_regimes)
        return data


@dataclass(frozen=True)
class RegisteredModel:
    spec: ModelSpec
    strategy: StrategyFn


_REGISTRY: dict[str, RegisteredModel] = {}


def register_model(spec: ModelSpec, strategy: StrategyFn) -> None:
    if spec.name in _REGISTRY:
        raise ValueError(f"duplicate model name: {spec.name}")
    _REGISTRY[spec.name] = RegisteredModel(spec=spec, strategy=strategy)


def get_model(name: str) -> RegisteredModel:
    try:
        return _REGISTRY[name]
    except KeyError as exc:
        raise KeyError(f"unknown model: {name}") from exc


def list_models() -> tuple[RegisteredModel, ...]:
    return tuple(_REGISTRY.values())


def model_inventory() -> list[dict[str, Any]]:
    return [item.spec.to_dict() for item in list_models()]


def validate_registry() -> None:
    if not _REGISTRY:
        raise ValueError("model registry is empty")
    for item in list_models():
        spec = item.spec
        if not spec.name or not spec.category or not spec.source:
            raise ValueError(f"incomplete model metadata: {spec.name!r}")
        if spec.lookahead_policy != "strictly_causal":
            raise ValueError(f"model {spec.name} does not declare strictly_causal")
        if spec.status not in {"candidate", "testing", "validated", "oos_retained", "deferred", "retired"}:
            raise ValueError(f"invalid status for {spec.name}: {spec.status}")
        if not spec.family:
            raise ValueError(f"model {spec.name} has no family")
        if spec.future_data_risk not in {"unknown", "none_declared", "review_required", "blocked"}:
            raise ValueError(f"invalid future-data risk for {spec.name}: {spec.future_data_risk}")
        lifecycle = {"not_run", "in_progress", "passed", "failed", "locked", "sealed", "not_authorized"}
        for field in ("train_status", "validation_status", "oos_status"):
            if getattr(spec, field) not in lifecycle:
                raise ValueError(f"invalid {field} for {spec.name}: {getattr(spec, field)}")
        if not spec.research_version:
            raise ValueError(f"model {spec.name} has no research version")
        if not spec.model_id:
            raise ValueError(f"model {spec.name} has no stable model_id")
        if spec.causal_timing not in {"t_minus_1_to_t_intent", "unverified"}:
            raise ValueError(f"invalid causal timing for {spec.name}: {spec.causal_timing}")
        if spec.warmup_bars is not None and spec.warmup_bars < 0:
            raise ValueError(f"invalid warmup_bars for {spec.name}: {spec.warmup_bars}")
        if not callable(item.strategy):
            raise TypeError(f"strategy is not callable: {spec.name}")

        signature = inspect.signature(item.strategy)
        parameters = signature.parameters
        if "df" not in parameters:
            raise ValueError(f"model {spec.name} must accept df")
        accepts_kwargs = any(
            p.kind == inspect.Parameter.VAR_KEYWORD
            for p in parameters.values()
        )
        if not accepts_kwargs:
            unknown = set(spec.parameter_grid) - set(parameters)
            if unknown:
                raise ValueError(
                    f"model {spec.name} parameter grid has unknown keys: "
                    f"{sorted(unknown)}"
                )
        for key, values in spec.parameter_grid.items():
            if not values:
                raise ValueError(f"model {spec.name} has empty grid: {key}")


def register_existing_models() -> None:
    from quantbot.strategies.models import (
        mean_reversion,
        trend_breakout,
        trend_pullback,
        volatility_breakout,
    )

    common = ("open", "high", "low", "close", "volume")
    existing = (
        ("trend_breakout", "趋势/突破", trend_breakout, "QuantBot 已验证基础模型"),
        ("trend_pullback", "趋势/回调", trend_pullback, "QuantBot 已验证基础模型"),
        ("volatility_breakout", "突破/波动率", volatility_breakout, "QuantBot 已验证基础模型"),
        ("mean_reversion", "反转/均值回归", mean_reversion, "QuantBot 已有基础模型，当前基准表现较弱"),
    )
    grids = {
        "trend_breakout": {"lookback": (20, 40, 60), "stop_atr": (1.5, 2.0, 2.5), "reward_r": (2.0, 3.0, 4.0)},
        "trend_pullback": {"ema_fast": (10, 20), "ema_slow": (50, 80, 120), "stop_atr": (1.5, 2.0, 2.5), "reward_r": (2.0, 3.0)},
        "volatility_breakout": {"range_lookback": (10, 20, 40), "stop_atr": (1.5, 2.0, 2.5), "reward_r": (2.0, 3.0, 4.0)},
        "mean_reversion": {"lookback": (20, 40, 60), "z_entry": (2.0, 2.5, 3.0), "z_exit": (0.5, 0.75, 1.0), "stop_atr": (1.5, 2.0, 2.5)},
    }
    for name, category, fn, rationale in existing:
        family = category.split("/", 1)[0]
        register_model(ModelSpec(
            name, category, "QuantBot现有模型", rationale, common, grids[name], ("多种市场环境",),
            family=family, description=rationale, future_data_risk="none_declared",
            train_status="not_run", validation_status="not_run", oos_status="sealed",
            cost_sensitivity="unassessed", research_version="existing-models-v1",
            model_id=f"quantbot.{name}.v1", causal_timing="t_minus_1_to_t_intent",
            long_short_capable=True, warmup_bars=None,
        ), fn)
