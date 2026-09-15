"""Canonical, installable source for the Forward ExecStartPre release gate.

This file is self-contained except for the target release's existing
checkpoint verifier.  It can therefore be installed beside a pre-existing
immutable target release; repository tests never install or execute it there.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Mapping

_COMMIT = re.compile(r"^[0-9a-f]{40}$")


class ForwardReleasePreflightError(RuntimeError): pass


def _commit(value: str, label: str) -> str:
    if not isinstance(value, str) or not _COMMIT.fullmatch(value):
        raise ForwardReleasePreflightError(f"forward_release_{label}_invalid")
    return value


def release_state(release_root: str | Path) -> dict[str, object]:
    root = Path(release_root)
    try:
        head = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
        dirty = subprocess.check_output(["git", "-C", str(root), "status", "--porcelain", "--untracked-files=all"], text=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ForwardReleasePreflightError("forward_release_git_state_unavailable") from exc
    return {"head": _commit(head, "head"), "clean": not bool(dirty.strip())}


def _checkpoint(release_root: str | Path, path: str | Path) -> Mapping[str, object]:
    target = Path(path)
    if not target.is_file():
        raise ForwardReleasePreflightError("forward_release_checkpoint_missing")
    sys.path.insert(0, str(Path(release_root).resolve()))
    try:
        from quantbot.forward_research.checkpoint import load_checkpoint
        raw = json.loads(target.read_text(encoding="utf-8"))
        value = load_checkpoint(target)
    except (OSError, ValueError, TypeError, json.JSONDecodeError, ImportError) as exc:
        raise ForwardReleasePreflightError("forward_release_checkpoint_invalid") from exc
    if not isinstance(raw, Mapping) or value.get("schema_version") != "quantbot-forward-checkpoint-v2":
        raise ForwardReleasePreflightError("forward_release_checkpoint_invalid")
    if value.get("forward_research_only") is not True or value.get("oos_allowed") is not False:
        raise ForwardReleasePreflightError("forward_release_checkpoint_safety_invalid")
    if not isinstance(value.get("runtime"), Mapping):
        raise ForwardReleasePreflightError("forward_release_checkpoint_invalid")
    _commit(value.get("git_commit"), "checkpoint_commit")
    return value


def _validate(*, release_root: str | Path, checkpoint_path: str | Path, target_commit: str,
              accepted_checkpoint_commits: tuple[str, ...]) -> dict[str, object]:
    target = _commit(target_commit, "target_commit")
    accepted = tuple(_commit(value, "approved_predecessor") for value in accepted_checkpoint_commits)
    state = release_state(release_root)
    if state["head"] != target:
        raise ForwardReleasePreflightError("forward_release_target_commit_mismatch")
    if state["clean"] is not True:
        raise ForwardReleasePreflightError("forward_release_not_clean")
    checkpoint = _checkpoint(release_root, checkpoint_path)
    if checkpoint["git_commit"] not in accepted:
        raise ForwardReleasePreflightError("forward_release_checkpoint_commit_unapproved")
    return {"release_head": target, "checkpoint_commit": checkpoint["git_commit"],
            "upgrade_compatibility": checkpoint["git_commit"] != target,
            "checkpoint_written": False}


def validate_startup(*, release_root: str | Path, checkpoint_path: str | Path, target_commit: str,
                     upgrade_mode: bool = False, approved_predecessor_commit: str | None = None) -> dict[str, object]:
    target = _commit(target_commit, "target_commit")
    if not upgrade_mode:
        if approved_predecessor_commit is not None:
            raise ForwardReleasePreflightError("forward_release_predecessor_without_upgrade_mode")
        allowed = (target,)
    else:
        predecessor = _commit(approved_predecessor_commit, "approved_predecessor")
        if predecessor == target:
            raise ForwardReleasePreflightError("forward_release_predecessor_equals_target")
        allowed = (target, predecessor)
    return _validate(release_root=release_root, checkpoint_path=checkpoint_path,
                     target_commit=target, accepted_checkpoint_commits=allowed)


def validate_watchdog(*, release_root: str | Path, checkpoint_path: str | Path,
                      target_commit: str) -> dict[str, object]:
    target = _commit(target_commit, "target_commit")
    return _validate(release_root=release_root, checkpoint_path=checkpoint_path,
                     target_commit=target, accepted_checkpoint_commits=(target,))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release", required=True)
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--target-commit", required=True)
    parser.add_argument("--upgrade-mode", action="store_true")
    parser.add_argument("--approved-predecessor-commit")
    args = parser.parse_args()
    value = validate_startup(release_root=args.release, checkpoint_path=args.checkpoint,
                             target_commit=args.target_commit, upgrade_mode=args.upgrade_mode,
                             approved_predecessor_commit=args.approved_predecessor_commit)
    print(json.dumps({"FORWARD_RELEASE_PREFLIGHT_OK": True, **value}, sort_keys=True))
    return 0


if __name__ == "__main__": raise SystemExit(main())
