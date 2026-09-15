"""Create an explicitly authorized, local-only Demo recovery epoch."""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from quantbot.demo_execution.config import load_json, validate_config
from quantbot.demo_execution.epoch_recovery import create_recovery_epoch


def current_git_commit(root: Path) -> str:
    return subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip()


def main() -> int:
    parser = argparse.ArgumentParser(description='Create a verified Demo recovery epoch without exchange access.')
    parser.add_argument('--config', required=True)
    parser.add_argument('--predecessor-root', required=True)
    parser.add_argument('--predecessor-checkpoint', required=True)
    parser.add_argument('--expected-predecessor-git-commit', required=True)
    parser.add_argument('--expected-predecessor-config-identity', required=True)
    parser.add_argument('--target-root', required=True)
    parser.add_argument('--target-git-commit', required=True)
    parser.add_argument('--expected-target-config-identity', required=True)
    parser.add_argument('--forward-root', required=True)
    parser.add_argument('--recovery-reason', required=True)
    args = parser.parse_args()
    config = validate_config(load_json(args.config))
    if config['config_identity'] != args.expected_target_config_identity:
        raise SystemExit('demo_recovery_target_config_mismatch')
    if args.target_git_commit != current_git_commit(Path.cwd()):
        raise SystemExit('demo_recovery_target_git_mismatch')
    result = create_recovery_epoch(
        predecessor_root=args.predecessor_root,
        predecessor_checkpoint=args.predecessor_checkpoint,
        expected_predecessor_git_commit=args.expected_predecessor_git_commit,
        expected_predecessor_config_identity=args.expected_predecessor_config_identity,
        target_root=args.target_root,
        target_git_commit=args.target_git_commit,
        target_config_identity=config['config_identity'],
        forward_root=args.forward_root,
        recovery_reason=args.recovery_reason,
    )
    print(json.dumps({'environment': 'DEMO', 'exchange_accessed': False, **result}, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
