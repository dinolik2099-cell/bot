# QuantBot Architecture Plan

## Canonical components

- Backtest semantics: `quantbot.backtest.engine_v2.BacktestEngine`.
- Costs: `quantbot.backtest.costs.CostModel`.
- Portfolio capital semantics: `quantbot.portfolio.shared_capital`.
- Research boundary and data splitting: `quantbot.research.boundary` and runner integration.
- Model registration: `quantbot.research.model_registry`.

## Dependency direction

```text
Model Registry -> Signal Engine -> Portfolio Candidate Selection -> Risk Engine
  -> Position Sizing -> Execution Abstraction -> Paper / Live adapters
```

Models emit data only.  Signals are non-executable intents.  Portfolio chooses
among approved intents.  Risk may reject any proposal.  Execution is the only
layer allowed to translate an approved decision into an order request.

## Retired or isolated paths

- Legacy research entry points must not become a second formal-engine path.
- Script-local execution/cost logic must migrate toward canonical engine and
  `CostModel`, not be independently enhanced.
- Frozen D1 artifacts are evidence, not mutable source files.

## Compatibility and integrity rules

- Preserve existing strategy dataframe output (`signal`, `stop`, `target`).
- New signal normalization uses a one-bar causal lag by default.
- Do not treat OOS authorization fields in historical D1 artifacts as current
  permission to open the sealed OOS window.
- Formal OOS, Monte Carlo, full stress, and live execution each require an
  explicit separate authorization.

## Migration sequence

1. Extend metadata and pure contracts without changing research outcomes.
2. Route new portfolio/risk work through the Signal contract.
3. Extract risk approval and sizing from shared-capital implementation.
4. Add execution and walk-forward interfaces with hard authorization gates.
5. Only after explicit permission, conduct controlled protocol-led research.
