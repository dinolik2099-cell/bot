"""Resource-bounded process execution support for the formal non-OOS runner."""
from __future__ import annotations
import os
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Mapping

HARD_MAX_WORKERS = 16
DEFAULT_CPU_FRACTION = 0.50
DEFAULT_RAM_FRACTION = 0.50
DEFAULT_RAM_PER_WORKER_BYTES = 2 * 1024 ** 3

@dataclass(frozen=True)
class WorkerResolution:
    logical_cpus: int
    available_memory_bytes: int
    cpu_fraction: float
    ram_fraction: float
    ram_per_worker_bytes: int
    hard_cap: int
    cpu_limit: int
    ram_limit: int
    workers: int

def logical_cpu_count() -> int:
    return max(1, int(os.cpu_count() or 1))

def available_memory_bytes() -> int:
    """Best-effort available RAM without adding a runtime dependency."""
    try:
        if os.name == "nt":
            import ctypes
            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_=[("dwLength",ctypes.c_ulong), ("dwMemoryLoad",ctypes.c_ulong), ("ullTotalPhys",ctypes.c_ulonglong), ("ullAvailPhys",ctypes.c_ulonglong), ("ullTotalPageFile",ctypes.c_ulonglong), ("ullAvailPageFile",ctypes.c_ulonglong), ("ullTotalVirtual",ctypes.c_ulonglong), ("ullAvailVirtual",ctypes.c_ulonglong), ("ullAvailExtendedVirtual",ctypes.c_ulonglong)]
            state=MEMORYSTATUSEX(); state.dwLength=ctypes.sizeof(state)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(state)): return int(state.ullAvailPhys)
        if os.name == "posix":
            meminfo = Path("/proc/meminfo")
            if meminfo.is_file():
                for line in meminfo.read_text(encoding="utf-8").splitlines():
                    if line.startswith("MemAvailable:"):
                        parts = line.split()
                        if len(parts) >= 2:
                            value = int(parts[1]) * 1024
                            if value > 0:
                                return value
        pages=os.sysconf("SC_AVPHYS_PAGES"); size=os.sysconf("SC_PAGE_SIZE"); return int(pages*size)
    except Exception:
        # Conservative fallback: one worker remains safe; it is never a reason
        # to expand concurrency without a real resource reading.
        return DEFAULT_RAM_PER_WORKER_BYTES

def resolve_workers(*, logical_cpus: int | None = None, available_ram_bytes: int | None = None,
                    cpu_fraction: float = DEFAULT_CPU_FRACTION, ram_fraction: float = DEFAULT_RAM_FRACTION,
                    ram_per_worker_bytes: int = DEFAULT_RAM_PER_WORKER_BYTES, hard_cap: int = HARD_MAX_WORKERS,
                    requested_cap: int | None = None) -> WorkerResolution:
    cpus=logical_cpu_count() if logical_cpus is None else int(logical_cpus)
    memory=available_memory_bytes() if available_ram_bytes is None else int(available_ram_bytes)
    if cpus<1 or memory<1 or not 0 < cpu_fraction <= 1 or not 0 < ram_fraction <= 1 or ram_per_worker_bytes<1 or not 1 <= hard_cap <= HARD_MAX_WORKERS:
        raise ValueError("worker_resolution_input_invalid")
    if requested_cap is not None and (type(requested_cap) is not int or not 1 <= requested_cap <= hard_cap): raise ValueError("requested_worker_cap_invalid")
    cpu_limit=max(1,int(cpus*cpu_fraction)); ram_limit=max(1,int(memory*ram_fraction)//ram_per_worker_bytes)
    workers=min(cpu_limit,ram_limit,hard_cap,requested_cap if requested_cap is not None else hard_cap)
    return WorkerResolution(cpus,memory,cpu_fraction,ram_fraction,ram_per_worker_bytes,hard_cap,cpu_limit,ram_limit,max(1,workers))

def frozen_worker_config(resolution: WorkerResolution) -> dict[str, object]:
    data=asdict(resolution); data["thread_env"]={key:"1" for key in ("OMP_NUM_THREADS","OPENBLAS_NUM_THREADS","MKL_NUM_THREADS","NUMEXPR_NUM_THREADS")}; return data

def apply_worker_thread_limits() -> None:
    for key in ("OMP_NUM_THREADS","OPENBLAS_NUM_THREADS","MKL_NUM_THREADS","NUMEXPR_NUM_THREADS"): os.environ[key]="1"

def execute_formal_task_payload(payload: Mapping[str, object]) -> dict[str, object]:
    """Picklable spawned-process entrypoint; no injected evaluator is accepted."""
    apply_worker_thread_limits()
    root=Path(str(payload["repo_root"])); import sys
    if str(root) not in sys.path: sys.path.insert(0,str(root))
    from scripts import run_formal_train_validation as runner
    from quantbot.research.formal_execution_manifest import validate_manifest
    n7,n8=runner.load_formal_context(); manifest=dict(payload["manifest"]); validate_manifest(manifest,n7,n8)
    authority=runner.build_authority(manifest,n7,n8)
    artifact=runner.execute_one_task(run_root=Path(str(payload["run_root"])),manifest=manifest,n7=n7,n8=n8,task_identity=str(payload["task_identity"]),authority=authority,owner=str(payload["owner"]),lease_seconds=int(payload["lease_seconds"]))
    return {"task_identity":artifact["task_identity"],"status":artifact["status"],"worker_pid":os.getpid()}

def synthetic_claim_only_payload(payload: Mapping[str, object]) -> dict[str, object]:
    """Spawn-safe test helper: exercises real N10 atomic claim, no evaluator."""
    apply_worker_thread_limits(); root=Path(str(payload["repo_root"])); import sys
    project=Path(str(payload["project_root"]));
    if str(project) not in sys.path: sys.path.insert(0,str(project))
    from scripts import run_formal_train_validation as runner
    n7,n8=runner.load_formal_context(); manifest=dict(payload["manifest"]); authority={"n7":n7,"n8":n8,"repo_root":root,"requested_windows":{"TRAIN":manifest["train_window"],"VALIDATION":manifest["validation_window"]},"output_path":manifest["output"]["destination"],"requested_workers":manifest["worker_config"]["workers"]}
    from quantbot.research.recoverable_execution import claim_task, RecoverableExecutionError
    try:
        claim_task(payload["run_root"],manifest,n7.plan,payload["task_identity"],owner=f"synthetic-{os.getpid()}",lease_seconds=int(payload.get("lease_seconds",1)),authority=authority)
        return {"claimed":True,"pid":os.getpid()}
    except RecoverableExecutionError as exc:
        return {"claimed":False,"reason":str(exc),"pid":os.getpid()}
