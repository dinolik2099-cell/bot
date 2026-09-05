# QuantBot Implementation Matrix

Source baseline: server snapshot `4e13d92`, then GitHub commit `46b7904`.
Research boundary: `UM_1H_6DC48D541517`.  Formal OOS remains sealed.

| ID | Area | Status | Safe next action | Research integrity boundary |
|---|---|---|---|---|
| IM-00 | Source recovery and Git sync | COMPLETE | Preserve server backup evidence | No report/data rewrite |
| IM-01 | D1 report provenance | PARTIAL | Add only future-run metadata schemas | Do not alter formal D1 artifacts |
| IM-02 | D1 stability diagnostic | COMPLETE | Regression coverage retained | No D1 rerun |
| IM-03 | D1 worker metadata | COMPLETE | Future reports use explicit fields | No D1 rerun |
| IM-04 | D1 six-symbol guard | COMPLETE | Keep regression test | No subset formal run |
| IM-05 | Model Registry | EXISTS_BUT_REFACTOR | Lifecycle metadata added; populate only through controlled research | OOS status stays sealed |
| IM-06 | Signal Engine | PARTIAL | Standard non-executable signal contract added | No portfolio/risk/execution bypass |
| IM-07 | Trade supervisor | MISSING | Define immutable trade-record contract | No performance claims |
| IM-08 | Market regime | MISSING | Implement causal-only detector interface | No future data |
| IM-09 | Portfolio Manager | EXISTS_BUT_REFACTOR | Extract candidate selection from shared-capital runner | No OOS selection |
| IM-10 | Risk Engine | MISSING | Add highest-priority approval layer | No live order path |
| IM-11 | Position sizing | PARTIAL | Reuse canonical cost/risk semantics | No duplicate engine |
| IM-12 | Execution abstraction | MISSING | Define paper-safe interface only | No credentials/orders |
| IM-13 | Walk-forward | MISSING | Build protocol and authorization gate | Formal run requires approval |
| IM-14 | Cost/stress framework | PARTIAL | Reuse `CostModel` and `engine_v2` | MC/full stress prohibited now |
| IM-15 | OOS protocol | RESEARCH_LOCKED | Implement no-read authorization guard | Do not read/run/aggregate OOS |
| IM-16 | Paper/Live adapters | PROHIBITED_NOW | Interfaces only after risk/execution layers | No persistent paper/live run |

Status vocabulary follows the master handoff: COMPLETE, PARTIAL,
EXISTS_BUT_REFACTOR, MISSING, RESEARCH_LOCKED, and PROHIBITED_NOW.
