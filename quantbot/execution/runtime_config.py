"""Fail-closed execution runtime configuration. Live execution is disabled."""
from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class RuntimeConfig:
    mode: str = "paper"
    one_shot: bool = True
    persist_state: bool = False
    live_enabled: bool = False

def validate_runtime_config(config: RuntimeConfig) -> None:
    if config.live_enabled or config.mode != "paper":
        raise PermissionError("live execution is disabled; only explicit paper mode is supported")
    if not config.one_shot:
        raise PermissionError("continuous runtime is not authorized")
    if config.persist_state:
        raise PermissionError("persistent paper runtime is not authorized")
