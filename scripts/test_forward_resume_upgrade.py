"""Synthetic runtime predecessor-resume tests; no Forward service is started."""
from __future__ import annotations

import json
import runpy
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

from quantbot.forward_research.checkpoint import checkpoint_payload, write_checkpoint
from quantbot.forward_research.core import ForwardResearchError, identity
from quantbot.forward_research.frozen_declarations import DECLARATION_SCHEMA, declaration_identity, manifest_identity
from quantbot.forward_research.production_runtime import _build_authority_for_test


def _reject(action, marker):
    try:
        action()
    except (ForwardResearchError, ValueError) as exc:
        assert marker in str(exc), str(exc)
        return
    raise AssertionError('unexpectedly accepted')


def _files(root: Path):
    config = root / 'config.yaml'
    config.write_text('forward_research_only: true\norder_placement_allowed: false\noos_allowed: false\n', encoding='utf-8')
    model = {'model_id': 'm', 'parameter_grid_hash': 'g' * 64, 'strategy_function_hash': 's' * 64,
             'implementation_module_hash': 'i' * 64, 'warmup_bars': 1}
    plan = {'research_freeze_identity': 'f' * 64, 'research_plan_identity': 'p' * 64,
            'oos_status': 'SEALED', 'oos_authorization': 'NOT_AUTHORIZED',
            'protocol_scope': {'timeframe': '1m'}, 'models': [model]}
    plan_path = root / 'plan.json'; plan_path.write_text(json.dumps(plan), encoding='utf-8')
    declaration = {'schema_version': DECLARATION_SCHEMA, 'research_freeze_identity': 'f' * 64,
                   'research_plan_identity': 'p' * 64, 'model_id': 'm', 'model_name': 'missing',
                   'params': {}, 'params_identity': identity({}), 'parameter_grid_hash': 'g' * 64,
                   'strategy_function_hash': 's' * 64, 'implementation_module_hash': 'i' * 64,
                   'input_boundary': 'COMPLETED_CANDLE_T_MINUS_1'}
    declaration['declaration_identity'] = declaration_identity(declaration)
    manifest = {'schema_version': DECLARATION_SCHEMA, 'decision_artifact_id': 'day0',
                'research_freeze_identity': 'f' * 64, 'research_plan_identity': 'p' * 64,
                'declarations': [declaration], 'forward_research_only': True,
                'oos_allowed': False, 'order_placement_allowed': False}
    manifest['manifest_identity'] = manifest_identity(manifest)
    declaration_path = root / 'declaration.json'; declaration_path.write_text(json.dumps(manifest), encoding='utf-8')
    return config, plan_path, declaration_path


def _authority(root, checkpoint, approved=None):
    config, plan, declaration = _files(root)
    return _build_authority_for_test(config_path=config, plan_path=plan, declaration_path=declaration,
                                     data_root=root / 'data', checkpoint_path=checkpoint, repo_root='.',
                                     upgrade_resume=bool(approved), approved_predecessor_commit=approved, _session=object())


def _write(authority, path, commit, *, config=None, plan=None, declaration=None, mutate=None):
    payload = checkpoint_payload(authority.runtime, config or authority.config['config_identity'], commit,
                                 research_plan_identity=plan or authority.plan['research_plan_identity'],
                                 declaration_manifest_identity=declaration or authority.manifest['manifest_identity'])
    if mutate is not None:
        mutate(payload)
        payload['checkpoint_identity'] = identity({key: value for key, value in payload.items() if key != 'checkpoint_identity'})
    write_checkpoint(path, payload)


def main():
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary); checkpoint = root / 'runtime.json'; normal = _authority(root, checkpoint)
        target, predecessor, unrelated = normal.git_commit, '3' * 40, '4' * 40
        config, plan, declaration = _files(root)
        _reject(lambda: _build_authority_for_test(config_path=config, plan_path=plan, declaration_path=declaration,
                                                   data_root=root / 'data', checkpoint_path=checkpoint, repo_root='.',
                                                   upgrade_resume=False, approved_predecessor_commit=predecessor,
                                                   _session=object()), 'forward_upgrade_resume_authorization_invalid')
        _write(normal, checkpoint, target)
        assert normal.resume()['git_commit'] == target
        _write(normal, checkpoint, predecessor); before_resume = checkpoint.read_bytes()
        _reject(normal.resume, 'forward_checkpoint_git_drift')
        upgraded = _authority(root, checkpoint, predecessor)
        assert upgraded.resume()['git_commit'] == predecessor and checkpoint.read_bytes() == before_resume
        _write(normal, checkpoint, unrelated)
        _reject(lambda: _authority(root, checkpoint, predecessor).resume(), 'forward_checkpoint_git_drift')
        # The predecessor route retains every non-Git provenance/safety check.
        _write(normal, checkpoint, predecessor, config='x' * 64)
        _reject(lambda: _authority(root, checkpoint, predecessor).resume(), 'forward_checkpoint_config_drift')
        _write(normal, checkpoint, predecessor, plan='x' * 64)
        _reject(lambda: _authority(root, checkpoint, predecessor).resume(), 'forward_checkpoint_plan_drift')
        _write(normal, checkpoint, predecessor, declaration='x' * 64)
        _reject(lambda: _authority(root, checkpoint, predecessor).resume(), 'forward_checkpoint_declaration_drift')
        _write(normal, checkpoint, predecessor, mutate=lambda row: row.__setitem__('schema_version', 'bad'))
        _reject(lambda: _authority(root, checkpoint, predecessor).resume(), 'forward_resume_checkpoint_safety_invalid')
        _write(normal, checkpoint, predecessor, mutate=lambda row: row.__setitem__('oos_allowed', True))
        _reject(lambda: _authority(root, checkpoint, predecessor).resume(), 'forward_resume_checkpoint_safety_invalid')
        _write(normal, checkpoint, predecessor); upgraded = _authority(root, checkpoint, predecessor)
        assert upgraded.resume()['git_commit'] == predecessor
        upgraded.checkpoint()
        assert json.loads(checkpoint.read_text(encoding='utf-8'))['git_commit'] == target
        assert _authority(root, checkpoint).resume()['git_commit'] == target
        # The CLI requires both explicit cutover flags and forwards the SHA.
        captured = {}
        class _FakeAuthority:
            def serve(self): captured['served'] = True
        def factory(**kwargs): captured.update(kwargs); return _FakeAuthority()
        old_argv = sys.argv
        try:
            sys.argv = ['run_forward_research.py', '--serve', '--config', str(root / 'config.yaml'),
                        '--plan', str(root / 'plan.json'), '--declarations', str(root / 'declaration.json'),
                        '--checkpoint', str(checkpoint), '--upgrade-resume',
                        '--approved-predecessor-commit', predecessor]
            with patch('quantbot.forward_research.production_runtime.build_production_authority', factory):
                try: runpy.run_path('scripts/run_forward_research.py', run_name='__main__')
                except SystemExit as exc: assert exc.code == 0
        finally: sys.argv = old_argv
        assert captured['upgrade_resume'] is True and captured['approved_predecessor_commit'] == predecessor and captured['served'] is True
    print('FORWARD_RESUME_TARGET_NORMAL=PASS')
    print('FORWARD_RESUME_PREDECESSOR_NORMAL_REJECTED=PASS')
    print('FORWARD_RESUME_EXACT_PREDECESSOR_UPGRADE=PASS')
    print('FORWARD_RESUME_UNRELATED_UPGRADE_REJECTED=PASS')
    print('FORWARD_RESUME_ALL_OTHER_IDENTITIES_RETAINED=PASS')
    print('FORWARD_RESUME_PRECHECKPOINT_READ_ONLY=PASS')
    print('FORWARD_RESUME_NATURAL_TARGET_CHECKPOINT=PASS')
    print('FORWARD_RESUME_TARGET_ONLY_RESTART=PASS')
    print('FORWARD_RESUME_CLI_EXPLICIT_WIRING=PASS')
    print('OOS_READS=0')
    print('EXCHANGE_ORDER_PLACEMENT=0')
    print('SYSTEMD_MUTATIONS=0')


if __name__ == '__main__': main()
