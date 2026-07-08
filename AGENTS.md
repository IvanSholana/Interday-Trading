# Agent Guide

This repo is an IDX interday trading research and screening tool. Keep changes small, tested, and explicit about whether they affect screening decisions, execution/risk decisions, UI presentation, or data collection.

## Project Map

- `main.py`: CLI stage orchestration for the full workflow.
- `src/interday_liquidity_screener/cli.py`: package CLI for Stage 1 liquidity screening.
- `src/interday_liquidity_screener/constants.py`: **single source of truth** for all status string labels (`WatchlistStatus` enum) and pipeline stage keys (`PipelineStage` enum). Always import from here instead of using bare string literals.
- `src/interday_liquidity_screener/pipeline.py`: core pipeline orchestration, stage runner helper functions (`capture_stage`, `run_pipeline`), `PipelineOptions` dataclass, `PipelinePaths` dataclass, and resume-caching logic.
- `src/interday_liquidity_screener/server.py`: FastAPI web/API surface for the React frontend. All 11 endpoints are documented with Google-style docstrings. The OpenAPI schema is auto-generated at `/docs`.
- `frontend/src/types/api.ts`: **TypeScript source of truth** for all API request and response shapes. Import from here instead of using `any`.
- `frontend/src/hooks/usePipeline.ts`: custom React hook that encapsulates all API calls and real-time polling state. `App.tsx` should only call this hook for pipeline interactions.
- `frontend/src`: React UI source. `App.tsx` contains layout and config state only. Built static assets are copied under `src/interday_liquidity_screener/static`.
- `src/interday_liquidity_screener/hybrid_screener.py`: hybrid watchlist scoring and status orchestration.
- `src/interday_liquidity_screener/hybrid_config.py`: hybrid screener constants, dataclass config, score/risk result models, and config loading.
- `src/interday_liquidity_screener/hybrid_utils.py`: shared coercion/scoring helpers used by hybrid scoring.
- `src/interday_liquidity_screener/trade_plan.py`: Stage 4 entry, TP/SL, sizing, fee, and trade-status logic.
- `src/interday_liquidity_screener/backtest/`: reusable backtest engine, cost model, metrics, and reports.
- `src/interday_liquidity_screener/enhancements/`: optional filters/sizers/confirmation modules used by hybrid scoring.
- `tests/`: pytest coverage. Prefer adding focused tests near the module being changed.

## Maintenance Rules

- Preserve public imports from existing modules when moving code. This project has tests and callers that import directly from feature modules.
- Treat `data/`, `results/`, `frontend/node_modules/`, `.venv/`, `__pycache__/`, and generated static assets as non-source unless the task is explicitly about them.
- Do not change trading thresholds, scoring weights, or status labels as a cleanup. Those are behavioral changes and need targeted tests.
- Use `rg` for repo search and run focused pytest first, then full pytest for shared scoring/config changes.
- For hybrid screener work, keep pure data contracts in `hybrid_config.py`, tiny conversion helpers in `hybrid_utils.py`, and orchestration/scoring decisions in `hybrid_screener.py`.

## Rules for LLM Coding Assistants

1. **Use constants, not magic strings.** Never write bare status string literals like `"EXECUTION_READY"`. Always import from `constants.py`:
   ```python
   from interday_liquidity_screener.constants import WatchlistStatus, PipelineStage
   if row["final_status"] == WatchlistStatus.EXECUTION_READY: ...
   ```

2. **Use typed interfaces, not `any`.** In TypeScript, never use `any`. Import the correct interface from `frontend/src/types/api.ts`:
   ```typescript
   import type { RunSummary, PipelineStatus, RunRequest } from '../types/api';
   ```

3. **Keep React components focused.** `App.tsx` handles layout and config state only. All API calls go through `usePipeline`. If a component file exceeds 300 lines, split it into a sub-component under `frontend/src/components/`.

4. **Write tests before marking work done.** When adding new filters, indicators, or pipeline helper functions, write a focused test in `tests/` first and confirm it passes with `pytest tests/<test_file>.py -q`.

5. **Never mutate scoring weights or status labels without a test.** These are behavioral changes that need a dedicated test asserting the old vs. new output. Add to the existing test for the relevant module.

6. **After any Python change, run focused pytest first:**
   ```powershell
   .venv\Scripts\python.exe -m pytest tests/ -x -q --tb=short
   ```

7. **After any frontend change, rebuild static assets:**
   ```powershell
   cd frontend && npm run build
   ```

