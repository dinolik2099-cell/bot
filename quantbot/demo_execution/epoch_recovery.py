"""Explicit, create-only recovery epoch construction for Demo fail-closed state."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .core import DemoExecutionError, canon, identity, utc_now
from .models import OrderState
from .persistence import DemoPersistence

CHECKPOINT_SCHEMA = 'quantbot-demo-checkpoint-v1'
# These states have durable evidence that no order POST was attempted.  Every
# other state is intentionally rejected rather than inferred safe.
SAFE_PREDECESSOR_STATES = {
    OrderState.INTENT_CREATED.value,
    OrderState.REJECTED_POLICY.value,
    OrderState.REJECTED_VENUE.value,
    OrderState.SKIPPED.value,
}
FILLED_AUTHORIZATION_SCHEMA = 'quantbot-demo-filled-recovery-authorization-v1'


def _sha256_bytes(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _require_sha(value: str, name: str, length: int) -> str:
    value = str(value)
    if len(value) != length or any(char not in '0123456789abcdef' for char in value.lower()):
        raise DemoExecutionError(f'demo_recovery_{name}_invalid')
    return value


def _read_json(path: Path, name: str):
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as exc:
        raise DemoExecutionError(f'demo_recovery_{name}_invalid') from exc
    return value


def _validate_checkpoint(checkpoint: dict, *, expected_git_commit: str, expected_config_identity: str, require_zero_fills=True) -> None:
    if not isinstance(checkpoint, dict) or checkpoint.get('schema_version') != CHECKPOINT_SCHEMA:
        raise DemoExecutionError('demo_recovery_checkpoint_schema_invalid')
    stored_identity = checkpoint.get('checkpoint_identity')
    if not isinstance(stored_identity, str) or stored_identity != identity({key: value for key, value in checkpoint.items() if key != 'checkpoint_identity'}):
        raise DemoExecutionError('demo_recovery_checkpoint_identity_invalid')
    if checkpoint.get('git_commit') != expected_git_commit:
        raise DemoExecutionError('demo_recovery_predecessor_git_mismatch')
    if checkpoint.get('config_identity') != expected_config_identity:
        raise DemoExecutionError('demo_recovery_predecessor_config_mismatch')
    if checkpoint.get('fail_closed') is not True:
        raise DemoExecutionError('demo_recovery_predecessor_not_fail_closed')
    if not isinstance(checkpoint.get('last_signal_cursor'), str) or not checkpoint['last_signal_cursor']:
        raise DemoExecutionError('demo_recovery_predecessor_cursor_invalid')
    if type(checkpoint.get('fills_seen')) is not int or (require_zero_fills and checkpoint['fills_seen'] != 0):
        raise DemoExecutionError('demo_recovery_predecessor_fills_not_safe')
    _require_sha(checkpoint.get('source_forward_identity'), 'predecessor_forward_identity', 64)


def _validate_ledger(rows) -> None:
    if not isinstance(rows, dict):
        raise DemoExecutionError('demo_recovery_ledger_invalid')
    for signal_identity, row in rows.items():
        if not isinstance(signal_identity, str) or not isinstance(row, dict) or row.get('state') not in SAFE_PREDECESSOR_STATES:
            raise DemoExecutionError('demo_recovery_predecessor_execution_ambiguity')


def _parse_timestamp(value, name):
    try:
        parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        if parsed.tzinfo is None:
            raise ValueError('timezone_required')
        return parsed.astimezone(timezone.utc)
    except Exception as exc:
        raise DemoExecutionError(f'demo_recovery_{name}_invalid') from exc


def _claim_authorization(path, authorization_identity, target_root):
    """Durably reserve one sealed authorization for exactly one target root.

    A claim survives pre-publication failures and allows retrying that same
    target only.  It is intentionally never removed or redirected.
    """
    claim_path = Path(path).with_name(Path(path).name + '.claim')
    claim = {'schema_version': 'quantbot-demo-filled-recovery-claim-v1',
             'authorization_identity': authorization_identity, 'target_root': str(target_root)}
    claim['claim_identity'] = identity(claim)
    try:
        with claim_path.open('x', encoding='utf-8') as handle:
            handle.write(canon(claim) + '\n'); handle.flush(); os.fsync(handle.fileno())
    except FileExistsError:
        existing = _read_json(claim_path, 'authorization_claim')
        if not isinstance(existing, dict) or existing.get('claim_identity') != identity({key: value for key, value in existing.items() if key != 'claim_identity'}) or any(existing.get(key) != value for key, value in claim.items() if key != 'claim_identity'):
            raise DemoExecutionError('demo_recovery_authorization_claim_mismatch')
        claim = existing
    except Exception as exc:
        raise DemoExecutionError('demo_recovery_authorization_claim_write_failed') from exc
    return claim_path, claim


def _filled_predecessor(checkpoint, rows):
    if not isinstance(rows, dict) or not rows:
        raise DemoExecutionError('demo_recovery_filled_ledger_invalid')
    filled = 0
    terminal = {item.value for item in __import__('quantbot.demo_execution.models', fromlist=['TERMINAL']).TERMINAL}
    for signal_identity, row in rows.items():
        intent = row.get('intent') if isinstance(row, dict) else None
        if not isinstance(signal_identity, str) or not isinstance(row, dict) or row.get('state') not in terminal or not isinstance(intent, dict):
            raise DemoExecutionError('demo_recovery_filled_lifecycle_ambiguity')
        if not isinstance(row.get('execution_intent_identity'), str) or not isinstance(row.get('client_order_id'), str) or intent.get('action') not in {'OPEN', 'CLOSE'}:
            raise DemoExecutionError('demo_recovery_filled_lifecycle_ambiguity')
        if row['state'] == OrderState.FILLED.value:
            filled += 1
    if filled == 0 or checkpoint.get('fills_seen') != filled:
        raise DemoExecutionError('demo_recovery_filled_count_mismatch')


def _filled_remote_result(ledger, adapter):
    """Reuse canonical reconciliation and position attribution without writing predecessor evidence."""
    from .reconciliation import reconcile
    from .runtime import DemoRuntime

    # The supplied ledger is already durable and contains terminal rows only;
    # canonical reconcile therefore performs read-only remote inspection.
    state = reconcile(ledger, adapter)
    if state.get('open_orders') != 0:
        raise DemoExecutionError('demo_recovery_remote_open_orders_present')
    positions = adapter.positions()
    class Context:
        _filled_at = DemoRuntime._filled_at
        _later_filled_open = DemoRuntime._later_filled_open
        def __init__(self, ledger): self.ledger = ledger
    context = Context(ledger)
    attributed = DemoRuntime._position_attributions(context, positions)
    for row in ledger.rows.values():
        current = attributed.get(row['intent'].get('symbol'))
        if row['state'] == OrderState.FILLED.value and row['intent'].get('action') == 'CLOSE' and current is not None and not context._later_filled_open(row, current['row']):
            raise DemoExecutionError('demo_recovery_close_position_not_flat')
    summary = [{'symbol': symbol, 'side': value['side'], 'quantity': format(value['quantity'], 'f'),
                'execution_intent_identity': value['row']['execution_intent_identity'],
                'client_order_id': value['row']['client_order_id']}
               for symbol, value in sorted(attributed.items())]
    return {'open_orders': state['open_orders'], 'attributed_positions': summary}


def create_recovery_epoch(*, predecessor_root, predecessor_checkpoint, expected_predecessor_git_commit: str,
                          expected_predecessor_config_identity: str, target_root, target_git_commit: str,
                          target_config_identity: str, forward_root, recovery_reason: str) -> dict:
    """Create a new local epoch from an explicitly verified safe predecessor.

    The predecessor is never opened for write.  This function has no exchange
    adapter parameter by design; remote reconciliation remains a mandatory
    later startup operation in :class:`DemoRuntime`.
    """
    predecessor_root = Path(predecessor_root).resolve()
    predecessor_checkpoint = Path(predecessor_checkpoint).resolve()
    target_root = Path(target_root).resolve()
    forward_root = Path(forward_root).resolve()
    expected_predecessor_git_commit = _require_sha(expected_predecessor_git_commit, 'predecessor_git_commit', 40)
    expected_predecessor_config_identity = _require_sha(expected_predecessor_config_identity, 'predecessor_config_identity', 64)
    target_git_commit = _require_sha(target_git_commit, 'target_git_commit', 40)
    target_config_identity = _require_sha(target_config_identity, 'target_config_identity', 64)
    if not isinstance(recovery_reason, str) or not recovery_reason.strip():
        raise DemoExecutionError('demo_recovery_reason_required')
    expected_checkpoint = predecessor_root / 'checkpoints' / 'runtime.json'
    if predecessor_checkpoint != expected_checkpoint or not predecessor_checkpoint.is_file():
        raise DemoExecutionError('demo_recovery_predecessor_checkpoint_path_invalid')
    ledger_path = predecessor_root / 'runtime' / 'ledger.json'
    if not ledger_path.is_file():
        raise DemoExecutionError('demo_recovery_predecessor_ledger_missing')
    if target_root.exists() or not target_root.parent.is_dir():
        raise DemoExecutionError('demo_recovery_target_root_exists')

    checkpoint_hash_before = _sha256_bytes(predecessor_checkpoint)
    ledger_hash_before = _sha256_bytes(ledger_path)
    checkpoint = _read_json(predecessor_checkpoint, 'checkpoint')
    ledger_rows = _read_json(ledger_path, 'ledger')
    _validate_checkpoint(checkpoint, expected_git_commit=expected_predecessor_git_commit,
                         expected_config_identity=expected_predecessor_config_identity)
    _validate_ledger(ledger_rows)
    source_forward_identity = identity({'root': str(forward_root)})
    if source_forward_identity != checkpoint['source_forward_identity']:
        raise DemoExecutionError('demo_recovery_predecessor_forward_mismatch')

    provenance = {
        'schema_version': 'quantbot-demo-recovery-v1',
        'predecessor_epoch': checkpoint['demo_epoch'],
        'predecessor_root': str(predecessor_root),
        'predecessor_checkpoint_identity': checkpoint['checkpoint_identity'],
        'predecessor_checkpoint_sha256': checkpoint_hash_before,
        'predecessor_ledger_sha256': ledger_hash_before,
        'predecessor_cursor': checkpoint['last_signal_cursor'],
        'predecessor_git_commit': expected_predecessor_git_commit,
        'predecessor_config_identity': expected_predecessor_config_identity,
        'source_forward_identity': source_forward_identity,
        'forward_root': str(forward_root),
        'target_git_commit': target_git_commit,
        'target_config_identity': target_config_identity,
        'recovery_reason': recovery_reason,
        'old_intents_not_replayed': True,
    }
    provenance['recovery_identity'] = identity(provenance)
    staging_root = target_root.parent / f'.{target_root.name}.recovery-staging-{uuid.uuid4().hex}'
    persistence = None
    try:
        staging_root.mkdir()
        persistence = DemoPersistence(staging_root)
        persistence.append('recovery', utc_now()[:10], provenance)
        new_checkpoint = {
            'schema_version': CHECKPOINT_SCHEMA,
            'git_commit': target_git_commit,
            'demo_epoch': target_root.name,
            'demo_epoch_start': utc_now(),
            'config_identity': target_config_identity,
            'source_forward_identity': source_forward_identity,
            'last_signal_cursor': checkpoint['last_signal_cursor'],
            'orders_seen': 0,
            'fills_seen': 0,
            'reconciliation': {},
            'fail_closed': False,
            'runtime_health': {'live_order_endpoint_allowed': False},
            'recovery': provenance,
        }
        new_checkpoint['checkpoint_identity'] = identity(new_checkpoint)
        persistence.write_checkpoint(new_checkpoint)
        persistence.flush()
        persistence.close()
        staged_checkpoint = _read_json(staging_root / 'checkpoints' / 'runtime.json', 'staged_checkpoint')
        if staged_checkpoint.get('checkpoint_identity') != identity({key: value for key, value in staged_checkpoint.items() if key != 'checkpoint_identity'}):
            raise DemoExecutionError('demo_recovery_staged_checkpoint_identity_invalid')
        staged_provenance = _read_json(next((staging_root / 'recovery').glob('*/*.jsonl')), 'staged_provenance')
        if staged_provenance.get('recovery_identity') != identity({key: value for key, value in staged_provenance.items() if key not in {'created_at', 'recovery_identity'}}):
            raise DemoExecutionError('demo_recovery_staged_provenance_identity_invalid')
        if _sha256_bytes(predecessor_checkpoint) != checkpoint_hash_before or _sha256_bytes(ledger_path) != ledger_hash_before:
            raise DemoExecutionError('demo_recovery_predecessor_mutation_detected')
        if target_root.exists():
            raise DemoExecutionError('demo_recovery_target_root_exists')
        staging_root.rename(target_root)
    except DemoExecutionError:
        if persistence is not None:
            try:
                persistence.close()
            except Exception:
                pass
        if staging_root.exists():
            shutil.rmtree(staging_root)
        raise
    except Exception as exc:
        if persistence is not None:
            try:
                persistence.close()
            except Exception:
                pass
        if staging_root.exists():
            shutil.rmtree(staging_root)
        raise DemoExecutionError('demo_recovery_target_write_failed') from exc
    return {'target_root': str(target_root), 'checkpoint_identity': new_checkpoint['checkpoint_identity'],
            'recovery_identity': provenance['recovery_identity'], 'cursor': checkpoint['last_signal_cursor']}


def create_filled_recovery_authorization(*, predecessor_root, predecessor_checkpoint, expected_predecessor_git_commit,
                                         expected_predecessor_config_identity, target_git_commit, target_config_identity,
                                         forward_root, target_root, authorization_path, adapter, recovery_reason, now=None,
                                         authorization_ttl_seconds=300):
    """Create one sealed, read-only reconciliation authorization for a filled predecessor.

    This function deliberately has no order-submission path.  It uses the
    existing reconciliation and position-attribution logic solely to prove the
    remote state before a separate local epoch-creation step.
    """
    from .ledger import ExecutionLedger
    predecessor_root, predecessor_checkpoint = Path(predecessor_root).resolve(), Path(predecessor_checkpoint).resolve()
    forward_root, target_root, authorization_path = Path(forward_root).resolve(), Path(target_root).resolve(), Path(authorization_path).resolve()
    predecessor_git = _require_sha(expected_predecessor_git_commit, 'predecessor_git_commit', 40)
    predecessor_config = _require_sha(expected_predecessor_config_identity, 'predecessor_config_identity', 64)
    target_git = _require_sha(target_git_commit, 'target_git_commit', 40)
    target_config = _require_sha(target_config_identity, 'target_config_identity', 64)
    if authorization_path.exists() or target_root.exists() or not target_root.parent.is_dir() or not authorization_path.parent.is_dir() or not isinstance(recovery_reason, str) or not recovery_reason.strip() or type(authorization_ttl_seconds) is not int or authorization_ttl_seconds <= 0:
        raise DemoExecutionError('demo_recovery_authorization_path_or_policy_invalid')
    if predecessor_checkpoint != predecessor_root / 'checkpoints' / 'runtime.json' or not predecessor_checkpoint.is_file():
        raise DemoExecutionError('demo_recovery_predecessor_checkpoint_path_invalid')
    ledger_path = predecessor_root / 'runtime' / 'ledger.json'
    if not ledger_path.is_file():
        raise DemoExecutionError('demo_recovery_predecessor_ledger_missing')
    checkpoint_hash, ledger_hash = _sha256_bytes(predecessor_checkpoint), _sha256_bytes(ledger_path)
    checkpoint, rows = _read_json(predecessor_checkpoint, 'checkpoint'), _read_json(ledger_path, 'ledger')
    _validate_checkpoint(checkpoint, expected_git_commit=predecessor_git, expected_config_identity=predecessor_config, require_zero_fills=False)
    _filled_predecessor(checkpoint, rows)
    source_forward_identity = identity({'root': str(forward_root)})
    if source_forward_identity != checkpoint['source_forward_identity']:
        raise DemoExecutionError('demo_recovery_predecessor_forward_mismatch')
    remote_result = _filled_remote_result(ExecutionLedger(predecessor_root), adapter)
    verified_at = _parse_timestamp(now or utc_now(), 'authorization_timestamp')
    authorization = {'schema_version': FILLED_AUTHORIZATION_SCHEMA, 'verified_at': verified_at.isoformat(),
                     'expires_at': (verified_at + timedelta(seconds=authorization_ttl_seconds)).isoformat(),
                     'predecessor_epoch': checkpoint['demo_epoch'], 'predecessor_root': str(predecessor_root),
                     'predecessor_checkpoint_identity': checkpoint['checkpoint_identity'], 'predecessor_checkpoint_sha256': checkpoint_hash,
                     'predecessor_ledger_sha256': ledger_hash, 'predecessor_cursor': checkpoint['last_signal_cursor'],
                     'predecessor_git_commit': predecessor_git, 'predecessor_config_identity': predecessor_config,
                     'source_forward_identity': source_forward_identity, 'forward_root': str(forward_root),
                     'target_git_commit': target_git, 'target_config_identity': target_config, 'authorized_target_root': str(target_root),
                     'recovery_reason': recovery_reason, 'predecessor_executed_fills': True,
                     'old_intents_not_replayed': True, 'remote_reconciliation': remote_result}
    authorization['authorization_identity'] = identity(authorization)
    try:
        with authorization_path.open('x', encoding='utf-8') as handle:
            handle.write(canon(authorization) + '\n'); handle.flush(); os.fsync(handle.fileno())
    except FileExistsError as exc:
        raise DemoExecutionError('demo_recovery_authorization_exists') from exc
    except Exception as exc:
        if authorization_path.exists(): authorization_path.unlink()
        raise DemoExecutionError('demo_recovery_authorization_write_failed') from exc
    if _sha256_bytes(predecessor_checkpoint) != checkpoint_hash or _sha256_bytes(ledger_path) != ledger_hash:
        raise DemoExecutionError('demo_recovery_predecessor_mutation_detected')
    return {'authorization_path': str(authorization_path), 'authorization_identity': authorization['authorization_identity'],
            'expires_at': authorization['expires_at'], 'remote_reconciliation': remote_result}


def create_filled_recovery_epoch(*, predecessor_root, predecessor_checkpoint, expected_predecessor_git_commit,
                                 expected_predecessor_config_identity, target_root, target_git_commit,
                                 target_config_identity, forward_root, authorization_path, now=None):
    """Consume one valid filled-predecessor authorization without exchange access."""
    predecessor_root, predecessor_checkpoint, target_root = Path(predecessor_root).resolve(), Path(predecessor_checkpoint).resolve(), Path(target_root).resolve()
    forward_root, authorization_path = Path(forward_root).resolve(), Path(authorization_path).resolve()
    if predecessor_checkpoint != predecessor_root / 'checkpoints' / 'runtime.json' or not predecessor_checkpoint.is_file():
        raise DemoExecutionError('demo_recovery_predecessor_checkpoint_path_invalid')
    if target_root.exists() or not target_root.parent.is_dir():
        raise DemoExecutionError('demo_recovery_target_or_authorization_used')
    checkpoint_hash, ledger_path = _sha256_bytes(predecessor_checkpoint), predecessor_root / 'runtime' / 'ledger.json'
    if not ledger_path.is_file(): raise DemoExecutionError('demo_recovery_predecessor_ledger_missing')
    ledger_hash = _sha256_bytes(ledger_path)
    checkpoint, rows, authorization = _read_json(predecessor_checkpoint, 'checkpoint'), _read_json(ledger_path, 'ledger'), _read_json(authorization_path, 'authorization')
    predecessor_git = _require_sha(expected_predecessor_git_commit, 'predecessor_git_commit', 40)
    predecessor_config = _require_sha(expected_predecessor_config_identity, 'predecessor_config_identity', 64)
    target_git = _require_sha(target_git_commit, 'target_git_commit', 40)
    target_config = _require_sha(target_config_identity, 'target_config_identity', 64)
    _validate_checkpoint(checkpoint, expected_git_commit=predecessor_git, expected_config_identity=predecessor_config, require_zero_fills=False); _filled_predecessor(checkpoint, rows)
    if not isinstance(authorization, dict) or authorization.get('schema_version') != FILLED_AUTHORIZATION_SCHEMA or authorization.get('authorization_identity') != identity({key: value for key, value in authorization.items() if key != 'authorization_identity'}):
        raise DemoExecutionError('demo_recovery_authorization_invalid')
    verified_at, expires_at, current = _parse_timestamp(authorization.get('verified_at'), 'authorization_timestamp'), _parse_timestamp(authorization.get('expires_at'), 'authorization_expiry'), _parse_timestamp(now or utc_now(), 'authorization_now')
    if current < verified_at or current > expires_at:
        raise DemoExecutionError('demo_recovery_authorization_stale')
    expected = {'predecessor_epoch': checkpoint.get('demo_epoch'), 'predecessor_root': str(predecessor_root),
                'predecessor_checkpoint_identity': checkpoint.get('checkpoint_identity'), 'predecessor_checkpoint_sha256': checkpoint_hash,
                'predecessor_ledger_sha256': ledger_hash, 'predecessor_cursor': checkpoint.get('last_signal_cursor'),
                'predecessor_git_commit': predecessor_git, 'predecessor_config_identity': predecessor_config,
                'source_forward_identity': identity({'root': str(forward_root)}), 'forward_root': str(forward_root),
                'target_git_commit': target_git, 'target_config_identity': target_config, 'authorized_target_root': str(target_root), 'predecessor_executed_fills': True,
                'old_intents_not_replayed': True}
    if any(authorization.get(key) != value for key, value in expected.items()) or not isinstance(authorization.get('remote_reconciliation'), dict) or authorization['remote_reconciliation'].get('open_orders') != 0:
        raise DemoExecutionError('demo_recovery_authorization_provenance_mismatch')
    claim_path, claim = _claim_authorization(authorization_path, authorization['authorization_identity'], target_root)
    provenance = {'schema_version': 'quantbot-demo-recovery-v1', **expected, 'recovery_reason': authorization.get('recovery_reason'),
                  'filled_recovery_authorization_identity': authorization['authorization_identity'],
                  'filled_recovery_authorization_claim_identity': claim['claim_identity'],
                  'remote_reconciliation': authorization['remote_reconciliation']}
    provenance['recovery_identity'] = identity(provenance)
    staging_root, persistence = target_root.parent / f'.{target_root.name}.recovery-staging-{uuid.uuid4().hex}', None
    try:
        staging_root.mkdir(); persistence = DemoPersistence(staging_root); persistence.append('recovery', utc_now()[:10], provenance)
        new_checkpoint = {'schema_version': CHECKPOINT_SCHEMA, 'git_commit': target_git, 'demo_epoch': target_root.name,
                          'demo_epoch_start': utc_now(), 'config_identity': target_config, 'source_forward_identity': expected['source_forward_identity'],
                          'last_signal_cursor': checkpoint['last_signal_cursor'], 'orders_seen': 0, 'fills_seen': 0, 'reconciliation': {}, 'fail_closed': False,
                          'runtime_health': {'live_order_endpoint_allowed': False}, 'recovery': provenance}
        new_checkpoint['checkpoint_identity'] = identity(new_checkpoint); persistence.write_checkpoint(new_checkpoint); persistence.flush(); persistence.close()
        staged_checkpoint = _read_json(staging_root / 'checkpoints' / 'runtime.json', 'staged_checkpoint')
        if staged_checkpoint.get('checkpoint_identity') != identity({key: value for key, value in staged_checkpoint.items() if key != 'checkpoint_identity'}): raise DemoExecutionError('demo_recovery_staged_checkpoint_identity_invalid')
        if _sha256_bytes(predecessor_checkpoint) != checkpoint_hash or _sha256_bytes(ledger_path) != ledger_hash: raise DemoExecutionError('demo_recovery_predecessor_mutation_detected')
        staging_root.rename(target_root)
    except DemoExecutionError:
        if persistence is not None:
            try:persistence.close()
            except Exception:pass
        if staging_root.exists(): shutil.rmtree(staging_root)
        raise
    except Exception as exc:
        if persistence is not None:
            try:persistence.close()
            except Exception:pass
        if staging_root.exists(): shutil.rmtree(staging_root)
        raise DemoExecutionError('demo_recovery_target_write_failed') from exc
    return {'target_root': str(target_root), 'checkpoint_identity': new_checkpoint['checkpoint_identity'],
            'recovery_identity': provenance['recovery_identity'], 'authorization_identity': authorization['authorization_identity'],
            'cursor': checkpoint['last_signal_cursor']}
