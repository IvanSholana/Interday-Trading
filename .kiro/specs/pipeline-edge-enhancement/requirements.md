# Requirements Document

## Introduction

This feature is a comprehensive edge-enhancement of the existing IDX interday trading screening pipeline (`src/interday_liquidity_screener/`). The current pipeline runs in stages: Stage 1 liquidity screening, Stage 2 technical context screening, Stage 3A Stockbit broker-summary collection, Stage 3B bandarmology scoring, and Stage 4 trade-plan/risk-management generation. All decision thresholds in the pipeline are currently hand-picked and have never been validated against realized outcomes, several computed broker-flow features are unused, some configuration parameters are exposed but never applied, and there is no global market-regime gate or backtesting capability.

The enhancement adds an empirical validation layer (walk-forward backtesting), strengthens the bandarmology score with concentration and price-vs-average features, introduces a market-regime/breadth gate, requires multi-bar confirmation for setups, replaces fixed take-profit levels with adaptive ones, models transaction costs and fill realism, and cleans up dead configuration and price-adjustment handling. The system remains a research and screening tool: it produces trade plans, statistics, and reports for human review, and does not place orders or provide investment advice.

The pipeline is a Python project using pandas, with data sourced from Yahoo Finance (via `yfinance`) and Stockbit. It exposes stage-based subcommands through `main.py`, and its core computation functions are pure to support property-based testing.

## Glossary

- **Pipeline**: The complete multi-stage IDX interday screening system under `src/interday_liquidity_screener/`.
- **Stage_1**: The liquidity screening stage producing `value_est`, `liquidity_score`, `liquidity_bucket`, and relative-activity metrics.
- **Stage_2**: The technical context screening stage producing `trend_score`, `momentum_score`, `volatility_score`, `entry_setup`, `technical_context`, and `bandar_watch_eligible`.
- **Stage_3A**: The Stockbit broker-summary and bandar-detector collection stage.
- **Stage_3B**: The bandarmology scoring stage producing `bandarmology_score` and `bandarmology_signal`.
- **Stage_4**: The trade-plan and risk-management stage producing entry, stop-loss, take-profit, and position-size fields.
- **Backtester**: The new Stage 5 walk-forward validation component that replays historical trade plans against subsequent price data and computes outcome statistics.
- **Regime_Filter**: The new global market-regime and breadth gate evaluated before trades are considered eligible.
- **Bandarmology_Score**: The 0-100 broker-flow accumulation score computed by Stage_3B.
- **HHI**: The Herfindahl-Hirschman Index measuring concentration of buyer or seller broker value.
- **Net_Buyer_Dominance**: A measure comparing aggregated top-3 buyer value against aggregated top-3 seller value.
- **Close_Vs_Top_Buyer_Avg**: The relative difference between the latest close price and the top buyer broker average price.
- **Last_Date**: The date of the latest bar used by Stage_2 for a given ticker's snapshot.
- **Snapshot_Bar**: The single most recent OHLCV bar (`features.iloc[-1]`) currently used by Stage_2 classification.
- **Confirmation_Window**: A configurable number of consecutive recent bars used to confirm a breakout or rebound setup.
- **Adaptive_Take_Profit**: A take-profit level derived from ATR or the next resistance level rather than a fixed percentage.
- **Adjusted_Close**: The Yahoo Finance dividend/split-adjusted close price series.
- **Raw_Close**: The unadjusted close price series used for IDX tick-size and execution-price computation.
- **Transaction_Cost_Model**: The component that applies broker fees, levies, and slippage to simulated fills.
- **Avg_Value_20d**: The trailing 20-day average traded value used as the liquidity reference for position-size capping.
- **Entry_Setup**: A Stage_2 classification such as `BREAKOUT_CANDIDATE`, `PULLBACK_CANDIDATE`, `REBOUND_CANDIDATE`, or `WATCH_ENTRY`.
- **Technical_Context**: A Stage_2 broad-context classification such as `BREAKOUT_NEAR` or `REBOUND_NEAR_LOW`.
- **Bandarmology_Signal**: The categorical broker-flow signal such as `STRONG_ACCUMULATION` or `MILD_DISTRIBUTION`.
- **Trade_Outcome**: The realized result of a simulated trade, classified as TP1-hit, TP2-hit, stop-hit, or time-stop-exit.
- **MFE**: Maximum Favorable Excursion, the largest unrealized gain during a trade.
- **MAE**: Maximum Adverse Excursion, the largest unrealized loss during a trade.
- **Expectancy**: The average profit or loss per trade across a set of simulated trades.
- **STOCKBIT_TOKEN**: The Stockbit API authentication token loaded from the environment (`.env`).

## Requirements

### Requirement 1: Walk-Forward Backtesting Framework (Stage 5)

**User Story:** As a researcher, I want a walk-forward backtester that replays historical trade plans against subsequent price data, so that I can measure whether the pipeline's hand-picked thresholds produce a real edge before relying on them.

#### Acceptance Criteria

1. THE Backtester SHALL accept a set of historical trade plans, each containing at minimum a ticker, an entry date, an entry price, a stop-loss price, a take-profit-1 price, a take-profit-2 price, and a time-stop horizon in trading days.
2. WHEN a trade plan and its subsequent OHLCV bars are provided, THE Backtester SHALL classify the Trade_Outcome as exactly one of TP1-hit, TP2-hit, stop-hit, or time-stop-exit.
3. IF within a single bar both the stop-loss price and a take-profit price are reachable by the bar's high-low range, THEN THE Backtester SHALL resolve the Trade_Outcome as stop-hit.
4. WHEN a trade plan is simulated, THE Backtester SHALL record the MFE and the MAE observed over the holding period as fractions of the entry price.
5. WHEN a set of trade plans has been simulated, THE Backtester SHALL compute the win rate, the Expectancy per trade, the TP1-hit rate, and the stop-hit rate over that set.
6. WHEN a set of trade plans has been simulated, THE Backtester SHALL report the win rate, the Expectancy per trade, the TP1-hit rate, and the stop-hit rate broken down separately by Entry_Setup, by Technical_Context, and by Bandarmology_Signal.
7. IF a trade plan references a ticker for which fewer than one subsequent bar is available, THEN THE Backtester SHALL exclude that trade plan from outcome statistics and record it in a skipped-trades count.
8. THE Pipeline SHALL expose the Backtester as a `stage5` subcommand in `main.py` consistent with the existing stage-based command structure.
9. THE Backtester SHALL write its per-trade results and its aggregated statistics to CSV output files under the configured output directory.

### Requirement 2: Bandarmology Score Enhancement

**User Story:** As a researcher, I want the bandarmology score to use the concentration, net-buyer-dominance, and price-vs-average features that are already computed, so that the broker-flow signal reflects the strongest available accumulation evidence.

#### Acceptance Criteria

1. WHEN `broker_activity_available` is true for a ticker, THE Stage_3B SHALL incorporate the buyer HHI and the seller HHI into the Bandarmology_Score.
2. WHEN `broker_activity_available` is true for a ticker, THE Stage_3B SHALL incorporate Net_Buyer_Dominance derived from `top3_buyer_value` and `top3_seller_value` into the Bandarmology_Score.
3. WHEN `close_vs_top_buyer_avg` is available for a ticker, THE Stage_3B SHALL incorporate Close_Vs_Top_Buyer_Avg into the Bandarmology_Score.
4. IF the buyer HHI, the seller HHI, `top3_buyer_value`, `top3_seller_value`, or `close_vs_top_buyer_avg` is missing or not a finite number for a ticker, THEN THE Stage_3B SHALL compute the Bandarmology_Score using the remaining available features without raising an error.
5. THE Stage_3B SHALL constrain the Bandarmology_Score to the inclusive range of 0 to 100.
6. THE Stage_3B SHALL record, for each scored ticker, which broker-flow features contributed to the Bandarmology_Score.

### Requirement 3: Broker-Flow Window Alignment

**User Story:** As a researcher, I want the broker-flow collection window to align with the Stage 2 snapshot date, so that broker-flow evidence and technical context describe the same period.

#### Acceptance Criteria

1. WHEN Stage_3A collects broker-flow data for a ticker, THE Stage_3A SHALL derive the collection window end date from the Stage_2 Last_Date for that ticker.
2. THE Stage_3A SHALL derive the collection window start date from the Last_Date minus a configurable number of trading days with a defined default.
3. WHERE a user supplies explicit from-date and to-date arguments, THE Stage_3A SHALL use the supplied dates instead of the Last_Date-derived window.
4. IF the Stage_2 Last_Date is missing for a ticker, THEN THE Stage_3A SHALL skip broker-flow collection for that ticker and record the ticker in a skipped-collection count.

### Requirement 4: Market Regime and Breadth Gate

**User Story:** As a researcher, I want a global market-regime and breadth gate applied before trades are considered eligible, so that trade candidates are suppressed during unfavorable broad-market conditions.

#### Acceptance Criteria

1. THE Regime_Filter SHALL compute a market-regime state from the IHSG index trend using a configurable moving-average lookback.
2. WHERE breadth data is available, THE Regime_Filter SHALL compute the percentage of screened stocks trading above a configurable moving average.
3. WHILE the market-regime state is classified as unfavorable, THE Stage_4 SHALL mark trade candidates with a regime-gated status instead of a valid trade-plan status.
4. THE Stage_4 SHALL record the market-regime state and the breadth percentage on each trade-plan row.
5. WHERE the user disables the Regime_Filter through configuration, THE Stage_4 SHALL evaluate trade candidates without applying the regime gate.
6. IF IHSG index data cannot be retrieved, THEN THE Regime_Filter SHALL report an unavailable regime state and THE Stage_4 SHALL record the unavailable state without rejecting candidates solely for that reason.

### Requirement 5: Multi-Bar Setup Confirmation

**User Story:** As a researcher, I want breakout and rebound setups confirmed across multiple recent bars instead of a single snapshot, so that transient single-day spikes are less likely to trigger a candidate.

#### Acceptance Criteria

1. WHEN Stage_2 classifies a `BREAKOUT_CANDIDATE`, THE Stage_2 SHALL require the breakout conditions to hold across a configurable Confirmation_Window of consecutive recent bars.
2. WHEN Stage_2 classifies a `REBOUND_CANDIDATE`, THE Stage_2 SHALL require the rebound conditions to hold across a configurable Confirmation_Window of consecutive recent bars.
3. WHERE the Confirmation_Window is configured as one bar, THE Stage_2 SHALL reproduce the single-Snapshot_Bar classification behavior.
4. IF fewer bars are available than the configured Confirmation_Window, THEN THE Stage_2 SHALL classify the ticker as `INVALID_DATA`.
5. THE Stage_2 SHALL record the number of confirming bars used for each confirmed setup.

### Requirement 6: Adaptive Take-Profit and Liquidity-Based Position Cap

**User Story:** As a researcher, I want take-profit levels derived from volatility or resistance and position sizes capped by liquidity, so that targets and fill assumptions reflect each stock's actual behavior.

#### Acceptance Criteria

1. THE Stage_4 SHALL compute Adaptive_Take_Profit levels for take-profit-1 and take-profit-2 from either an ATR multiple or the next resistance level according to configuration.
2. WHERE the user selects fixed-percentage take-profit through configuration, THE Stage_4 SHALL reproduce the existing fixed take-profit behavior.
3. THE Stage_4 SHALL cap the position size so that the position value does not exceed a configurable percentage of the ticker's Avg_Value_20d.
4. WHEN both the liquidity-based cap and the existing risk-based and capital-based caps apply, THE Stage_4 SHALL select the smallest resulting position size.
5. THE Stage_4 SHALL record the take-profit method used and the binding position-size constraint on each trade-plan row.
6. IF the Avg_Value_20d is missing or not positive for a ticker, THEN THE Stage_4 SHALL apply the existing risk-based and capital-based caps without the liquidity-based cap and record that the liquidity cap was not applied.

### Requirement 7: Transaction Cost, Fee, and Slippage Modeling

**User Story:** As a researcher, I want simulated trades to account for fees and slippage, so that measured expectancy reflects net interday returns rather than gross returns.

#### Acceptance Criteria

1. THE Transaction_Cost_Model SHALL apply a configurable buy-side fee rate and a configurable sell-side fee rate to each simulated fill.
2. THE Transaction_Cost_Model SHALL apply a configurable slippage amount to each simulated entry price and each simulated exit price.
3. WHEN the Backtester computes the Expectancy per trade, THE Backtester SHALL compute it net of the fees and slippage from the Transaction_Cost_Model.
4. WHERE the user configures all fee and slippage parameters to zero, THE Transaction_Cost_Model SHALL leave simulated fill prices and returns unchanged.
5. THE Backtester SHALL report both the gross Expectancy and the net Expectancy for each simulated set of trades.

### Requirement 8: Configuration and Price-Adjustment Cleanup

**User Story:** As a developer, I want dead configuration parameters resolved and price adjustment handled correctly, so that the pipeline's behavior matches its exposed configuration and its indicators are not distorted by corporate actions.

#### Acceptance Criteria

1. WHEN `min_volume_ratio` is configured, THE Stage_1 SHALL apply `min_volume_ratio` as a screening threshold.
2. WHEN `max_return_5d` is configured, THE Stage_1 SHALL apply `max_return_5d` as a screening threshold.
3. WHEN Stage_2 computes trend, momentum, and volatility indicators, THE Stage_2 SHALL compute them from the Adjusted_Close series.
4. WHEN Stage_4 computes IDX tick-size rounding and execution prices, THE Stage_4 SHALL use the Raw_Close series.
5. THE Pipeline SHALL document, for each configuration parameter, whether the parameter is applied and in which stage.

### Requirement 9: Research-Tool Boundaries and Data-Provider Compliance

**User Story:** As the system owner, I want the enhanced pipeline to remain a compliant research tool, so that it respects data-provider terms and does not act as an order-execution or advice system.

#### Acceptance Criteria

1. THE Pipeline SHALL produce screening results, trade plans, backtest statistics, and reports without placing, routing, or transmitting any order to a broker or exchange.
2. THE Pipeline SHALL load STOCKBIT_TOKEN from the environment and SHALL NOT store the token value in source files or output files.
3. WHEN Stage_3A issues successive requests to Stockbit, THE Stage_3A SHALL apply the configured inter-request delay and retry-backoff limits.
4. THE Pipeline SHALL present trade plans and backtest statistics as research outputs and SHALL label outputs as not constituting investment advice.
5. WHERE new data-source requests to Yahoo Finance are added, THE Pipeline SHALL reuse the existing batching and sleep configuration to respect rate limits.

### Requirement 10: Backward-Compatible Pipeline Integration

**User Story:** As a developer, I want the enhancements to integrate with the existing stage-based structure and pure-function design, so that current outputs and property-based tests continue to work.

#### Acceptance Criteria

1. THE Pipeline SHALL preserve the existing `stage1` through `stage4` subcommand interfaces in `main.py`.
2. THE Pipeline SHALL implement new scoring, confirmation, take-profit, cost, and regime computations as pure functions that derive outputs solely from their inputs.
3. WHERE a new configuration parameter is introduced, THE Pipeline SHALL provide a default value that preserves the current pipeline behavior for that parameter.
4. THE Pipeline SHALL retain all existing output columns in each stage's CSV output and SHALL add new fields as additional columns.
