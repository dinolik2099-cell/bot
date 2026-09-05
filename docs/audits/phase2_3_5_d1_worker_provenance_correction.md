# Phase 2.3.5 D1 Worker Provenance Correction

## Status

PROVENANCE_CORRECTION_ONLY

This record corrects execution-worker provenance for the historical formal
Phase 2.3.5 D1 parameter research run.

The original research report is intentionally preserved unchanged.
No TRAIN, VALIDATION, freeze, metric, parameter, or OOS result is modified
by this correction.

## Historical formal run

- Research phase: Phase 2.3.5 D1
- Dataset: UM_1H_6DC48D541517
- Formal run Git commit: 4e13d9260818cc058ce2ed51418b57a84e17c0d2
- Formal launch argument: `--workers 24`
- Actual requested worker concurrency: 24
- Task count: 72 Model×Symbol tasks
- Historical report field: `workers = 72`
- Historical report version: 1.0
- Historical report SHA256: 8e58951838d1409effb0634497fc535eb49adf6cf76ffea23c5c8b1a26d97fc2

## Correction

The historical report's top-level `workers = 72` value represented the
72 Model×Symbol tasks rather than the actual requested concurrent worker
count.

The correct execution provenance for the formal run is:

- requested_workers: 24
- task_count: 72
- max_concurrent_workers: 24

The historical report does not contain the newer explicit provenance fields
`requested_workers`, `max_concurrent_workers`, and `task_count`.

Current D1 code records those fields separately.

## Research-impact assessment

This is a provenance/metadata correction only.

It does not alter:

- TRAIN evaluations
- VALIDATION evaluations
- model parameters
- ranking
- freeze/hold decisions
- strategy metrics
- dataset boundaries
- gap policy
- execution semantics

OOS remains sealed and is not read or evaluated by this correction.

## Preservation policy

The historical Phase 2.3.5 D1 JSON report must not be silently overwritten
to repair this metadata discrepancy.

This audit note is the authoritative correction record associated with the
original report hash above.
