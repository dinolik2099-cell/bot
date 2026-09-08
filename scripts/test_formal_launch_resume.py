from pathlib import Path
import importlib.util
import json
import shutil
import subprocess
import sys
import uuid

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

from quantbot.research.formal_runner import load_n7_context
from quantbot.research.canonical_data_adapter import load_n8_data_context
from quantbot.research.formal_execution_manifest import FormalAuthorizationError

PLAN = PROJECT / "docs/handoff/FROZEN_RESEARCH_PLAN_N5.json"
FREEZE = PROJECT / "docs/handoff/CANDIDATE_UNIVERSE_FREEZE_N3.json"
LOCK = PROJECT / "data/reports/research_boundary_lock.json"
AUDIT = PROJECT / "server_local_audit/formal_launch_resume_cases"

def load_candidate():
    path = PROJECT / "scripts/run_formal_train_validation.py"
    spec = importlib.util.spec_from_file_location("formal_launch_candidate", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def clean_repo(path):
    path.mkdir(parents=True)
    subprocess.check_call(["git","init","-q",str(path)])
    subprocess.check_call(["git","-C",str(path),"config","user.email","launch@example.invalid"])
    subprocess.check_call(["git","-C",str(path),"config","user.name","Launch Test"])
    (path/"README").write_text("synthetic\n",encoding="utf-8")
    exclude = path / ".git/info/exclude"
    exclude.write_text(exclude.read_text(encoding="utf-8") + "\ndata/\n", encoding="utf-8")
    subprocess.check_call(["git","-C",str(path),"add","README"])
    subprocess.check_call(["git","-C",str(path),"commit","-q","-m","initial"])
    return subprocess.check_output(
        ["git","-C",str(path),"rev-parse","HEAD"],text=True
    ).strip()

def main():
    mod=load_candidate()
    lock=json.loads(LOCK.read_text(encoding="utf-8"))
    n7=load_n7_context(PLAN,FREEZE,lock)
    n8=load_n8_data_context(n7,LOCK)

    AUDIT.mkdir(parents=True,exist_ok=True)
    work=AUDIT/("case_"+uuid.uuid4().hex)
    repo=work/"repo"

    try:
        clean_repo(repo)
        mod.ROOT=repo

        calls=[]
        class FirstResolution:
            pass

        def first_resolve(requested_cap=None):
            calls.append(requested_cap)
            return FirstResolution()

        def first_frozen(_resolution):
            return {
                "workers":12,
                "available_memory_bytes":55600000000,
                "logical_cpus":72,
                "cpu_fraction":0.5,
                "ram_fraction":0.5,
                "ram_per_worker_bytes":2147483648,
                "hard_cap":16,
                "cpu_limit":36,
                "ram_limit":12,
                "thread_env":{
                    "MKL_NUM_THREADS":"1",
                    "NUMEXPR_NUM_THREADS":"1",
                    "OMP_NUM_THREADS":"1",
                    "OPENBLAS_NUM_THREADS":"1",
                },
            }

        mod.resolve_workers=first_resolve
        mod.frozen_worker_config=first_frozen

        first,_=mod.load_or_create_launch_manifest(n7,n8)
        first_identity=first["manifest_identity"]
        first_root=mod.runtime_root_for(first)

        assert calls==[None]
        assert first["worker_config"]["workers"]==12
        assert mod.formal_launch_path().is_file()

        def forbidden_resolve(requested_cap=None):
            raise AssertionError("RESUME_RE_RESOLVED_RESOURCES")

        mod.resolve_workers=forbidden_resolve

        second,_=mod.load_or_create_launch_manifest(n7,n8)
        second_root=mod.runtime_root_for(second)

        assert second["manifest_identity"]==first_identity
        assert second_root==first_root
        assert second["worker_config"]["workers"]==12

        mismatch=False
        try:
            mod.load_or_create_launch_manifest(n7,n8,requested_workers=7)
        except RuntimeError as exc:
            mismatch=str(exc)=="formal_frozen_worker_request_mismatch"
        assert mismatch

        (repo/"README").write_text("synthetic changed\n",encoding="utf-8")
        subprocess.check_call(["git","-C",str(repo),"add","README"])
        subprocess.check_call(["git","-C",str(repo),"commit","-q","-m","drift"])

        drift=False
        try:
            mod.load_or_create_launch_manifest(n7,n8)
        except FormalAuthorizationError as exc:
            drift=str(exc)=="source_git_commit_mismatch"
        assert drift

        print("FORMAL_LAUNCH_RESUME_SYNTHETIC_TEST_OK")
        print("FIRST_WORKERS=12")
        print("RESUME_RESOURCE_RERESOLUTION_BLOCKED=PASS")
        print("MANIFEST_IDENTITY_STABLE=PASS")
        print("RUN_ROOT_STABLE=PASS")
        print("EXPLICIT_WORKER_DRIFT_BLOCKED=PASS")
        print("SOURCE_HEAD_DRIFT_BLOCKED=PASS")
        print("OOS_STATUS=SEALED")
        print("OOS_AUTHORIZATION=NOT_AUTHORIZED")
    finally:
        shutil.rmtree(work,ignore_errors=True)

if __name__=="__main__":
    main()
