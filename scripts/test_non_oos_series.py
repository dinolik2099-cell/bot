#!/usr/bin/env python3
from __future__ import annotations
import copy
import json
from pathlib import Path

from quantbot.research.artifact_store import read_verified_json, seal
from quantbot.research.non_oos_series import (
    NonOOSSeriesError, retained_candidates, metrics_match, replay_candidate,
    build_diagnostic_artifact, validate_diagnostic_artifact,
)

ROOT = Path(__file__).resolve().parents[1]
N11 = ROOT / 'data/reports/formal_runs/N11_FORMAL_TRAIN_VALIDATION_RESULT.json'
PLAN = ROOT / 'docs/handoff/FROZEN_RESEARCH_PLAN_N5.json'


def expect_block(label, fn):
    try:
        fn()
    except Exception:
        print(label, 'PASS')
        return
    raise AssertionError(label + '_DID_NOT_BLOCK')


def reseal(row):
    x = dict(row); x.pop('artifact_identity', None); return seal(x)


def main():
    package = read_verified_json(N11); plan = json.loads(PLAN.read_text())
    candidates = retained_candidates(package, plan)
    assert len(candidates) == 724
    assert len({c.candidate_identity for c in candidates}) == 724
    assert len({c.validation_result_identity for c in candidates}) == 724
    assert all(c.params and c.family for c in candidates)
    print('REAL_N11_724_UNIQUE PASS')

    bad = copy.deepcopy(package); bad['schema_version'] = 'unknown'; bad = reseal(bad)
    expect_block('UNKNOWN_SCHEMA', lambda: retained_candidates(bad, plan))
    bad = copy.deepcopy(package); bad['oos_status'] = 'OPEN'; bad['oos_authorization'] = 'AUTHORIZED'; bad = reseal(bad)
    expect_block('OOS_OPEN', lambda: retained_candidates(bad, plan))
    bad = copy.deepcopy(package); bad['tasks'][0]['validation_result_identities'][0] = '0'*64; bad = reseal(bad)
    expect_block('NESTED_VALIDATION_ID_TAMPER', lambda: retained_candidates(bad, plan))
    bad = copy.deepcopy(package); bad['tasks'][0]['selected_train_top_k'] = bad['tasks'][0]['selected_train_top_k'][:-1]; bad = reseal(bad)
    expect_block('TOPK_BINDING_TAMPER', lambda: retained_candidates(bad, plan))
    retained_task = next(t for t in package['tasks'] if any(r['research_state']=='RETAINED_FOR_FUTURE_REVIEW' for r in t['validation_results']))
    idx = next(i for i,r in enumerate(retained_task['validation_results']) if r['research_state']=='RETAINED_FOR_FUTURE_REVIEW')
    bad = copy.deepcopy(package)
    task = next(t for t in bad['tasks'] if t['task_identity']==retained_task['task_identity'])
    task['validation_results'][idx]['oos_authorized'] = True; bad = reseal(bad)
    expect_block('RETAINED_OOS_TRUE', lambda: retained_candidates(bad, plan))
    bad_plan = copy.deepcopy(plan); bad_plan['boundary_identity_hash'] = '0'*64
    expect_block('BOUNDARY_MISMATCH', lambda: retained_candidates(package, bad_plan))

    assert metrics_match({'total_return':1,'max_drawdown':.2,'profit_factor':float('inf'),'trades':4}, {'total_return':1,'max_drawdown':.2,'profit_factor':float('inf'),'trades':4})
    assert not metrics_match({'total_return':1,'max_drawdown':.2,'profit_factor':2,'trades':4}, {'total_return':1,'max_drawdown':.2,'profit_factor':float('inf'),'trades':4})
    print('METRIC_INF_SEMANTICS PASS')

    expect_block('OOS_REPLAY_WINDOW', lambda: replay_candidate(candidates[0], window='OOS', n7=None, window_loader=None, strategy_resolver=None, engine_factory=None))

    import numpy as np
    corr = np.eye(2); corr[0,1]=corr[1,0]=.99
    artifact = build_diagnostic_artifact(package=package, candidates=candidates[:2], validation_corr=corr, group_summaries={}, replay_matches=4, replay_mismatches=[])
    assert validate_diagnostic_artifact(artifact)
    bad = reseal({**artifact, 'selection_rule_changed': True})
    expect_block('SELECTION_RULE_CHANGED', lambda: validate_diagnostic_artifact(bad))
    print('NON_OOS_SERIES_TEST PASS')

if __name__ == '__main__': main()
