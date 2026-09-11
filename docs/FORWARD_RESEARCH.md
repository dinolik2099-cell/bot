# Forward Research

This is an independent, append-only public-market **Shadow Research** plane. It does not alter N1–N12, N5, N11, N12, TRAIN/VALIDATION/OOS boundaries, candidate ranking, Paper or Live state. OOS is unavailable and order placement is hard-disabled.

Universe snapshots are point-in-time Binance USDT-M perpetual contracts that are TRADING and have 24h quote volume at least 3M USDT. Completed candles remain the only model input; intrabar observations are evidence only. Long and Short observations use symmetric MFE/MAE and direction-aware trailing rules.

Data lives under `data/forward_research/` as append-only date partitions. Daily manifests hash every file; never edit a written observation. Stop the service with `systemctl stop quantbot-forward-research`; it is supplied but never auto-enabled. Run `scripts/audit_forward_research.py --root data/forward_research --days 14` for evidence-only diagnostics. It never ranks models or changes frozen selection.

## Frozen declarations

Forward does not optimize parameters or select models from N5 grids. Before a
service is allowed to route models, an external versioned decision artifact
must declare fixed model parameters and bind each row to the accepted N5 plan,
N3 freeze, grid hash, strategy hash, and module hash. Verify an artifact with
`scripts/run_forward_research.py --config config/forward_research.yaml --preflight --plan docs/handoff/FROZEN_RESEARCH_PLAN_N5.json --declarations <artifact.json>`.
