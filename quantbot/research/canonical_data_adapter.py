"""N8 boundary-locked canonical non-OOS data adapter.

The adapter owns validation, not file discovery.  Its injected canonical source
must accept an explicit window range and return ``(frame, 'canonical_raw')``.
This prevents the legacy whole-dataset/fallback path from accidentally loading
OOS data under a TRAIN or VALIDATION request.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping

import pandas as pd

from .formal_runner import N7Context, N7ExecutionError, authorize_n7_window
from .freeze_manifest import _hash
from .integration import load_boundary_lock, timestamp_in_non_tradable_gap


class N8DataError(RuntimeError):
    pass


@dataclass(frozen=True)
class N8DataContext:
    n7: N7Context
    dataset: Any


def load_n8_data_context(n7: N7Context, boundary_lock_path) -> N8DataContext:
    """Metadata-only wiring validation; no market-data source is called."""
    dataset=load_boundary_lock(boundary_lock_path)
    plan=n7.plan; freeze=n7.freeze
    if dataset.dataset_id!=plan['boundary']['dataset_id']: raise N8DataError('dataset_id_mismatch')
    if dataset.interval!='1h' or plan['protocol_scope']['timeframe']!='1h': raise N8DataError('timeframe_mismatch')
    if dataset.synthetic_candles: raise N8DataError('synthetic_candles_not_allowed')
    if dataset.gap_policy!='non_tradable': raise N8DataError('gap_policy_mismatch')
    if dataset.lookahead_policy!='execution_at_T_uses_information_strictly_before_T': raise N8DataError('causal_policy_mismatch')
    if _hash(plan['boundary'])!=plan['boundary_identity_hash']: raise N8DataError('boundary_identity_mismatch')
    if plan['boundary']!=freeze['research_boundary']: raise N8DataError('accepted_boundary_mismatch')
    locked={item.name:{'start':item.start.isoformat(),'end':item.end.isoformat()} for item in dataset.windows}
    expected={'TRAIN':plan['boundary']['train_boundary'],'VALIDATION':plan['boundary']['validation_boundary'],'OOS':plan['boundary']['oos_boundary']}
    if locked!=expected: raise N8DataError('boundary_lock_window_mismatch')
    if tuple(plan['symbols'])!=tuple(n7.freeze['protocol_scope']['symbols']): raise N8DataError('symbol_universe_mismatch')
    if freeze['protocol_scope']['engine_identity']!='quantbot.backtest.engine_v2.BacktestEngine': raise N8DataError('engine_identity_mismatch')
    if freeze['protocol_scope']['cost_model_identity']!='quantbot.backtest.costs.CostModel': raise N8DataError('cost_model_identity_mismatch')
    return N8DataContext(n7=n7,dataset=dataset)


def _window(dataset, name: str):
    try: authorize_n7_window(name)
    except N7ExecutionError as exc: raise N8DataError('window_not_authorized') from exc
    return next(item for item in dataset.windows if item.name==name)


def _validate_frame(context: N8DataContext, frame: pd.DataFrame, symbol: str, window_name: str) -> pd.DataFrame:
    if not isinstance(frame,pd.DataFrame) or frame.empty: raise N8DataError('empty_frame')
    if not isinstance(frame.index,pd.DatetimeIndex) or frame.index.tz is None: raise N8DataError('utc_index_required')
    if not frame.index.is_monotonic_increasing: raise N8DataError('timestamps_not_monotonic')
    if frame.index.has_duplicates: raise N8DataError('duplicate_timestamps')
    required={'open','high','low','close','volume'}
    if required-set(frame.columns): raise N8DataError('missing_ohlcv_columns')
    if frame.attrs.get('synthetic_candles') is True or ('synthetic' in frame.columns and bool(frame['synthetic'].any())):
        raise N8DataError('synthetic_rows_not_allowed')
    window=_window(context.dataset,window_name)
    start,end=window.start,window.end
    index=frame.index.tz_convert('UTC')
    if index[0]<start or index[-1]>end: raise N8DataError('frame_outside_requested_window')
    if any(timestamp_in_non_tradable_gap(context.dataset,symbol,ts) for ts in index): raise N8DataError('frame_contains_non_tradable_gap')
    return frame


def make_n8_window_loader(context: N8DataContext, canonical_window_source: Callable[..., tuple[pd.DataFrame,str]]):
    """Return the only N8 data-loader entrypoint used by formal execution.

    ``canonical_window_source`` receives a fully checked exact range.  It may
    not choose another source or silently widen the request.
    """
    def loader(*, window: str, symbol: str, task: Mapping[str, Any], boundary: Mapping[str, Any]):
        request=_window(context.dataset,window)
        if symbol not in context.n7.plan['symbols'] or symbol not in context.n7.freeze['protocol_scope']['symbols']:
            raise N8DataError('symbol_not_frozen')
        if task.get('symbol')!=symbol or task.get('model_id') not in {x['model_id'] for x in context.n7.plan['models']}:
            raise N8DataError('task_not_frozen')
        if boundary!=context.n7.plan['boundary'] or boundary.get('dataset_id')!=context.dataset.dataset_id:
            raise N8DataError('boundary_request_mismatch')
        frame,source=canonical_window_source(symbol=symbol,market=context.dataset.market,interval=context.dataset.interval,
                                               window=window,start=request.start,end=request.end,dataset_id=context.dataset.dataset_id)
        if source!='canonical_raw': raise N8DataError('noncanonical_or_fallback_source')
        return _validate_frame(context,frame,symbol,window)
    return loader
