"""Explicit, create-only recovery epoch construction for Demo fail-closed state."""
from __future__ import annotations

import hashlib
import json
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


def _validate_checkpoint(checkpoint: dict, *, expected_git_commit: str, expected_config_identity: str) -> None:
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
    if type(checkpoint.get('fills_seen')) is not int or checkpoint['fills_seen'] != 0:
        raise DemoExecutionError('demo_recovery_predecessor_fills_not_safe')


def _validate_ledger(rows) -> None:
    if not isinstance(rows, dict):
        raise DemoExecutionError('demo_recovery_ledger_invalid')
    for signal_identity, row in rows.items():
        if not isinstance(signal_identity, str) or not isinstance(row, dict) or row.get('state') not in SAFE_PREDECESSOR_STATES:
            raise DemoExecutionError('demo_recovery_predecessor_execution_ambiguity')


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
    if target_root.exists():
        raise DemoExecutionError('demo_recovery_target_root_exists')

    checkpoint_hash_before = _sha256_bytes(predecessor_checkpoint)
    ledger_hash_before = _sha256_bytes(ledger_path)
    checkpoint = _read_json(predecessor_checkpoint, 'checkpoint')
    ledger_rows = _read_json(ledger_path, 'ledger')
    _validate_checkpoint(checkpoint, expected_git_commit=expected_predecessor_git_commit,
                         expected_config_identity=expected_predecessor_config_identity)
    _validate_ledger(ledger_rows)

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
        'target_git_commit': target_git_commit,
        'target_config_identity': target_config_identity,
        'recovery_reason': recovery_reason,
        'old_intents_not_replayed': True,
    }
    provenance['recovery_identity'] = identity(provenance)
    target_root.mkdir(parents=True, exist_ok=False)
    persistence = DemoPersistence(target_root)
    try:
        persistence.append('recovery', utc_now()[:10], provenance)
        new_checkpoint = {
            'schema_version': CHECKPOINT_SCHEMA,
            'git_commit': target_git_commit,
            'demo_epoch': target_root.name,
            'demo_epoch_start': utc_now(),
            'config_identity': target_config_identity,
            'source_forward_identity': identity({'root': str(Path(forward_root))}),
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
    finally:
        persistence.close()
    if _sha256_bytes(predecessor_checkpoint) != checkpoint_hash_before or _sha256_bytes(ledger_path) != ledger_hash_before:
        raise DemoExecutionError('demo_recovery_predecessor_mutation_detected')
    return {'target_root': str(target_root), 'checkpoint_identity': new_checkpoint['checkpoint_identity'],
            'recovery_identity': provenance['recovery_identity'], 'cursor': checkpoint['last_signal_cursor']}
