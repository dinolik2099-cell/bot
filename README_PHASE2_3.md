# QuantBot Phase 2.3 — Controlled Parameter Research V1.0

## Purpose

Establish a disciplined parameter-research layer after the Phase 2.2.2 multi-strategy/multi-asset baseline.

## Research candidates

- `trend_breakout`
- `trend_pullback`
- `volatility_breakout`

`mean_reversion` is intentionally excluded from this first-pass research.

## Data discipline

The research boundary remains the authoritative source. The process is:

1. TRAIN: evaluate the controlled parameter grid.
2. TRAIN ranking: rank by `total_return - max_drawdown`.
3. VALIDATION: evaluate only the top-K TRAIN candidates.
4. Freeze one parameter set per strategy/asset using VALIDATION.
5. OOS: evaluate the frozen parameter set exactly after selection.

OOS is never used for parameter selection.

## First-pass grids

### trend_breakout

- `lookback`: 20, 40, 60
- `stop_atr`: 1.5, 2.0, 2.5
- `reward_r`: 2.0, 3.0, 4.0
- 27 candidates

### trend_pullback

- `ema_fast`: 10, 20
- `ema_slow`: 50, 80, 120
- `stop_atr`: 1.5, 2.0, 2.5
- `reward_r`: 2.0, 3.0
- 36 candidates

### volatility_breakout

- `range_lookback`: 10, 20, 40
- `stop_atr`: 1.5, 2.0, 2.5
- `reward_r`: 2.0, 3.0, 4.0
- 27 candidates

Default top-K from TRAIN: 3.

For six assets this means 540 TRAIN evaluations, 54 VALIDATION evaluations, and 18 final OOS evaluations.

## Output

`data/reports/phase2_3_parameter_research.json`

The report records the grids, ranking rule, frozen parameter sets, validation candidates, OOS results, and errors.
