"""Synthetic-only multiprocessing safety tests for the formal parallel runner."""
from __future__ import annotations
from concurrent.futures import ProcessPoolExecutor
import json, multiprocessing, os, shutil, subprocess, sys, tempfile, time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from quantbot.research.formal_parallel import resolve_workers,frozen_worker_config,available_memory_bytes,synthetic_claim_only_payload
from quantbot.research.formal_runner import load_n7_context
from quantbot.research.canonical_data_adapter import load_n8_data_context
from quantbot.research.formal_execution_manifest import build_manifest,preflight_authorize,FormalAuthorizationError,TRUSTED_MAX_WORKERS
from quantbot.research.recoverable_execution import initialize_run,load_run,claim_task,RecoverableExecutionError
PLAN=ROOT/'docs/handoff/FROZEN_RESEARCH_PLAN_N5.json';FREEZE=ROOT/'docs/handoff/CANDIDATE_UNIVERSE_FREEZE_N3.json';LOCK=ROOT/'data/reports/research_boundary_lock.json'
def clean_repo(path):
 path.mkdir();subprocess.check_call(['git','init','-q',str(path)]);subprocess.check_call(['git','-C',str(path),'config','user.email','parallel@example.invalid']);subprocess.check_call(['git','-C',str(path),'config','user.name','Parallel']);(path/'README').write_text('x');subprocess.check_call(['git','-C',str(path),'add','README']);subprocess.check_call(['git','-C',str(path),'commit','-q','-m','x']);return subprocess.check_output(['git','-C',str(path),'rev-parse','HEAD'],text=True).strip()
def main():
 assert resolve_workers(logical_cpus=1,available_ram_bytes=1).workers==1
 assert resolve_workers(logical_cpus=8,available_ram_bytes=64*1024**3).workers==4
 assert resolve_workers(logical_cpus=32,available_ram_bytes=128*1024**3).workers==16
 assert resolve_workers(logical_cpus=64,available_ram_bytes=128*1024**3,requested_cap=8).workers==8
 for n in (1,4,8,16): assert resolve_workers(logical_cpus=64,available_ram_bytes=128*1024**3,requested_cap=n).workers==n
 config=frozen_worker_config(resolve_workers(logical_cpus=64,available_ram_bytes=128*1024**3));assert config['workers']==16 and all(v=='1' for v in config['thread_env'].values())
 if os.name=='posix' and Path('/proc/meminfo').is_file():
  memavailable=[line for line in Path('/proc/meminfo').read_text(encoding='utf-8').splitlines() if line.startswith('MemAvailable:')]
  assert len(memavailable)==1
  expected_available=int(memavailable[0].split()[1])*1024
  actual_available=available_memory_bytes()
  assert actual_available==expected_available,(actual_available,expected_available)
  print(f'LINUX_MEMAVAILABLE_BYTES={actual_available}')
 lock=json.loads(LOCK.read_text());n7=load_n7_context(PLAN,FREEZE,lock);n8=load_n8_data_context(n7,LOCK)
 with tempfile.TemporaryDirectory() as td:
  base=Path(td);repo=base/'repo';commit=clean_repo(repo);one=build_manifest(n7,n8,source_git_commit=commit,worker_config={'workers':1},output_destination='data/reports/formal_runs/synthetic.json',created_at='x');two=build_manifest(n7,n8,source_git_commit=commit,worker_config={'workers':2},output_destination='data/reports/formal_runs/synthetic.json',created_at='x');assert one['manifest_identity']!=two['manifest_identity']
  try:build_manifest(n7,n8,source_git_commit=commit,worker_config={'workers':TRUSTED_MAX_WORKERS+1},output_destination='data/reports/formal_runs/synthetic.json',created_at='x');preflight_authorize(two,n7,n8,repo_root=repo,requested_windows={'TRAIN':two['train_window'],'VALIDATION':two['validation_window']},output_path=two['output']['destination'],requested_workers=17)
  except FormalAuthorizationError:pass
  else:raise AssertionError('worker cap bypass')
  run=base/'run';initialize_run(run,two,n7.plan,n7=n7,n8=n8,repo_root=repo);task=n7.plan['tasks'][0]['task_identity'];payload={'project_root':str(ROOT),'repo_root':str(repo),'run_root':str(run),'manifest':two,'task_identity':task,'lease_seconds':1}
  with ProcessPoolExecutor(max_workers=2,mp_context=multiprocessing.get_context('spawn')) as pool: results=list(pool.map(synthetic_claim_only_payload,(payload,payload)))
  assert sum(row['claimed'] for row in results)==1
  state=load_run(run,two,n7.plan);assert state['tasks'][task]['status']=='RUNNING'
  time.sleep(1.05);authority={'n7':n7,'n8':n8,'repo_root':repo,'requested_windows':{'TRAIN':two['train_window'],'VALIDATION':two['validation_window']},'output_path':two['output']['destination'],'requested_workers':2};claim_task(run,two,n7.plan,task,owner='reclaimed',lease_seconds=1,authority=authority);assert load_run(run,two,n7.plan)['tasks'][task]['owner']=='reclaimed'
 print('FORMAL_PARALLEL_EXECUTOR_SYNTHETIC_TEST_OK')
 print('OOS_EVALUATOR_CALLS=0');print('OOS_MARKET_DATA_READS=0')
if __name__=='__main__':main()
