# Forward Shadow Engineering Audit

## Scope

This plane is an append-only, public-market observation system.  It is not a
formal N-series research runner and cannot authorize or consume OOS, Paper,
Exchange, or Live execution.

## Engineering closure controls

1. Completed candle history is keyed by `(symbol, interval)`; a second market
   cannot enter a model's input history.
2. A model can run only from an external named declaration artifact.  Each row
   is bound to the accepted N5/N3 identity chain and to its grid, function and
   implementation hashes.  The runtime never selects or optimizes parameters.
3. The service routes only a validated `ForwardPipeline`, and only after a
   public candle is marked closed.  It has no evaluator, loader, parameter, or
   strategy injection argument.
4. Shadow paths collect only post-signal UTC closed prices.  Completion emits
   evidence; it never creates a position or order.
5. A checkpoint is bound to its config, source Git commit, N5 research-plan
   identity, and declaration-manifest identity.  A drifted resume fails closed.
6. Daily evidence seals are create-only and identity checked.  The audit
   rejects provenance-chain drift, non-public source records, and OOS claims.

## Deliberate operational boundary

No declaration artifact is checked in as a presumed winning-model selection.
Such an artifact needs an explicit external decision identifier and fixed
parameters.  This is intentional: N5 freezes the candidate/grid metadata, not
a Forward-optimized selection, and the Forward code must not manufacture one.

## Verification boundary

The following are engineering-only synthetic checks:

```text
scripts/test_forward_research.py
scripts/test_future_data_plane.py
scripts/test_research_plan.py
```

They do not establish model performance.  At their completion, OOS is still
`SEALED / NOT_AUTHORIZED`; formal TRAIN/VALIDATION, D1/D2/D3, Paper, Exchange,
and Live activity remain zero.
