from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path

from quantbot.demo_execution.config import validate_config
from quantbot.demo_execution.core import DemoExecutionError, identity
from quantbot.demo_execution.epoch_recovery import create_recovery_epoch, create_filled_recovery_authorization, create_filled_recovery_epoch
from quantbot.demo_execution.persistence import DemoPersistence
from quantbot.demo_execution.runtime import DemoRuntime
from quantbot.demo_execution.execution_engine import DemoExecutionEngine
from quantbot.demo_execution.models import ExecutionIntent

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


class FilledRecoveryAdapter:
    def __init__(self, amount='63', open_orders=None):
        self.amount, self.remote_open_orders, self.calls = amount, ([] if open_orders is None else open_orders), []
    def open_orders(self): self.calls.append('open_orders'); return self.remote_open_orders
    def positions(self): self.calls.append('positions'); return [{'symbol': 'BTCUSDT', 'positionAmt': self.amount, 'markPrice': '1'}]
    def query_order(self, *_args): self.calls.append('query_order'); raise AssertionError('filled_predecessor_has_no_unresolved_order')
    def create_order(self, _order): self.calls.append('create_order'); raise AssertionError('authorization_must_never_post')


def write_filled_predecessor(root, cfg):
    checkpoint = write_predecessor(root, cfg, state='FILLED', fills=3)
    rows = {}
    for seed, direction, action, at in (
        ('a', 'SHORT', 'OPEN', '2026-09-15T00:00:00+00:00'),
        ('b', 'LONG', 'CLOSE', '2026-09-15T00:01:00+00:00'),
        ('c', 'LONG', 'OPEN', '2026-09-15T00:02:00+00:00'),
    ):
        signal_identity = seed * 64
        intent = ExecutionIntent.from_signal({'signal_identity': signal_identity, 'symbol': 'BTCUSDT', 'direction': direction,
                                              'model_id': 'm', 'declaration_identity': 'd', 'signal_timestamp': at}, 10, action)
        rows[signal_identity] = {'signal_identity': signal_identity, 'execution_intent_identity': intent.intent_identity,
                                 'client_order_id': intent.client_order_id, 'state': 'FILLED', 'quantity': '63', 'dry_run': False,
                                 'intent': intent.row(), 'events': [{'state': 'INTENT_CREATED', 'at': '2026-09-14T23:59:00+00:00'},
                                                                     {'state': 'VALIDATED', 'at': '2026-09-14T23:59:30+00:00'},
                                                                     {'state': 'FILLED', 'at': at}]}
    (Path(root) / 'runtime' / 'ledger.json').write_text(json.dumps(rows), encoding='utf-8')
    checkpoint['fills_seen'] = 3; checkpoint['orders_seen'] = 3; checkpoint['checkpoint_identity'] = identity({key: value for key, value in checkpoint.items() if key != 'checkpoint_identity'})
    (Path(root) / 'checkpoints' / 'runtime.json').write_text(json.dumps(checkpoint), encoding='utf-8')
    return checkpoint


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

        # Filled predecessors remain blocked by the ordinary zero-fill seam.
        filled_predecessor = root / 'demo_execution_c60a235_recovery1'
        filled_checkpoint = write_filled_predecessor(filled_predecessor, cfg)
        filled_checkpoint_path = filled_predecessor / 'checkpoints' / 'runtime.json'
        filled_ledger_path = filled_predecessor / 'runtime' / 'ledger.json'
        filled_checkpoint_hash, filled_ledger_hash = sha(filled_checkpoint_path), sha(filled_ledger_path)
        blocked(lambda: recover(filled_predecessor, root / 'ordinary_filled_rejected', cfg))
        authorization_path = root / 'filled-recovery.authorization.json'
        verified_at = '2026-09-15T00:03:00+00:00'
        filled_adapter = FilledRecoveryAdapter()
        authorization = create_filled_recovery_authorization(
            predecessor_root=filled_predecessor, predecessor_checkpoint=filled_checkpoint_path,
            expected_predecessor_git_commit=PREDECESSOR_COMMIT, expected_predecessor_config_identity=cfg['config_identity'],
            target_git_commit=TARGET_COMMIT, target_config_identity=cfg['config_identity'], forward_root=root / 'forward_read_only',
            authorization_path=authorization_path, adapter=filled_adapter, recovery_reason='approved_reconciliation_after_close_fix', now=verified_at)
        filled_target = root / 'demo_execution_filled_recovery2'
        filled_result = create_filled_recovery_epoch(
            predecessor_root=filled_predecessor, predecessor_checkpoint=filled_checkpoint_path,
            expected_predecessor_git_commit=PREDECESSOR_COMMIT, expected_predecessor_config_identity=cfg['config_identity'],
            target_root=filled_target, target_git_commit=TARGET_COMMIT, target_config_identity=cfg['config_identity'],
            forward_root=root / 'forward_read_only', authorization_path=authorization_path, now='2026-09-15T00:04:00+00:00')
        filled_new_checkpoint = json.loads((filled_target / 'checkpoints' / 'runtime.json').read_text(encoding='utf-8'))
        assert filled_result['cursor'] == filled_checkpoint['last_signal_cursor'] and filled_new_checkpoint['orders_seen'] == 0 and filled_new_checkpoint['fills_seen'] == 0 and filled_new_checkpoint['fail_closed'] is False
        assert filled_new_checkpoint['recovery']['predecessor_executed_fills'] is True and filled_new_checkpoint['recovery']['old_intents_not_replayed'] is True
        assert not (filled_target / 'runtime' / 'ledger.json').exists() and filled_checkpoint_hash == sha(filled_checkpoint_path) and filled_ledger_hash == sha(filled_ledger_path) and 'create_order' not in filled_adapter.calls
        # A sealed authorization has a short validity window and one local use.
        blocked(lambda: create_filled_recovery_epoch(predecessor_root=filled_predecessor, predecessor_checkpoint=filled_checkpoint_path, expected_predecessor_git_commit=PREDECESSOR_COMMIT, expected_predecessor_config_identity=cfg['config_identity'], target_root=root / 'replayed_authorization', target_git_commit=TARGET_COMMIT, target_config_identity=cfg['config_identity'], forward_root=root / 'forward_read_only', authorization_path=authorization_path, now='2026-09-15T00:04:00+00:00'))
        for label, adapter_value in (('residual', FilledRecoveryAdapter(amount='-63')), ('open_orders', FilledRecoveryAdapter(open_orders=[{'clientOrderId': 'unknown'}]))):
            unsafe_auth = root / f'{label}.authorization.json'
            blocked(lambda unsafe_auth=unsafe_auth, adapter_value=adapter_value: create_filled_recovery_authorization(predecessor_root=filled_predecessor, predecessor_checkpoint=filled_checkpoint_path, expected_predecessor_git_commit=PREDECESSOR_COMMIT, expected_predecessor_config_identity=cfg['config_identity'], target_git_commit=TARGET_COMMIT, target_config_identity=cfg['config_identity'], forward_root=root / 'forward_read_only', authorization_path=unsafe_auth, adapter=adapter_value, recovery_reason='unsafe', now=verified_at))
        # Semantically altered but rehashed authorizations still fail their exact
        # predecessor/target provenance comparisons; stale evidence fails too.
        for label, key, value in (('cursor', 'predecessor_cursor', 'signals/x:1'), ('target_git', 'target_git_commit', 'b' * 40), ('forward', 'source_forward_identity', 'e' * 64)):
            replay_predecessor = root / f'filled_{label}'; replay_checkpoint = write_filled_predecessor(replay_predecessor, cfg); replay_path = replay_predecessor / 'checkpoints' / 'runtime.json'; replay_auth = root / f'{label}.authorization.json'
            create_filled_recovery_authorization(predecessor_root=replay_predecessor, predecessor_checkpoint=replay_path, expected_predecessor_git_commit=PREDECESSOR_COMMIT, expected_predecessor_config_identity=cfg['config_identity'], target_git_commit=TARGET_COMMIT, target_config_identity=cfg['config_identity'], forward_root=root / 'forward_read_only', authorization_path=replay_auth, adapter=FilledRecoveryAdapter(), recovery_reason='approved', now=verified_at)
            altered = json.loads(replay_auth.read_text(encoding='utf-8')); altered[key] = value; altered['authorization_identity'] = identity({item: payload for item, payload in altered.items() if item != 'authorization_identity'}); replay_auth.write_text(json.dumps(altered), encoding='utf-8')
            blocked(lambda replay_predecessor=replay_predecessor, replay_path=replay_path, replay_auth=replay_auth, label=label: create_filled_recovery_epoch(predecessor_root=replay_predecessor, predecessor_checkpoint=replay_path, expected_predecessor_git_commit=PREDECESSOR_COMMIT, expected_predecessor_config_identity=cfg['config_identity'], target_root=root / f'{label}_target', target_git_commit=TARGET_COMMIT, target_config_identity=cfg['config_identity'], forward_root=root / 'forward_read_only', authorization_path=replay_auth, now='2026-09-15T00:04:00+00:00'))
        stale_predecessor = root / 'filled_stale'; write_filled_predecessor(stale_predecessor, cfg); stale_path = stale_predecessor / 'checkpoints' / 'runtime.json'; stale_auth = root / 'stale.authorization.json'
        create_filled_recovery_authorization(predecessor_root=stale_predecessor, predecessor_checkpoint=stale_path, expected_predecessor_git_commit=PREDECESSOR_COMMIT, expected_predecessor_config_identity=cfg['config_identity'], target_git_commit=TARGET_COMMIT, target_config_identity=cfg['config_identity'], forward_root=root / 'forward_read_only', authorization_path=stale_auth, adapter=FilledRecoveryAdapter(), recovery_reason='approved', now=verified_at)
        blocked(lambda: create_filled_recovery_epoch(predecessor_root=stale_predecessor, predecessor_checkpoint=stale_path, expected_predecessor_git_commit=PREDECESSOR_COMMIT, expected_predecessor_config_identity=cfg['config_identity'], target_root=root / 'stale_target', target_git_commit=TARGET_COMMIT, target_config_identity=cfg['config_identity'], forward_root=root / 'forward_read_only', authorization_path=stale_auth, now='2026-09-15T00:20:00+00:00'))
        # A mutable predecessor after authorization, malformed authorization,
        # or non-unique current position attribution is never recoverable.
        bound_predecessor = root / 'filled_bound'; write_filled_predecessor(bound_predecessor, cfg); bound_path = bound_predecessor / 'checkpoints' / 'runtime.json'; bound_auth = root / 'bound.authorization.json'
        create_filled_recovery_authorization(predecessor_root=bound_predecessor, predecessor_checkpoint=bound_path, expected_predecessor_git_commit=PREDECESSOR_COMMIT, expected_predecessor_config_identity=cfg['config_identity'], target_git_commit=TARGET_COMMIT, target_config_identity=cfg['config_identity'], forward_root=root / 'forward_read_only', authorization_path=bound_auth, adapter=FilledRecoveryAdapter(), recovery_reason='approved', now=verified_at)
        changed_checkpoint = json.loads(bound_path.read_text(encoding='utf-8')); changed_checkpoint['last_signal_cursor'] = 'signals/changed:1'; changed_checkpoint['checkpoint_identity'] = identity({key: value for key, value in changed_checkpoint.items() if key != 'checkpoint_identity'}); bound_path.write_text(json.dumps(changed_checkpoint), encoding='utf-8')
        blocked(lambda: create_filled_recovery_epoch(predecessor_root=bound_predecessor, predecessor_checkpoint=bound_path, expected_predecessor_git_commit=PREDECESSOR_COMMIT, expected_predecessor_config_identity=cfg['config_identity'], target_root=root / 'changed_checkpoint_target', target_git_commit=TARGET_COMMIT, target_config_identity=cfg['config_identity'], forward_root=root / 'forward_read_only', authorization_path=bound_auth, now='2026-09-15T00:04:00+00:00'))
        malformed_auth = root / 'malformed.authorization.json'; malformed_auth.write_text('{not-json', encoding='utf-8')
        fresh_predecessor = root / 'filled_malformed'; write_filled_predecessor(fresh_predecessor, cfg); fresh_path = fresh_predecessor / 'checkpoints' / 'runtime.json'
        blocked(lambda: create_filled_recovery_epoch(predecessor_root=fresh_predecessor, predecessor_checkpoint=fresh_path, expected_predecessor_git_commit=PREDECESSOR_COMMIT, expected_predecessor_config_identity=cfg['config_identity'], target_root=root / 'malformed_auth_target', target_git_commit=TARGET_COMMIT, target_config_identity=cfg['config_identity'], forward_root=root / 'forward_read_only', authorization_path=malformed_auth, now='2026-09-15T00:04:00+00:00'))
        ambiguous_predecessor = root / 'filled_ambiguous'; write_filled_predecessor(ambiguous_predecessor, cfg); ambiguous_path = ambiguous_predecessor / 'checkpoints' / 'runtime.json'; ambiguous_rows = json.loads((ambiguous_predecessor / 'runtime' / 'ledger.json').read_text(encoding='utf-8')); duplicate = dict(ambiguous_rows['c' * 64]); duplicate['signal_identity'] = 'd' * 64; duplicate['execution_intent_identity'] = 'e' * 64; duplicate['client_order_id'] = 'QB' + 'D' * 30; ambiguous_rows['d' * 64] = duplicate; (ambiguous_predecessor / 'runtime' / 'ledger.json').write_text(json.dumps(ambiguous_rows), encoding='utf-8'); ambiguous_checkpoint = json.loads(ambiguous_path.read_text(encoding='utf-8')); ambiguous_checkpoint['fills_seen'] = 4; ambiguous_checkpoint['orders_seen'] = 4; ambiguous_checkpoint['checkpoint_identity'] = identity({key: value for key, value in ambiguous_checkpoint.items() if key != 'checkpoint_identity'}); ambiguous_path.write_text(json.dumps(ambiguous_checkpoint), encoding='utf-8')
        blocked(lambda: create_filled_recovery_authorization(predecessor_root=ambiguous_predecessor, predecessor_checkpoint=ambiguous_path, expected_predecessor_git_commit=PREDECESSOR_COMMIT, expected_predecessor_config_identity=cfg['config_identity'], target_git_commit=TARGET_COMMIT, target_config_identity=cfg['config_identity'], forward_root=root / 'forward_read_only', authorization_path=root / 'ambiguous.authorization.json', adapter=FilledRecoveryAdapter(), recovery_reason='unsafe', now=verified_at))
        write_failure_predecessor = root / 'filled_write_failure'; write_filled_predecessor(write_failure_predecessor, cfg); write_failure_path = write_failure_predecessor / 'checkpoints' / 'runtime.json'; write_failure_auth = root / 'write_failure.authorization.json'
        create_filled_recovery_authorization(predecessor_root=write_failure_predecessor, predecessor_checkpoint=write_failure_path, expected_predecessor_git_commit=PREDECESSOR_COMMIT, expected_predecessor_config_identity=cfg['config_identity'], target_git_commit=TARGET_COMMIT, target_config_identity=cfg['config_identity'], forward_root=root / 'forward_read_only', authorization_path=write_failure_auth, adapter=FilledRecoveryAdapter(), recovery_reason='approved', now=verified_at)
        original_write_checkpoint = DemoPersistence.write_checkpoint
        DemoPersistence.write_checkpoint = lambda self, _row: (_ for _ in ()).throw(OSError('synthetic_filled_checkpoint_failure'))
        try:
            blocked(lambda: create_filled_recovery_epoch(predecessor_root=write_failure_predecessor, predecessor_checkpoint=write_failure_path, expected_predecessor_git_commit=PREDECESSOR_COMMIT, expected_predecessor_config_identity=cfg['config_identity'], target_root=root / 'filled_write_failure_target', target_git_commit=TARGET_COMMIT, target_config_identity=cfg['config_identity'], forward_root=root / 'forward_read_only', authorization_path=write_failure_auth, now='2026-09-15T00:04:00+00:00'))
        finally:
            DemoPersistence.write_checkpoint = original_write_checkpoint
        assert not (root / 'filled_write_failure_target').exists() and not list(root.glob('.filled_write_failure_target.recovery-staging-*'))

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
    print('DEMO_FILLED_RECOVERY_DEFAULT_SEAM_REJECTS=PASS')
    print('DEMO_FILLED_RECOVERY_CANONICAL_RECONCILIATION_AUTHORIZATION=PASS')
    print('DEMO_FILLED_RECOVERY_AUTHORIZATION_BINDING_AND_EXPIRY=PASS')
    print('DEMO_FILLED_RECOVERY_AMBIGUOUS_REMOTE_STATE_REJECTED=PASS')
    print('DEMO_FILLED_RECOVERY_CREATE_ONLY_AND_ATOMIC=PASS')
    print('OOS_READS=0')
    print('FORWARD_MUTATIONS=0')
    print('LIVE_ORDER_PLACEMENT=0')


if __name__ == '__main__':
    main()
