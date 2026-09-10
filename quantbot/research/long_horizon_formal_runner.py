"""Canonical long-horizon evaluator construction; execution remains gated."""
from __future__ import annotations
from typing import Mapping
from .future_data_plane import FutureRuntimeContext, make_future_canonical_evaluator
from .long_horizon import LongHorizonProtocol, WINDOW_DAYS


class LongHorizonRunnerError(RuntimeError):
    pass


def make_long_horizon_canonical_evaluator(*, runtime: FutureRuntimeContext, evidence,
                                          n8_context, raw_root, strategy_resolver, engine_factory):
    """Bind the immutable 180/200/240-day contract to N7/N8 execution."""
    if runtime.protocol.get('stage')!='long_horizon': raise LongHorizonRunnerError('long_horizon_stage_required')
    config=runtime.protocol.get('config')
    if not isinstance(config,Mapping): raise LongHorizonRunnerError('long_horizon_config_missing')
    try: protocol=LongHorizonProtocol(**dict(config.get('protocol',{})))
    except (TypeError,ValueError) as exc: raise LongHorizonRunnerError('long_horizon_protocol_invalid') from exc
    protocol.validate()
    if tuple(config.get('windows',()))!=WINDOW_DAYS: raise LongHorizonRunnerError('long_horizon_windows_drift')
    return make_future_canonical_evaluator(runtime=runtime,evidence=evidence,n8_context=n8_context,
                                           raw_root=raw_root,strategy_resolver=strategy_resolver,engine_factory=engine_factory)
