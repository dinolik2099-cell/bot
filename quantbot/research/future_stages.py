"""Canonical, identity-bound future-stage contracts after accepted N11/N12.

The module wires *inputs* and the existing shared-capital engine.  It does not
open OOS, run MC/long-horizon research, start Paper, or connect an exchange.
"""
from __future__ import annotations
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Mapping, Sequence
from .artifact_store import seal, validate_seal, write_new_json
from .authorization import AuthorizationError, Capability, locked_evidence

class StageState(str, Enum): PENDING="PENDING"; RUNNING="RUNNING"; INTERRUPTED="INTERRUPTED"; FAILED="FAILED"; COMPLETE="COMPLETE"

@dataclass(frozen=True)
class N12CandidateInput:
    candidate_identity: str; validation_result_identity: str; selected_train_result_identity: str
    task_identity: str; model_id: str; family: str; symbol: str; params: Mapping[str, Any]

@dataclass(frozen=True)
class PortfolioProtocol:
    n11_identity: str; n12_identity: str; correlation_sha256: str; dataset_id: str; boundary_identity_hash: str
    research_freeze_identity: str; research_plan_identity: str; engine_identity: str; cost_model_identity: str
    candidates: tuple[N12CandidateInput, ...]; policy_identity: str; state: str="FROZEN_INPUT"

    def identity(self) -> str:
        return seal({"schema_version":"quantbot-portfolio-protocol-v2", **asdict(self)})["artifact_identity"]

def build_portfolio_protocol(*, n11_identity: str, n12_artifact: Mapping[str, Any], candidates: Sequence[N12CandidateInput],
                             correlation_sha256: str, source: Mapping[str, Any], policy_identity: str) -> dict[str, Any]:
    """Build the only permitted N12 portfolio input; no ranking/search occurs."""
    validate_seal(n12_artifact)
    if n12_artifact.get("oos_status")!="SEALED" or n12_artifact.get("oos_authorization")!="NOT_AUTHORIZED": raise ValueError("n12_oos_not_sealed")
    if n12_artifact.get("input_n11_artifact_identity")!=n11_identity: raise ValueError("n11_n12_identity_mismatch")
    ids=[row.candidate_identity for row in candidates]
    if not ids or len(ids)!=len(set(ids)): raise ValueError("n12_candidate_identity_invalid")
    required=("dataset_id","boundary_identity_hash","research_freeze_identity","research_plan_identity","engine_identity","cost_model_identity")
    if any(not source.get(key) for key in required) or len(correlation_sha256)!=64 or not policy_identity: raise ValueError("portfolio_provenance_missing")
    return seal({"schema_version":"quantbot-portfolio-protocol-v2","n11_identity":n11_identity,"n12_identity":n12_artifact["artifact_identity"],"correlation_sha256":correlation_sha256,"source":dict(source),"policy_identity":policy_identity,"candidates":[asdict(row) for row in sorted(candidates,key=lambda row:row.candidate_identity)],"shared_capital_component":"quantbot.portfolio.shared_capital.shared_backtest","oos_status":"SEALED","oos_authorization":"NOT_AUTHORIZED"})

def validate_portfolio_protocol(protocol: Mapping[str, Any]) -> bool:
    validate_seal(protocol)
    if protocol.get("schema_version")!="quantbot-portfolio-protocol-v2" or protocol.get("oos_status")!="SEALED" or protocol.get("oos_authorization")!="NOT_AUTHORIZED": raise ValueError("portfolio_protocol_invalid")
    candidates=protocol.get("candidates"); ids=[row.get("candidate_identity") for row in candidates] if isinstance(candidates,list) else []
    if not ids or len(ids)!=len(set(ids)) or protocol.get("shared_capital_component")!="quantbot.portfolio.shared_capital.shared_backtest": raise ValueError("portfolio_protocol_candidate_binding_invalid")
    return True

def execute_shared_capital_protocol(protocol: Mapping[str, Any], *, frames, signal_maps, recipe_keys, boundary):
    """Deny-by-default public portfolio execution entrypoint.

    A validated N12 protocol establishes what a future portfolio run *would*
    consume; it does not grant permission to load data or perform accounting.
    The canonical engine call is deliberately unreachable here until a future
    reviewed orchestration layer supplies a separate authority implementation.
    """
    validate_portfolio_protocol(protocol)
    raise AuthorizationError("shared_capital_formal_execution_not_authorized")

def _execute_shared_capital_after_authorization(protocol: Mapping[str, Any], *, frames, signal_maps, recipe_keys, boundary):
    """Internal canonical delegation reserved for a future reviewed runner."""
    validate_portfolio_protocol(protocol)
    from quantbot.portfolio.shared_capital import shared_backtest
    return shared_backtest(frames,signal_maps,recipe_keys,boundary)

@dataclass(frozen=True)
class FormalStageProtocol:
    stage: str; input_identity: str; dataset_id: str; boundary_identity_hash: str; source_git_commit: str
    config: Mapping[str, Any]; oos_status: str="SEALED"; oos_authorization: str="NOT_AUTHORIZED"
    def artifact(self) -> dict[str, Any]: return seal({"schema_version":"quantbot-formal-stage-protocol-v1", **asdict(self)})

@dataclass(frozen=True)
class ResumableStageState:
    protocol_identity: str; state: StageState=StageState.PENDING; completed_chunks: tuple[str,...]=(); failed_chunks: tuple[str,...]=()
    def resume(self) -> "ResumableStageState":
        if self.state not in {StageState.PENDING,StageState.INTERRUPTED,StageState.FAILED}: raise ValueError("stage_not_resumable")
        return ResumableStageState(self.protocol_identity,StageState.RUNNING,self.completed_chunks,self.failed_chunks)

    def record(self, chunk_identity: str, *, succeeded: bool) -> "ResumableStageState":
        """Return a new fenced state after exactly one declared chunk completes.

        This is deliberately pure: a future disk-backed coordinator can persist
        it atomically without making a second, incompatible execution state
        machine.  A chunk may never be recorded twice, including once as a
        success and once as a failure.
        """
        if self.state != StageState.RUNNING or not isinstance(chunk_identity, str) or len(chunk_identity) != 64:
            raise ValueError("stage_chunk_state_invalid")
        seen=set(self.completed_chunks) | set(self.failed_chunks)
        if chunk_identity in seen: raise ValueError("stage_chunk_already_recorded")
        completed=self.completed_chunks + (chunk_identity,) if succeeded else self.completed_chunks
        failed=self.failed_chunks if succeeded else self.failed_chunks + (chunk_identity,)
        return ResumableStageState(self.protocol_identity,StageState.RUNNING,completed,failed)

    def finish(self, expected_chunks: Sequence[str]) -> "ResumableStageState":
        expected=tuple(expected_chunks)
        if len(expected)!=len(set(expected)) or any(not isinstance(item,str) or len(item)!=64 for item in expected):
            raise ValueError("stage_expected_chunks_invalid")
        observed=set(self.completed_chunks) | set(self.failed_chunks)
        if observed != set(expected): raise ValueError("stage_chunk_set_incomplete")
        return ResumableStageState(self.protocol_identity,StageState.FAILED if self.failed_chunks else StageState.COMPLETE,
                                   self.completed_chunks,self.failed_chunks)

@dataclass(frozen=True)
class FutureStageChunk:
    """A deterministic work unit for future authorized stages.

    ``window`` intentionally accepts only TRAIN/VALIDATION.  It makes it
    impossible for a walk-forward, MC, or long-horizon scheduler to smuggle an
    OOS read into its work declaration.
    """
    stage: str; ordinal: int; input_identity: str; window: str = "TRAIN_VALIDATION"
    def identity(self) -> str:
        if self.window != "TRAIN_VALIDATION" or self.ordinal < 0 or not self.stage or len(self.input_identity)!=64:
            raise ValueError("future_stage_chunk_invalid")
        return seal({"schema_version":"quantbot-future-stage-chunk-v1",**asdict(self)})["artifact_identity"]

def build_future_stage_execution_plan(protocol: Mapping[str, Any], *, accepted_input_identity: str,
                                      chunk_count: int) -> dict[str, Any]:
    """Create an immutable, non-executing plan with an exact chunk universe.

    This is the common production-shaped planning path for walk-forward,
    Monte-Carlo and long-horizon work.  Execution still requires the separate
    future authorization gate; constructing this plan has no loader/evaluator
    dependency and performs no research.
    """
    validate_stage_protocol(protocol,accepted_input_identity=accepted_input_identity)
    if not isinstance(chunk_count,int) or not 1 <= chunk_count <= 100_000: raise ValueError("future_stage_chunk_count_invalid")
    protocol_id=protocol["artifact_identity"]
    chunks=[{"ordinal":index,"chunk_identity":FutureStageChunk(protocol["stage"],index,protocol_id).identity(),"window":"TRAIN_VALIDATION"} for index in range(chunk_count)]
    return seal({"schema_version":"quantbot-future-stage-execution-plan-v1","protocol_identity":protocol_id,
                 "stage":protocol["stage"],"input_identity":accepted_input_identity,"chunks":chunks,
                 "oos_status":"SEALED","oos_authorization":"NOT_AUTHORIZED"})

def validate_future_stage_execution_plan(plan: Mapping[str, Any], *, protocol: Mapping[str, Any],
                                         accepted_input_identity: str) -> bool:
    validate_seal(plan); validate_stage_protocol(protocol,accepted_input_identity=accepted_input_identity)
    if plan.get("schema_version")!="quantbot-future-stage-execution-plan-v1" or plan.get("protocol_identity")!=protocol.get("artifact_identity") or plan.get("stage")!=protocol.get("stage") or plan.get("input_identity")!=accepted_input_identity:
        raise ValueError("future_stage_execution_binding_invalid")
    if plan.get("oos_status")!="SEALED" or plan.get("oos_authorization")!="NOT_AUTHORIZED": raise ValueError("future_stage_execution_oos_violation")
    chunks=plan.get("chunks")
    if not isinstance(chunks,list) or not chunks: raise ValueError("future_stage_chunks_missing")
    expected=[]
    for index,row in enumerate(chunks):
        if not isinstance(row,Mapping) or row.get("ordinal")!=index or row.get("window")!="TRAIN_VALIDATION": raise ValueError("future_stage_chunk_order_invalid")
        expected.append(FutureStageChunk(protocol["stage"],index,protocol["artifact_identity"]).identity())
    actual=[row.get("chunk_identity") for row in chunks]
    if actual!=expected or len(actual)!=len(set(actual)): raise ValueError("future_stage_chunk_identity_invalid")
    return True

def build_future_stage_result(plan: Mapping[str, Any], *, protocol: Mapping[str, Any],
                              accepted_input_identity: str, state: ResumableStageState,
                              chunk_results: Sequence[Mapping[str, Any]], source_git_commit: str) -> dict[str, Any]:
    """Package a completed future stage without allowing silent partial success.

    The actual evaluator is intentionally outside this builder.  Once a future
    authorization exists, it must return one result for every predeclared
    chunk; this function enforces exact identity coverage and emits immutable
    provenance only after the coordinator has reached ``COMPLETE``.
    """
    validate_future_stage_execution_plan(plan,protocol=protocol,accepted_input_identity=accepted_input_identity)
    if state.protocol_identity != protocol.get("artifact_identity") or state.state != StageState.COMPLETE or state.failed_chunks:
        raise ValueError("future_stage_result_not_complete")
    expected=[row["chunk_identity"] for row in plan["chunks"]]
    rows=sorted((dict(row) for row in chunk_results),key=lambda row:row.get("chunk_identity",""))
    actual=[row.get("chunk_identity") for row in rows]
    if set(actual)!=set(expected) or len(actual)!=len(expected) or len(actual)!=len(set(actual)):
        raise ValueError("future_stage_result_chunk_set_invalid")
    for row in rows:
        if row.get("status")!="COMPLETED" or row.get("window")!="TRAIN_VALIDATION" or not isinstance(row.get("result_identity"),str) or len(row["result_identity"])!=64:
            raise ValueError("future_stage_result_row_invalid")
    return seal({"schema_version":"quantbot-future-stage-result-v1","protocol_identity":protocol["artifact_identity"],
                 "execution_plan_identity":plan["artifact_identity"],"input_identity":accepted_input_identity,
                 "source_git_commit":source_git_commit,"chunks":rows,"counts":{"chunks":len(rows)},
                 "oos_status":"SEALED","oos_authorization":"NOT_AUTHORIZED"})

def validate_future_stage_result(result: Mapping[str, Any], *, plan: Mapping[str, Any], protocol: Mapping[str, Any],
                                 accepted_input_identity: str) -> bool:
    validate_seal(result); validate_future_stage_execution_plan(plan,protocol=protocol,accepted_input_identity=accepted_input_identity)
    if result.get("schema_version")!="quantbot-future-stage-result-v1" or result.get("protocol_identity")!=protocol.get("artifact_identity") or result.get("execution_plan_identity")!=plan.get("artifact_identity") or result.get("input_identity")!=accepted_input_identity:
        raise ValueError("future_stage_result_binding_invalid")
    if result.get("oos_status")!="SEALED" or result.get("oos_authorization")!="NOT_AUTHORIZED": raise ValueError("future_stage_result_oos_violation")
    if not isinstance(result.get("source_git_commit"),str) or len(result["source_git_commit"])!=40: raise ValueError("future_stage_result_source_invalid")
    expected={row["chunk_identity"] for row in plan["chunks"]}; rows=result.get("chunks")
    if not isinstance(rows,list) or result.get("counts",{}).get("chunks")!=len(expected) or {row.get("chunk_identity") for row in rows}!=expected or len(rows)!=len(expected):
        raise ValueError("future_stage_result_coverage_invalid")
    if any(row.get("status")!="COMPLETED" or row.get("window")!="TRAIN_VALIDATION" or not isinstance(row.get("result_identity"),str) or len(row["result_identity"])!=64 for row in rows): raise ValueError("future_stage_result_rows_invalid")
    return True

def write_future_stage_result(root: str, result: Mapping[str, Any], *, plan: Mapping[str, Any],
                              protocol: Mapping[str, Any], accepted_input_identity: str):
    """Create-only output writer after complete protocol/plan/result validation.

    A sealed JSON object alone is not authority to write an accepted-stage
    result: it must be proven to belong to the supplied frozen execution plan.
    """
    validate_future_stage_result(result,plan=plan,protocol=protocol,
                                 accepted_input_identity=accepted_input_identity)
    return write_new_json(root,"FUTURE_STAGE_RESULT",result)

def validate_stage_protocol(artifact: Mapping[str, Any], *, accepted_input_identity: str) -> bool:
    validate_seal(artifact)
    if artifact.get("schema_version")!="quantbot-formal-stage-protocol-v1" or artifact.get("input_identity")!=accepted_input_identity: raise ValueError("stage_input_drift")
    if artifact.get("oos_status")!="SEALED" or artifact.get("oos_authorization")!="NOT_AUTHORIZED": raise ValueError("stage_oos_violation")
    return True

class PreOOSStatus(str, Enum): ENGINEERING_READY="ENGINEERING_READY"; RESEARCH_NOT_YET_COMPLETE="RESEARCH_NOT_YET_COMPLETE"; OOS_NOT_AUTHORIZED="OOS_NOT_AUTHORIZED"; OOS_AUTHORIZED="OOS_AUTHORIZED"
def pre_oos_gate(evidence: Mapping[str, str], *, required: Sequence[str], human_authorized: bool=False) -> PreOOSStatus:
    if any(not evidence.get(key) for key in required): return PreOOSStatus.RESEARCH_NOT_YET_COMPLETE
    # Engineering completeness can never become authority by itself.
    return PreOOSStatus.OOS_AUTHORIZED if human_authorized else PreOOSStatus.OOS_NOT_AUTHORIZED

def require_future_stage(capability: Capability) -> None:
    locked_evidence(capability).require()
