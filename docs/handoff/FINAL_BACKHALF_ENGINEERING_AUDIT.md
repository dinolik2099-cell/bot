# QuantBot Final Backhalf Engineering Audit

Baseline audited: `e80bba04833c637dc06911f7ade780a18a13e895` (plus subsequent engineering commits). This is an engineering readiness classification, not an OOS, Monte Carlo, Paper, or Live authorization.

| Capability | Status | Canonical path / reason |
|---|---|---|
| N3/N5/N7/N8/N9/N10/N11 formal non-OOS chain | COMPLETE_REAL | Frozen plan, canonical loader/engine/cost, recoverable state and N11 evidence package. |
| N12 retained candidates and series diagnostics | COMPLETE_REAL | `research.non_oos_series` and `run_non_oos_series_diagnostics.py`; exact candidate identities are extracted from N11. |
| N12 to portfolio provenance bridge | COMPLETE_REAL | `research.future_stages.build_portfolio_protocol`; exact candidate identities, N11/N12/correlation/dataset/boundary/engine/cost identity are mandatory. |
| Shared-capital portfolio execution | ENGINE_READY_LOCKED | `portfolio.shared_capital.shared_backtest` remains the only accounting execution truth. The formal result path binds N12/N8 inputs, all candidate sleeves, source revision and create-only sealed output; formal accounting remains separately authorized. |
| Portfolio construction / weights / risk / attribution | ENGINE_READY_LOCKED | `portfolio.weight_engine`, `portfolio.research_artifact`, `research.future_stages`, and `research.portfolio_formal_runner`; frozen policy is a protocol input, never post-hoc searched. |
| Cost/slippage stress | ENGINE_READY_LOCKED | Frozen scenarios are executed by the canonical N7/N8 evaluator with a derived `CostModel`, deterministic chunks, checkpoint/resume and complete-only result sealing. |
| Regime/failure attribution | ENGINE_READY_LOCKED | PIT regime labeling and deterministic failure diagnostics have canonical chunk loops, checkpoints and provenance rows. No formal data evaluation has been run. |
| Walk-forward | ENGINE_READY_LOCKED | Non-OOS folds execute only explicit TRAIN/VALIDATION work through N7/N8, with deterministic chunking and sealed resume state; OOS folds remain separately locked. |
| Monte Carlo | ENGINE_READY_PERMANENTLY_LOCKED | A deterministic, fixed-seed, chunked runner is implemented and accepts only sealed non-synthetic upstream evidence. The independent MC authority remains locked, so no formal MC run can start today. |
| 180/200/240 day studies | ENGINE_READY_LOCKED | Immutable 180/200/240 windows use canonical N7/N8 evaluation with deterministic chunks, checkpoint/resume, diagnostics and sealed result coverage. |
| Persistent Paper runtime | COMPLETE_PROTOCOL | Durable ledger/recovery/reconciliation/supervisor path exists; startup remains intentionally disabled. |
| Exchange and Live | INTENTIONALLY_DISABLED | Fake/Paper adapters and live authorization state machine exist; credentials/network/real adapter and orders remain disabled. |
| Pre-OOS gate | COMPLETE_PROTOCOL | Requires N3/N5/N11/N12/portfolio/stress/walk-forward/MC/long-horizon evidence plus explicit human authority. Engineering readiness cannot authorize OOS. |
| Post-OOS/Paper/Live gates | COMPLETE_PROTOCOL | State-machine and evidence model exist; no OOS/Paper evidence can self-authorize a later stage. |
| Legacy D1 / Phase2.4 scripts | LEGACY_NONCANONICAL | Kept only for historical reproducibility. They are not the current N11/N12 canonical portfolio input. |

## Canonical future runners

1. Current non-OOS portfolio protocol: `research.future_stages.build_portfolio_protocol`.
2. Canonical shared-capital execution: `research.future_stages.execute_shared_capital_protocol` → `portfolio.shared_capital.shared_backtest`.
3. N12 diagnostics: `scripts/run_non_oos_series_diagnostics.py`.
4. Stress / regime / failure / walk-forward / MC / long-horizon: `FormalStageProtocol` + `build_future_stage_execution_plan` + `FutureRuntimeContext` + `future_stage_execution`; each uses deterministic chunk scheduling, complete-only result sealing and identity-bound checkpoint/resume. Their public canonical runners never accept a raw evaluator, resampler or raw loader. They require explicit authority before canonical construction or a protected read.
5. Paper: `execution.persistent_paper_runtime` plus `execution.paper_runtime`.
6. Pre-OOS: `research.future_stages.pre_oos_gate`.
7. Live: `execution.live_authorization`; deliberately disabled.

## Current restrictions

OOS is `SEALED / NOT_AUTHORIZED`. No OOS data, formal Monte Carlo, formal long-horizon study, persistent Paper, exchange connection, credential read, or Live order is authorized by this document or any engineering artifact.

## Post-N12 integrity hardening baseline

The current engineering baseline additionally requires semantic revalidation,
not merely a recomputed outer JSON hash, for the following chain:

1. N11 evidence packages recompute aggregate TRAIN and VALIDATION evaluation
   counts from their exact task artifacts.
2. N12 diagnostics rebuild their complete payload from the accepted N11 package
   and frozen diagnostics policy before acceptance.
3. Portfolio artifacts rebuild deterministic weights, exposure, diversification
   and correlation constraints from the declared candidate/policy inputs.
4. Stress artifacts retain the base `CostModel` and rederive the stressed model.
5. Future-stage plans/results bind every declared chunk, complete state and
   create-only output to their frozen protocol/input identities.
6. Walk-forward fold results bind to the exact frozen fold request; Monte Carlo
   and long-horizon checkpoints reject protocol/state drift.
7. Persistent Paper checkpoints recompute their persisted identity, including
   heartbeat, before reload.

These are integrity and audit controls only.  They grant no research, OOS,
Paper, exchange, or Live authority.

## Latest data-plane hardening

The canonical portfolio input preparation layer validates the accepted N12
external anchor before it creates the N8 windowed loader.  It resolves the
exact retained N12 candidate set against both the portfolio protocol and the
N12 manifest, then carries every candidate's N11/N12/task/model/family/symbol
and parameter provenance into a distinct shared-capital sleeve.  It allows
only `TRAIN` or `VALIDATION` preparation and intentionally stops before the
shared-capital accounting call; it is not evidence of a portfolio run.

The common future data-plane validator now rejects partial, duplicate, missing,
wrongly bound, non-completed, OOS-claiming, or identity-tampered result rows.
This makes stress, regime, failure, walk-forward, Monte Carlo, and long-horizon
results auditable only after their declared work-plan coverage is complete. It
does not authorize any of those evaluators.

## Finalization closure

Every future stage now has one common finalization path. A final artifact can
be created only from a validated complete future result and a sealed N10 input
anchor with the same protocol, execution-plan and input identities. The anchor
also carries the accepted N9/N10/N3/N5/candidate/boundary/dataset chain.
Finalization is create-only and rejects partial result coverage, stale anchors,
cross-stage substitution, source-revision omission and OOS field drift.

## Stage-by-stage completion classification

| Stage | PROTOCOL_IMPLEMENTED | REAL_EVALUATOR_IMPLEMENTED | EXECUTION_LOOP_IMPLEMENTED | CHECKPOINT_RESUME_IMPLEMENTED | CANONICAL_CLI_IMPLEMENTED | FORMAL_RESEARCH_EXECUTED |
|---|---|---|---|---|---|---|
| Portfolio | YES | YES | YES | Existing N10 recovery | YES | NO |
| Stress | YES | YES | YES | YES | YES | NO |
| Regime | YES | YES | YES | YES | YES | NO |
| Failure | YES | Failure-supervisor adapter | YES | YES | YES | NO |
| Walk-forward | YES | YES | YES | YES | YES | NO |
| Monte Carlo | YES | Deterministic fixed-seed resampler, authority locked | YES | YES | YES | NO |
| Long-horizon | YES | YES | YES | YES | YES | NO |

The engineering Definition of Done for this non-OOS data-plane closure is
therefore limited to implementation and synthetic/metadata verification:
canonical reader/evaluator construction, frozen input identity, resumable
checkpoint, complete result validation, N10 binding and immutable finalization
are implemented. It is explicitly not a claim that any formal research, OOS,
Monte Carlo, Paper or Live execution has occurred.

## Local verification limit

The local checkout used for engineering does not contain the server-produced N11/N12 report directory. Therefore real-artifact replay is not rerun locally; only synthetic provenance/wiring tests are run. The accepted server artifact remains the authority and must not be regenerated locally.
