---
name: trading-strategy-change
description: Safely implement, review, or validate behavioral changes to the IDX interday trading strategy in this repository. Use for changes to screening filters, indicators, hybrid scoring, weights, thresholds, watchlist statuses, entry/TP/SL rules, position sizing, fees, execution or risk gates, backtest assumptions, and MCP tools that expose those decisions. Also use when investigating whether a proposed code or configuration change can alter candidate selection or trade outcomes.
---

# Trading Strategy Change

Treat strategy behavior as a versioned decision system. Make the smallest auditable change, preserve existing public imports, and prove the intended difference with focused tests.

## Classify the impact

Before editing, state which surfaces the change affects:

- **Screening decision:** candidate inclusion, ranking, score, or final watchlist status.
- **Execution/risk decision:** entry, TP/SL, sizing, fees, liquidity, or trade eligibility.
- **Backtest semantics:** fills, costs, ambiguous bars, dates, metrics, or comparison baselines.
- **Presentation only:** API/UI wording or display with no decision change.
- **Data collection only:** source acquisition or normalization with no intended rule change.

If presentation or collection can indirectly affect a decision, classify it under both surfaces.

## Trace the decision path

1. Read `AGENTS.md`; inspect the current implementation and nearby tests.
2. Trace inputs through configuration, coercion, scoring, status assignment, trade planning, and backtesting as applicable.
3. Identify the single source of truth:
   - Import status labels and pipeline keys from `src/interday_liquidity_screener/constants.py`.
   - Keep hybrid contracts in `hybrid_config.py`, tiny conversions in `hybrid_utils.py`, and scoring/orchestration in `hybrid_screener.py`.
   - Keep entry, TP/SL, sizing, fees, and trade-status behavior in `trade_plan.py`.
   - Preserve TypeScript contracts in `frontend/src/types/api.ts`; never introduce `any`.
4. Search every caller, configuration path, persisted output, MCP/API exposure, and dependent test.
5. Record old and intended behavior with at least one boundary example.

## Define the behavioral contract

Specify input conditions, old decision, intended decision, equality and missing-data behavior, backward compatibility, and expected effects on screening, risk, and backtests.

Do not silently choose a trading assumption when alternatives materially change selection, risk, or historical performance. Ask for direction.

## Implement narrowly

1. Add or update a focused test that captures the old-versus-new decision.
2. Centralize new configuration with validation and an explicit default. Do not scatter thresholds or weights.
3. Use `WatchlistStatus` and `PipelineStage`; never add bare status or stage strings.
4. Preserve public imports when moving logic.
5. Avoid unrelated refactors and generated files.
6. Update API types and `usePipeline` when contracts cross the frontend boundary. Keep API calls out of `App.tsx`.
7. Update MCP schemas or descriptions when tool inputs or returned decision fields change.

## Test the decision

Cover the smallest relevant matrix:

- below, at, and above a changed threshold;
- enabled and disabled optional behavior;
- missing, `None`/`NaN`, malformed, or insufficient data;
- unchanged behavior outside the requested scope;
- affected status transitions or risk decisions;
- costs and anti-look-ahead behavior for historical outcomes.

Run the nearest focused test first. After Python changes, run:

```powershell
.venv\Scripts\python.exe -m pytest tests/ -x -q --tb=short
```

Run the full suite for shared scoring/config changes. After frontend changes, run:

```powershell
cd frontend
npm run build
```

Report validation that could not run; never imply it passed.

## Validate research integrity

For backtest-affecting changes, check:

- no future data enters signals, eligibility, universe construction, or fills;
- costs, tick rounding, lot sizing, and same-day ambiguity match live assumptions;
- comparisons share universe, period, capital, and cost model;
- missing or delisted symbols are not discarded in a performance-improving way;
- parameter optimization is separated from evaluation data.

Do not infer strategy improvement from unit tests. Performance claims require a comparable backtest with period, sample size, costs, and caveats.

## Hand off clearly

Summarize the changed decision behavior, impact surfaces, files/configuration, validation results, untested assumptions, and whether saved outputs or resume caches need regeneration.
