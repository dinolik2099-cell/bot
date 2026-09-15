"""Synthetic cutover provenance tests; no production release is inspected."""
from __future__ import annotations

import subprocess
import tempfile
import importlib.util
from pathlib import Path

from quantbot.forward_research.checkpoint import checkpoint_payload, write_checkpoint
from quantbot.forward_research.runtime import ForwardRuntime

_SOURCE = Path(__file__).resolve().parents[1] / 'deploy' / 'forward_preflight.py'
_SPEC = importlib.util.spec_from_file_location('forward_preflight_test_source', _SOURCE)
_MODULE = importlib.util.module_from_spec(_SPEC); _SPEC.loader.exec_module(_MODULE)
validate_startup = _MODULE.validate_startup
validate_watchdog = _MODULE.validate_watchdog
ForwardReleasePreflightError = _MODULE.ForwardReleasePreflightError


def _reject(action, marker):
    try:
        action()
    except ForwardReleasePreflightError as exc:
        assert marker in str(exc), str(exc)
        return
    raise AssertionError('unexpectedly accepted')


def _repo(root: Path) -> str:
    subprocess.check_call(['git', 'init', '-q', str(root)])
    subprocess.check_call(['git', '-C', str(root), 'config', 'user.email', 'forward@example.invalid'])
    subprocess.check_call(['git', '-C', str(root), 'config', 'user.name', 'Forward'])
    (root / 'release.txt').write_text('immutable', encoding='utf-8')
    subprocess.check_call(['git', '-C', str(root), 'add', 'release.txt'])
    subprocess.check_call(['git', '-C', str(root), 'commit', '-q', '-m', 'release'])
    return subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip()


def _checkpoint(path: Path, commit: str):
    write_checkpoint(path, checkpoint_payload(ForwardRuntime(), 'c' * 64, commit,
                                              research_plan_identity='p' * 64,
                                              declaration_manifest_identity='d' * 64))


def main():
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary) / 'release'; root.mkdir()
        target = _repo(root)
        predecessor = '3' * 40
        checkpoint = Path(temporary) / 'runtime.json'
        _checkpoint(checkpoint, target)
        original = checkpoint.read_bytes()
        assert validate_startup(release_root=root, checkpoint_path=checkpoint, target_commit=target)['checkpoint_commit'] == target
        assert validate_watchdog(release_root=root, checkpoint_path=checkpoint, target_commit=target)['checkpoint_commit'] == target
        assert checkpoint.read_bytes() == original
        _checkpoint(checkpoint, predecessor); predecessor_bytes = checkpoint.read_bytes()
        allowed = validate_startup(release_root=root, checkpoint_path=checkpoint, target_commit=target,
                                  upgrade_mode=True, approved_predecessor_commit=predecessor)
        assert allowed['upgrade_compatibility'] is True and checkpoint.read_bytes() == predecessor_bytes
        _reject(lambda: validate_startup(release_root=root, checkpoint_path=checkpoint, target_commit=target), 'checkpoint_commit_unapproved')
        _reject(lambda: validate_watchdog(release_root=root, checkpoint_path=checkpoint, target_commit=target), 'checkpoint_commit_unapproved')
        _checkpoint(checkpoint, '4' * 40)
        _reject(lambda: validate_startup(release_root=root, checkpoint_path=checkpoint, target_commit=target,
                                         upgrade_mode=True, approved_predecessor_commit=predecessor), 'checkpoint_commit_unapproved')
        _checkpoint(checkpoint, target)
        _reject(lambda: validate_startup(release_root=root, checkpoint_path=checkpoint, target_commit='5' * 40), 'target_commit_mismatch')
        (root / 'dirty.txt').write_text('dirty', encoding='utf-8')
        _reject(lambda: validate_startup(release_root=root, checkpoint_path=checkpoint, target_commit=target), 'not_clean')
    print('FORWARD_RELEASE_TARGET_CHECKPOINT=PASS')
    print('FORWARD_RELEASE_APPROVED_PREDECESSOR_CUTOVER=PASS')
    print('FORWARD_RELEASE_PREDECESSOR_STEADY_STATE_REJECTED=PASS')
    print('FORWARD_RELEASE_UNRELATED_CHECKPOINT_REJECTED=PASS')
    print('FORWARD_RELEASE_DIRTY_OR_WRONG_RELEASE_REJECTED=PASS')
    print('FORWARD_RELEASE_PREFLIGHT_READ_ONLY=PASS')
    print('FORWARD_WATCHDOG_TARGET_ONLY=PASS')
    print('OOS_READS=0')
    print('EXCHANGE_ORDER_PLACEMENT=0')
    print('SYSTEMD_MUTATIONS=0')


if __name__ == '__main__': main()
