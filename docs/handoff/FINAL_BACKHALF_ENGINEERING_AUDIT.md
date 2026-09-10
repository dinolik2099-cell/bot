# QuantBot Final Backhalf Engineering Audit

Baseline audited: `e80bba04833c637dc06911f7ade780a18a13e895` (plus subsequent engineering commits). This is an engineering readiness classification, not an OOS, Monte Carlo, Paper, or Live authorization.

| Capability | Status | Canonical path / reason |
|---|---|---|
| N3/N5/N7/N8/N9/N10/N11 formal non-OOS chain | COMPLETE_REAL | Frozen plan, canonical loader/engine/cost, recoverable state and N11 evidence package. |
| N12 retained candidates and series diagnostics | COMPLETE_REAL | `research.non_oos_series` and `run_non_oos_series_diagnostics.py`; exact candidate identities are extracted from N11. |
| N12 to portfolio provenance bridge | COMPLETE_REAL | `research.future_stages.build_portfolio_protocol`; exact candidate identities, N11/N12/correlation/dataset/boundary/engine/cost identity are mandatory. |
| Shared-capital portfolio execution | ENGINE_READY_LOCKED | `portfolio.shared_capital.shared_backtest` remains the only accounting execution truth. The canonical runner builds one sleeve per retained N12 `candidate_identity`, so no model/symbol parameter candidate is silently collapsed. Formal accounting remains separately authorized. |
| Portfolio construction / weights / risk / attribution | ENGINE_READY_LOCKED | `portfolio.weight_engine`, `portfolio.research_artifact`, `research.future_stages`, and `research.portfolio_formal_runner`; frozen policy is a protocol input, never post-hoc searched. |
| Cost/slippage stress | ENGINE_READY_LOCKED | `backtest.stress_framework` derives from canonical `CostModel`; future formal stage uses frozen protocol input and complete result provenance. |
| Regime/failure attribution | ENGINE_READY_LOCKED | PIT regime and deterministic failure supervisor exist; future stages bind their provenance inputs. No formal data evaluation has been run. |
| Walk-forward | COMPLETE_PROTOCOL | Fold/request/aggregate/resume contracts now share an identity-bound, chunked TRAIN/VALIDATION-only execution plan; data execution remains blocked until specific future research authorization. |
| Monte Carlo | COMPLETE_PROTOCOL | Deterministic seed/resampler/result infrastructure now has the same immutable chunk lifecycle; formal simulation remains blocked by authorization. |
| 180/200/240 day studies | COMPLETE_PROTOCOL | Immutable protocol/checkpoint/resume contracts now use the shared chunk lifecycle; formal execution remains blocked. |
| Persistent Paper runtime | COMPLETE_PROTOCOL | Durable ledger/recovery/reconciliation/supervisor path exists; startup remains intentionally disabled. |
| Exchange and Live | INTENTIONALLY_DISABLED | Fake/Paper adapters and live authorization state machine exist; credentials/network/real adapter and orders remain disabled. |
| Pre-OOS gate | COMPLETE_PROTOCOL | Requires N3/N5/N11/N12/portfolio/stress/walk-forward/MC/long-horizon evidence plus explicit human authority. Engineering readiness cannot authorize OOS. |
| Post-OOS/Paper/Live gates | COMPLETE_PROTOCOL | State-machine and evidence model exist; no OOS/Paper evidence can self-authorize a later stage. |
| Legacy D1 / Phase2.4 scripts | LEGACY_NONCANONICAL | Kept only for historical reproducibility. They are not the current N11/N12 canonical portfolio input. |

## Canonical future runners

1. Current non-OOS portfolio protocol: `research.future_stages.build_portfolio_protocol`.
2. Canonical shared-capital execution: `research.future_stages.execute_shared_capital_protocol` → `portfolio.shared_capital.shared_backtest`.
3. N12 diagnostics: `scripts/run_non_oos_series_diagnostics.py`.
4. Stress / walk-forward / MC / long-horizon: `FormalStageProtocol` + `build_future_stage_execution_plan` + `ResumableStageState` + `FutureRuntimeContext`; each work unit is identity-bound, TRAIN/VALIDATION-only, duplicate-proof, and requires a future explicit authorization before any evaluator or loader can be attached. Its v2 result validator requires exact chunk coverage, result identities, protocol/plan/input provenance, a valid source revision, and sealed OOS fields before a create-only result can be written.
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

## Local verification limit

The local checkout used for engineering does not contain the server-produced N11/N12 report directory. Therefore real-artifact replay is not rerun locally; only synthetic provenance/wiring tests are run. The accepted server artifact remains the authority and must not be regenerated locally.
