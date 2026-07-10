# MCP Professional Trading Workflow

This MCP server is a decision-support interface for the IDX interday trading
pipeline. It helps an agent run scans, inspect evidence, and produce a
capital-aware shortlist. It does not place orders and does not guarantee profit.

## Recommended Flow

1. Run the evening scan.
   - Blocking: `run_trading_pipeline` runs synchronously and returns when the
     scan finishes.
   - Non-blocking: `start_pipeline_run` returns a `job_id` immediately and runs
     the scan on a background thread. Poll `get_pipeline_run_status(job_id)`
     until the status is `SUCCEEDED` or `FAILED`. Prefer this for long scans so
     the agent stays responsive.
   - Use `run_phase="malam"` to skip live orderbook checks.
   - Enable the P1-P5 safety modules unless doing a controlled experiment.
   - Use the actual capital and risk settings, not placeholders.

2. Inspect the watchlist with `get_watchlist_results`.
   - Treat `EXECUTION_DRAFT` as a draft only.
   - Treat `EXECUTION_READY` as eligible for review, not an order instruction.
   - Reject or ignore rows with explicit risk statuses unless a later run changes
     their status.

3. Build the professional pack with `get_trade_recommendation`.
   - Use `output_format="markdown"` for human review.
   - Use `output_format="json"` for agent workflows.
   - Pass `max_tp_pct` when the user has a hard TP constraint.
   - Shortcut: `get_run_bundle(run_id)` returns the audit, watchlist, and
     recommendation in one call to avoid extra round trips.

4. Run `run_morning_confirmation` before market execution.
   - This resumes the evening run and executes Stage 3C orderbook confirmation.
   - Re-check recommendation output after the morning run.
   - Do not chase opening gaps beyond the planned entry zone.

## Output Formats & Resources

- Every inspection and decision-support tool accepts `output_format="json"` for
  structured agent parsing or `output_format="markdown"` for human review.
- Static context is also exposed as cacheable MCP resources: `mcp://capabilities`,
  `mcp://recommendation-policy`, and `mcp://workflow`.
- The `evening_scan_workflow` prompt returns a ready-made malam -> pagi playbook.

## Decision Grades

- `A`: Live-ready candidate with strong confidence and no hard audit flags.
- `B`: Strong draft or candidate that still needs live confirmation.
- `C`: Watchlist-quality or moderate-confidence candidate; monitor only unless
  a later scan upgrades it.
- `D`: Rejected, incomplete, outside user constraints, or not affordable.

## Audit Flags

- `NEEDS_LIVE_CONFIRMATION`: Historical/pre-market setup is acceptable, but
  orderbook or live market conditions still need confirmation.
- `WATCH_ONLY`: Useful to monitor, not an execution plan.
- `INCOMPLETE_PRICE_PLAN`: Missing entry, TP, or SL.
- `TP_OUTSIDE_USER_CAP`: Actual TP from rounded prices violates the user's TP
  constraint.
- `RISK_REWARD_BELOW_MINIMUM`: Risk/reward is below the professional minimum.
- `NO_AFFORDABLE_LOT`: Capital cannot buy at least one lot.
- `HIGH_CAPITAL_CONCENTRATION`: Position uses more than 95% of available capital.
- `LOW_GROSS_PROFIT`: Gross profit target is below the small-account viability
  threshold.

## Interpretation Rules

- The recommendation layer does not create new signals. It reads
  `hybrid_watchlist.csv` and adds sizing, TP-cap, audit, and communication
  discipline.
- Actual TP and SL percentages are computed from the rounded IDX tick prices,
  not from the unrounded target percentage.
- `position_value` and `lots` are informational sizing outputs. The final
  execution decision still depends on live price, orderbook depth, spread,
  market regime, and user risk tolerance.
