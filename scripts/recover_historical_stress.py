"""Operator launcher for provenance-clean recovery of a historical Stress run.

The launcher never imports QuantBot research code from its own checkout.  It
creates (or verifies) a detached worktree at the source commit recorded in the
frozen protocol, then starts a fresh Python process whose imports are rooted
only in that worktree.  The original execution JSON is read-only input; a new
create-only recovery artifact is the only output.
"""
from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import subprocess
import sys


SOURCE_COMMIT = "b1062cbb28d7407479286a6f171ca13aa77cf992"
HIGH_FAILED_CHUNK = "1f19a7078d61ef8e4918fca8af968b896f7c436f5048b29b13d3a3c5cbb7ec70"


BOOTSTRAP = r'''
import hashlib,json,sys
from pathlib import Path

worktree=Path(sys.argv[1]).resolve()
protocol_path,plan_path,execution_path,authority_path,raw_root,output_path,expected_commit,failed_chunk=sys.argv[2:]
# The launcher is intentionally outside the worktree.  Remove its directory
# from module lookup, then bind every QuantBot import to the historical tree.
sys.path[:]=[str(worktree)]+[item for item in sys.path if Path(item or '.').resolve()!=Path(sys.argv[0]).resolve().parent]
from quantbot.research.authorization import Capability
from quantbot.research.artifact_store import seal
from quantbot.research.future_data_plane import FutureRuntimeContext
from quantbot.research.future_stage_cli import _authority,resolve_canonical_runtime
from quantbot.research.future_stages import ResumableStageState,StageState
import quantbot.research.stress_formal_runner as stress_runner

def load(path):
    value=json.loads(Path(path).read_text(encoding='utf-8'))
    if not isinstance(value,dict):raise RuntimeError('historical_stress_recovery_json_mapping_required')
    return value

protocol,plan,original=load(protocol_path),load(plan_path),load(execution_path)
runtime=FutureRuntimeContext(protocol,plan,protocol['input_identity']);runtime.validate()
if protocol.get('stage')!='stress' or protocol.get('source_git_commit')!=expected_commit:
    raise RuntimeError('historical_stress_recovery_source_commit_mismatch')
state=runtime.validate_checkpoint(original.get('checkpoint',{}))
rows=tuple(dict(row) for row in original.get('rows',()))
if state.state!=StageState.INTERRUPTED or tuple(state.failed_chunks)!=(failed_chunk,) or len(state.completed_chunks)!=11:
    raise RuntimeError('historical_stress_recovery_original_state_invalid')
if len(rows)!=11 or {row.get('chunk_identity') for row in rows}!=set(state.completed_chunks):
    raise RuntimeError('historical_stress_recovery_completed_evidence_invalid')
# This is a new sealed retry input, not a rewrite of the original checkpoint.
# Clearing exactly the failed set exposes only that frozen ordinal as pending;
# completed identities/rows remain verbatim and are revalidated by the
# historical runner before it constructs any evaluator.
retry_state=ResumableStageState(state.protocol_identity,StageState.INTERRUPTED,state.completed_chunks,())
retry_checkpoint=runtime.checkpoint(retry_state)
authority=_authority(authority_path,Capability.TRAIN_VALIDATION)
runtime.authorize(authority,Capability.TRAIN_VALIDATION)
deps=resolve_canonical_runtime(runtime)
if deps['source_git_commit']!=expected_commit:
    raise RuntimeError('historical_stress_recovery_observed_commit_mismatch')
# b106's coordinator deliberately catches a chunk exception.  Observe the
# exception outside its sealed checkpoint without changing the evaluator or
# allowing it to return a different value: record, then immediately re-raise
# into the original coordinator.  This field is new recovery-tool evidence,
# never a claimed mutation of the original execution artifact.
external_retry_diagnostic={}
original_factory=stress_runner.make_canonical_plan_chunk_executor
def observed_factory(*args,**kwargs):
    executor=original_factory(*args,**kwargs)
    def observed(chunk):
        try:return executor(chunk)
        except Exception as exc:
            external_retry_diagnostic.update({'source':'external_historical_recovery_observer',
                'chunk_identity':chunk.get('chunk_identity'),'exception_type':type(exc).__name__,
                'exception_message':str(exc)[:4096]})
            raise
    return observed
stress_runner.make_canonical_plan_chunk_executor=observed_factory
original_worker=stress_runner._stress_chunk_worker
def observed_worker(request,chunk):
    try:return original_worker(request,chunk)
    except Exception as exc:
        external_retry_diagnostic.update({'source':'external_historical_recovery_observer',
            'chunk_identity':chunk.get('chunk_identity'),'exception_type':type(exc).__name__,
            'exception_message':str(exc)[:4096]})
        raise
stress_runner._stress_chunk_worker=observed_worker
output=stress_runner.run_authorized_stress(runtime=runtime,evidence=authority,n8_context=deps['n8'],raw_root=raw_root,
    strategy_resolver=deps['strategy_resolver'],source_git_commit=deps['source_git_commit'],checkpoint=retry_checkpoint,
    prior_rows=rows,workers='auto')
new_rows=[dict(row) for row in output.rows]
if output.state.state==StageState.COMPLETE:
    if output.state.failed_chunks or len(output.state.completed_chunks)!=12 or output.result is None:
        raise RuntimeError('historical_stress_recovery_complete_state_invalid')
    if len(new_rows)!=12 or len({row.get('chunk_identity') for row in new_rows})!=12:
        raise RuntimeError('historical_stress_recovery_row_coverage_invalid')
    runtime.validate_result(output.result)
elif output.result is not None:
    raise RuntimeError('historical_stress_recovery_partial_result_invalid')
artifact=seal({'schema_version':'quantbot-historical-stress-recovery-v1',
    'historical_source_git_commit':expected_commit,
    'original_execution_sha256':hashlib.sha256(Path(execution_path).read_bytes()).hexdigest(),
    'original_checkpoint_identity':original['checkpoint'].get('artifact_identity'),
    'retry_checkpoint_identity':retry_checkpoint.get('artifact_identity'),
    'failed_chunk_requested':failed_chunk,
    'state':{'protocol_identity':output.state.protocol_identity,'state':output.state.state.value,
             'completed_chunks':list(output.state.completed_chunks),'failed_chunks':list(output.state.failed_chunks)},
    'external_retry_diagnostic':dict(external_retry_diagnostic) if external_retry_diagnostic else None,
    'checkpoint':dict(output.checkpoint),'rows':new_rows,
    'result':dict(output.result) if output.result is not None else None,
    'oos_status':'SEALED','oos_authorization':'NOT_AUTHORIZED'})
target=Path(output_path)
target.parent.mkdir(parents=True,exist_ok=True)
with target.open('x',encoding='utf-8') as handle:
    json.dump(artifact,handle,indent=2,sort_keys=True);handle.write('\n')
print('HISTORICAL_STRESS_RECOVERY_ARTIFACT='+str(target))
print('HISTORICAL_SOURCE_GIT_COMMIT='+expected_commit)
print('RECOVERY_STATE='+output.state.state.value)
print('RECOVERY_COMPLETED='+str(len(output.state.completed_chunks)))
print('RECOVERY_FAILED='+str(len(output.state.failed_chunks)))
'''


def _git(repo_root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo_root), *args], check=True)


def ensure_detached_worktree(repo_root: Path, worktree: Path, source_commit: str) -> None:
    """Create once or prove the existing path is exactly the required commit."""
    _git(repo_root, "cat-file", "-e", source_commit)
    if worktree.exists():
        observed=subprocess.check_output(["git", "-C", str(worktree), "rev-parse", "HEAD"], text=True).strip()
        if observed != source_commit:
            raise RuntimeError("historical_stress_recovery_worktree_commit_mismatch")
        status=subprocess.check_output(["git", "-C", str(worktree), "status", "--porcelain"], text=True)
        if status.strip():
            raise RuntimeError("historical_stress_recovery_worktree_not_clean")
        return
    _git(repo_root, "worktree", "add", "--detach", str(worktree), source_commit)


def main() -> int:
    parser=argparse.ArgumentParser(description="Run one historical Stress failed-chunk recovery from its exact source commit")
    parser.add_argument("--repo-root",required=True);parser.add_argument("--worktree",required=True)
    parser.add_argument("--protocol-json",required=True);parser.add_argument("--plan-json",required=True)
    parser.add_argument("--original-execution-json",required=True);parser.add_argument("--authority-json",required=True)
    parser.add_argument("--raw-root",required=True);parser.add_argument("--output-json",required=True)
    parser.add_argument("--source-commit",default=SOURCE_COMMIT);parser.add_argument("--failed-chunk",default=HIGH_FAILED_CHUNK)
    parser.add_argument("--dry-run",action="store_true")
    args=parser.parse_args();repo=Path(args.repo_root).resolve();worktree=Path(args.worktree).resolve()
    # HIGH_FAILED_CHUNK remains the backward-compatible default. Explicit
    # failed identities are validated against the sealed original checkpoint
    # inside BOOTSTRAP before any historical evaluation can start.
    if args.source_commit!=SOURCE_COMMIT:
        raise RuntimeError("historical_stress_recovery_source_commit_mismatch")
    output=Path(args.output_json)
    if output.resolve()==Path(args.original_execution_json).resolve():
        raise RuntimeError("historical_stress_recovery_original_overwrite_forbidden")
    if output.exists():raise RuntimeError("historical_stress_recovery_output_exists")
    ensure_detached_worktree(repo,worktree,args.source_commit)
    command=[sys.executable,"-B","-c",BOOTSTRAP,str(worktree),args.protocol_json,args.plan_json,
             args.original_execution_json,args.authority_json,args.raw_root,str(output),args.source_commit,args.failed_chunk]
    print("HISTORICAL_STRESS_WORKTREE="+str(worktree));print("HISTORICAL_SOURCE_GIT_COMMIT="+args.source_commit)
    if args.dry_run:
        print("HISTORICAL_STRESS_RECOVERY_DRY_RUN=PASS");return 0
    environment={**os.environ,"PYTHONPATH":str(worktree)}
    subprocess.run(command,cwd=worktree,env=environment,check=True)
    return 0


if __name__=="__main__":raise SystemExit(main())
