from __future__ import annotations
import copy, tempfile
from quantbot.research.result_package import build_evidence_package, validate_evidence_package
from quantbot.research.artifact_store import ArtifactError

def reject(fn):
    try: fn()
    except ArtifactError: return
    raise AssertionError("tamper accepted")
def main():
    binding={"run_id":"r"*64,"manifest_identity":"m"*64,"research_freeze_identity":"f"*64,"research_plan_identity":"p"*64,"candidate_universe_hash":"c"*64,"dataset_id":"synthetic","boundary_identity_hash":"b"*64,"oos_status":"SEALED","oos_authorization":"NOT_AUTHORIZED"}
    artifacts=[{"task_identity":str(i)*64,"run_id":"r"*64,"manifest_identity":"m"*64,"status":"COMPLETED","result_hash":("a" if i == 0 else "b")*64,"actual_train_evaluations":2,"actual_validation_evaluations":1} for i in range(2)]
    state={"run_id":"r"*64,"revision":2,"tasks":{row["task_identity"]:{"attempts":[]} for row in artifacts},"accounting":{}}
    pkg=build_evidence_package(run_state=state,execution_binding=binding,task_artifacts=artifacts,authority_manifest={"manifest_identity":"m"*64},source_git_commit="g"*40,environment={"python":"synthetic"},created_at="2026-01-01T00:00:00Z")
    assert validate_evidence_package(pkg,expected_run_id="r"*64,expected_manifest_identity="m"*64)
    for mutate in (lambda x:x["tasks"].pop(),lambda x:x["tasks"][0].update(result_hash="z"*64),lambda x:x.update(run_id="x"*64),lambda x:x.update(n9_manifest_identity="x"*64)):
        altered=copy.deepcopy(pkg); mutate(altered); reject(lambda:validate_evidence_package(altered,expected_run_id="r"*64,expected_manifest_identity="m"*64))
    print("RESULT_PACKAGE_ADVERSARIAL_SYNTHETIC_TEST_OK")
if __name__=="__main__": main()
