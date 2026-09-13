"""Synthetic-only checks for the detached-worktree recovery launcher."""
from __future__ import annotations
import tempfile
from pathlib import Path
from unittest.mock import patch

from recover_historical_stress import SOURCE_COMMIT,HIGH_FAILED_CHUNK,ensure_detached_worktree,BOOTSTRAP


def main():
    assert SOURCE_COMMIT=='b1062cbb28d7407479286a6f171ca13aa77cf992'
    assert HIGH_FAILED_CHUNK=='1f19a7078d61ef8e4918fca8af968b896f7c436f5048b29b13d3a3c5cbb7ec70'
    # The bootstrap is deliberately an external launcher: it imports the
    # historical worktree's canonical CLI + run_authorized_stress rather than
    # injecting an evaluator or calling the private chunk coordinator.
    assert 'stress_runner.run_authorized_stress' in BOOTSTRAP and '_execute_stress_chunks' not in BOOTSTRAP
    assert 'resolve_canonical_runtime(runtime)' in BOOTSTRAP
    assert "state.completed_chunks,()" in BOOTSTRAP
    assert "len(state.completed_chunks)!=11" in BOOTSTRAP
    assert "len(output.state.completed_chunks)!=12" in BOOTSTRAP
    assert "target.open('x'" in BOOTSTRAP
    assert 'external_historical_recovery_observer' in BOOTSTRAP and 'raise' in BOOTSTRAP
    assert 'historical_stress_recovery_original_overwrite_forbidden' in Path('scripts/recover_historical_stress.py').read_text(encoding='utf-8')
    calls=[]
    with tempfile.TemporaryDirectory() as root:
        repo=Path(root)/'repo';repo.mkdir();worktree=Path(root)/'b106'
        with patch('recover_historical_stress._git',side_effect=lambda *parts:calls.append(parts)):
            ensure_detached_worktree(repo,worktree,SOURCE_COMMIT)
    assert calls==[(repo,'cat-file','-e',SOURCE_COMMIT),(repo,'worktree','add','--detach',str(worktree),SOURCE_COMMIT)]
    print('HISTORICAL_STRESS_RECOVERY_SYNTHETIC_TEST_OK')
    print('FAILED_ONLY_RETRY_STATE=PASS')
    print('DETACHED_SOURCE_COMMIT_FENCE=PASS')
    print('CREATE_ONLY_RECOVERY_ARTIFACT=PASS')
    print('OOS_READS=0');print('FORMAL_STRESS_RUNS=0')


if __name__=='__main__':main()
