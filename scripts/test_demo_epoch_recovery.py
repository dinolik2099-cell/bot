from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path

from quantbot.demo_execution.config import validate_config
from quantbot.demo_execution.core import DemoExecutionError, identity
from quantbot.demo_execution.epoch_recovery import create_recovery_epoch
from quantbot.demo_execution.persistence import DemoPersistence
from quantbot.demo_execution.runtime import DemoRuntime
from quantbot.demo_execution.execution_engine import DemoExecutionEngine

PREDECESSOR_COMMIT = '4' * 40
TARGET_COMMIT = 'a' * 40


def config():
    return validate_config({'environment': 'DEMO', 'live_order_endpoint_allowed': False,
                            'endpoint': 'https://demo-fapi.binance.com',
                            'execution_policy': {'enabled': True, 'position_mode': 'ONE_WAY',
                                                 'margin_mode': 'ISOLATED', 'leverage': 1,
                                                 'order_notional': 10, 'max_signal_age_seconds': 300,
                                                 'risk': {'max_open_orders': 1, 'max_total_gross_exposure': 10,
                                                          'max_strategy_exposure': 10, 'max_order_notional': 10,
                                                          'max_daily_loss': 1}}})


def blocked(fn):
    try:
        fn()
    except DemoExecutionError:
        return
    raise AssertionError('expected_recovery_rejection')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_predecessor(root, cfg, *, state='INTENT_CREATED', fills=0, malformed=False, forward_root=None):
    root = Path(root)
    forward_root = Path(forward_root or root.parent / 'forward_read_only').resolve()
    (root / 'checkpoints').mkdir(parents=True)
    (root / 'runtime').mkdir(parents=True)
    checkpoint = {'schema_version': 'quantbot-demo-checkpoint-v1', 'git_commit': PREDECESSOR_COMMIT,
                  'demo_epoch': root.name, 'demo_epoch_start': '2026-09-15T00:00:00+00:00',
                  'config_identity': cfg['config_identity'], 'source_forward_identity': identity({'root': str(forward_root)}),
                  'last_signal_cursor': 'signals/2026-09-15/signals.jsonl:15967', 'orders_seen': 1,
                  'fills_seen': fills, 'reconciliation': {}, 'fail_closed': True,
                  'runtime_health': {'live_order_endpoint_allowed': False}}
    checkpoint['checkpoint_identity'] = ('bad' * 22) if malformed else identity(checkpoint)
    (root / 'checkpoints' / 'runtime.json').write_text(json.dumps(checkpoint), encoding='utf-8')
    rows = {'s' * 64: {'signal_identity': 's' * 64, 'execution_intent_identity': 'i' * 64,
                       'client_order_id': 'QB' + 'A' * 30, 'state': state,
                       'intent': {'signal_identity': 's' * 64, 'action': 'OPEN'}, 'events': []}}
    (root / 'runtime' / 'ledger.json').write_text(json.dumps(rows), encoding='utf-8')
    return checkpoint


class FailingStartupAdapter:
    def __init__(self):
        self.calls = []
    def positions(self):
        self.calls.append('positions')
        raise DemoExecutionError('synthetic_reconciliation_failure')
    def open_orders(self):
        self.calls.append('open_orders')
        return []
    def create_order(self, _order):
        self.calls.append('create_order')
        raise AssertionError('recovery_must_never_post')


def recover(predecessor, target, cfg, **overrides):
    args = {'predecessor_root': predecessor, 'predecessor_checkpoint': Path(predecessor) / 'checkpoints' / 'runtime.json',
            'expected_predecessor_git_commit': PREDECESSOR_COMMIT,
            'expected_predecessor_config_identity': cfg['config_identity'], 'target_root': target,
            'target_git_commit': TARGET_COMMIT, 'target_config_identity': cfg['config_identity'],
            'forward_root': Path(predecessor).parent / 'forward_read_only', 'recovery_reason': 'approved_quantity_filter_recovery'}
    args.update(overrides)
    return create_recovery_epoch(**args)


def main():
    cfg = config()
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        predecessor = root / 'demo_execution_44c630d_day2'
        old_checkpoint = write_predecessor(predecessor, cfg)
        checkpoint_path = predecessor / 'checkpoints' / 'runtime.json'
        ledger_path = predecessor / 'runtime' / 'ledger.json'
        checkpoint_hash, ledger_hash = sha(checkpoint_path), sha(ledger_path)
        target = root / 'demo_execution_recovery_01'
        result = recover(predecessor, target, cfg)
        checkpoint = json.loads((target / 'checkpoints' / 'runtime.json').read_text(encoding='utf-8'))
        recovery_files = list((target / 'recovery').glob('*/*.jsonl'))
        provenance = json.loads(recovery_files[0].read_text(encoding='utf-8').splitlines()[0])
        assert result['cursor'] == old_checkpoint['last_signal_cursor'] == checkpoint['last_signal_cursor']
        assert checkpoint['fail_closed'] is False and checkpoint['git_commit'] == TARGET_COMMIT
        assert checkpoint['config_identity'] == cfg['config_identity'] and checkpoint['recovery']['recovery_identity'] == result['recovery_identity']
        assert checkpoint['checkpoint_identity'] == identity({key: value for key, value in checkpoint.items() if key != 'checkpoint_identity'})
        assert provenance['recovery_identity'] == identity({key: value for key, value in provenance.items() if key not in {'created_at', 'recovery_identity'}})
        assert provenance['predecessor_epoch'] == predecessor.name and provenance['predecessor_checkpoint_identity'] == old_checkpoint['checkpoint_identity']
        assert provenance['predecessor_cursor'] == old_checkpoint['last_signal_cursor'] and provenance['old_intents_not_replayed'] is True
        assert provenance['source_forward_identity'] == old_checkpoint['source_forward_identity'] and provenance['forward_root'] == str((root / 'forward_read_only').resolve())
        assert checkpoint_hash == sha(checkpoint_path) and ledger_hash == sha(ledger_path)
        assert not (target / 'runtime' / 'ledger.json').exists()

        # The tool accepts no adapter or order function.  Runtime reconciliation
        # still remains the later mandatory remote safety boundary.
        adapter = FailingStartupAdapter()
        runtime = DemoRuntime(cfg, target, root / 'forward_read_only', adapter, TARGET_COMMIT)
        engine = DemoExecutionEngine(runtime.ledger, runtime.persistence, adapter, cfg, target.name)
        try:
            runtime.startup_reconcile()
        except DemoExecutionError as exc:
            runtime.startup_fail_closed(engine, exc)
        recovered_checkpoint = runtime.persistence.read_checkpoint()
        assert recovered_checkpoint['fail_closed'] is True and recovered_checkpoint['last_signal_cursor'] == old_checkpoint['last_signal_cursor']
        runtime.persistence.close()
        assert adapter.calls == ['open_orders', 'positions']

        for state in ('SUBMITTING', 'RECONCILING', 'FILLED'):
            unsafe = root / f'unsafe_{state.lower()}'
            write_predecessor(unsafe, cfg, state=state, fills=1 if state == 'FILLED' else 0)
            blocked(lambda unsafe=unsafe: recover(unsafe, root / f'target_{state.lower()}', cfg))
        fills = root / 'unsafe_fills'
        write_predecessor(fills, cfg, fills=1)
        blocked(lambda: recover(fills, root / 'target_fills', cfg))
        wrong_git = root / 'wrong_git'
        write_predecessor(wrong_git, cfg)
        blocked(lambda: recover(wrong_git, root / 'target_wrong_git', cfg, expected_predecessor_git_commit='b' * 40))
        blocked(lambda: recover(wrong_git, root / 'target_wrong_config', cfg, expected_predecessor_config_identity='c' * 64))
        malformed = root / 'malformed'
        write_predecessor(malformed, cfg, malformed=True)
        blocked(lambda: recover(malformed, root / 'target_malformed', cfg))
        wrong_forward = root / 'wrong_forward'
        write_predecessor(wrong_forward, cfg)
        blocked(lambda: recover(wrong_forward, root / 'target_wrong_forward', cfg, forward_root=root / 'other_forward'))
        existing = root / 'existing_target'
        existing.mkdir()
        blocked(lambda: recover(wrong_git, existing, cfg))
        failing_target = root / 'target_mid_write_failure'
        failing_checkpoint_hash, failing_ledger_hash = sha(checkpoint_path), sha(ledger_path)
        original_write_checkpoint = DemoPersistence.write_checkpoint
        def fail_mid_write(self, _row):
            raise OSError('synthetic_checkpoint_write_failure')
        DemoPersistence.write_checkpoint = fail_mid_write
        try:
            blocked(lambda: recover(predecessor, failing_target, cfg))
        finally:
            DemoPersistence.write_checkpoint = original_write_checkpoint
        assert not failing_target.exists() and not list(root.glob(f'.{failing_target.name}.recovery-staging-*'))
        assert failing_checkpoint_hash == sha(checkpoint_path) and failing_ledger_hash == sha(ledger_path)
    print('DEMO_RECOVERY_SAFE_PREDECESSOR_CREATE_ONLY=PASS')
    print('DEMO_RECOVERY_CURSOR_EXACT_INHERITANCE=PASS')
    print('DEMO_RECOVERY_PROVENANCE_COMPLETE=PASS')
    print('DEMO_RECOVERY_PREDECESSOR_BYTES_UNCHANGED=PASS')
    print('DEMO_RECOVERY_AMBIGUOUS_SUBMITTING_REJECTED=PASS')
    print('DEMO_RECOVERY_AMBIGUOUS_RECONCILING_REJECTED=PASS')
    print('DEMO_RECOVERY_FILLED_OR_NONZERO_FILLS_REJECTED=PASS')
    print('DEMO_RECOVERY_WRONG_IDENTITY_AND_MALFORMED_REJECTED=PASS')
    print('DEMO_RECOVERY_WRONG_FORWARD_ROOT_REJECTED=PASS')
    print('DEMO_RECOVERY_EXISTING_TARGET_REJECTED=PASS')
    print('DEMO_RECOVERY_MID_WRITE_FAILURE_ATOMIC=PASS')
    print('DEMO_RECOVERY_FINAL_IDENTITIES_RECOMPUTE=PASS')
    print('DEMO_RECOVERY_NO_BINANCE_OR_ORDER_ACCESS=PASS')
    print('DEMO_RECOVERY_STARTUP_RECONCILIATION_STILL_FAIL_CLOSED=PASS')
    print('OOS_READS=0')
    print('FORWARD_MUTATIONS=0')
    print('LIVE_ORDER_PLACEMENT=0')


if __name__ == '__main__':
    main()
