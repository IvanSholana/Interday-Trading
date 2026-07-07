# IDX Hybrid Screener Methodology

This framework is a screening, validation, backtesting, and paper-journal system for small Indonesian retail trading. It does not place broker orders, does not connect to trading endpoints, and does not guarantee profit.

## Methodology Summary

The screener uses a hybrid dual-flow pipeline:

Flow A, Safe Execution Flow:
Universe Safety -> Liquidity -> Technical -> Broker-flow confirmation -> Price Extension Check -> Pre-market Watchlist -> Orderbook Validation -> Trade Plan.

Flow B, Smart Money Discovery Flow:
Universe Safety -> Broker-flow/Bandarmology -> Liquidity Guard -> Price Extension Check -> Technical Trigger Pending -> Early Watch/Ready Soon -> Orderbook Validation only if promoted.

The final BPJS/micro flow merges both watchlists, ranks a maximum of 3-10 names, then applies live orderbook, net profit after fee, and risk-plan gates before any `EXECUTION_READY` status is allowed.

## Modes

`weekend_preparation`: Broad EOD scan. Produces `EARLY_WATCH`, `READY_SOON`, warnings, or skips. It never produces `EXECUTION_READY`.

`normal_execution`: Standard pre-market scan. It may produce `EXECUTION_DRAFT`, but requires live orderbook validation before `EXECUTION_READY`.

`smart_money_first`: Prioritizes accumulation without chasing price. It should normally produce `EARLY_WATCH` or `READY_SOON`, not direct buy signals.

`bpjs_live`: Strict 1-3% TP mode. Live orderbook, spread, and net-profit-after-fee checks are mandatory. Missing orderbook becomes `NEED_ORDERBOOK`.

`interday_swing`: Less strict on same-day orderbook and more balanced toward smart money, structure, sector, and market regime. Risk plan and price extension warnings still apply.

## Scoring Formula

Scores are 0-100 and configurable in `config/screener.yml`.

Liquidity uses average value, volume, frequency, RVOL, and tradability. BPJS mode gives this high weight because small TP leaves little room for execution friction.

Technical setup uses MA20/MA50 structure, RSI, ATR percentage, close location value, and recent returns. It favors non-extended momentum and pullback/rebound readiness.

Smart money uses broker-flow or bandarmology fields when available: net buy windows, accumulation/distribution window count, top buyer/seller dominance, HHI concentration, and close vs top buyer average. Missing broker-flow returns a neutral score with a warning.

Price extension penalizes excessive 1D/3D/5D returns, distance above MA20, price far above top buyer average, and late volume spikes after a rally.

Market regime and sector strength are neutral when unavailable. They only hard-block if configured.

Orderbook validates spread, best bid/offer, top-5 depth, bid/offer ratio, offer wall, frequency, value, tradability, UMA, notation, and corporate action flags.

Risk plan calculates entry, TP1, TP2, stop loss, lot affordability, fees, slippage, net profit, risk amount, reward amount, and R:R.

## Status Definitions

`EARLY_WATCH`: Interesting but not ready.
`READY_SOON`: Setup improving, still needs final validation.
`EXECUTION_DRAFT`: Pre-market candidate without live orderbook pass.
`NEED_ORDERBOOK`: BPJS candidate cannot proceed without live orderbook.
`EXECUTION_CANDIDATE`: Gates pass except final live validation.
`EXECUTION_READY`: Live orderbook and risk gates pass. This is not an order instruction.
`DANGER_CHASING`: Price is too extended.
`DISTRIBUTION_WARNING`: Broker-flow distribution risk is high.
`ORDERBOOK_WEAK` / `ORDERBOOK_REJECT`: Live book is not supportive.
`LOW_LIQUIDITY`, `NET_PROFIT_NOT_WORTH_IT`, `TOO_EXPENSIVE_FOR_CAPITAL`, `RISK_REWARD_BAD`, `DATA_INSUFFICIENT`, `SKIP`: Explicit rejection or insufficiency reasons.

## Daily SOP

Weekend/EOD:
Run the hybrid screener. Review top candidates. Label `EARLY_WATCH`, `READY_SOON`, `EXECUTION_DRAFT`, `DANGER_CHASING`, `DISTRIBUTION_WARNING`, and `SKIP`. Keep only 3-10 names, preferably 3-5 for BPJS.

Pre-market:
Check news, corporate action, notasi, UMA, and IEP/IEV if available. Do not trust cancellable pre-open orders too much. Do not mark anything execution-ready before live validation.

Market open:
Avoid blind entry in the first minute unless pre-open evidence is strong and the live orderbook is supportive. Validate spread, bid depth, offer wall, frequency, value, and actual prints. If the orderbook is weak, skip even if EOD scores are high.

Entry:
Enter only if a trade plan exists. TP, SL, lot size, expected net profit, and R:R must be clear. For 1-3 lot BPJS, net profit after fees must be worth the risk and effort.

Exit:
Respect TP/SL. Do not widen SL casually. Journal every trade.

## Backtest Methodology

The comparison backtest supports `normal_execution`, `smart_money_first`, and `hybrid_dual_flow`. Metrics include trade count, TP hit rate, stop-loss rate, average win/loss, expectancy, profit factor, drawdown, holding period, gross return, net return after fee/slippage, win rate, average R multiple, skipped reasons, and status distribution.

Daily OHLC ambiguity is conservative by default: if TP and SL are touched in the same candle, the simulator assumes SL first.

Walk-forward validation is supported by running separate train/test period bundles. The framework does not auto-tune thresholds, to avoid curve fitting.

## Running

Legacy liquidity scan:

```bash
liquidity-screen --tickers-file examples/tickers.txt --output results/liquidity.csv
```

Hybrid run:

```bash
python -m interday_liquidity_screener run --input results/stage2.csv --mode weekend_preparation --capital-profile capital_1m --output results/hybrid_watchlist.csv
```

BPJS live with orderbook:

```bash
python -m interday_liquidity_screener run --input results/stage2.csv --broker-flow results/bandar.csv --orderbook results/orderbook.csv --mode bpjs_live --capital-profile capital_1m
```

Backtest comparison:

```bash
python -m interday_liquidity_screener backtest --input results/hybrid_candidates.csv --price-dir data/prices --output results/hybrid_backtest_comparison.csv
```

Paper journal:

```bash
python -m interday_liquidity_screener journal add --date 2026-07-06 --symbol TLKM --entry-price 2500 --exit-price 2550 --lot 1 --mode bpjs_live
```

Explain one candidate:

```bash
python -m interday_liquidity_screener explain --input results/hybrid_watchlist.csv --symbol TLKM
```

## Warnings And Limitations

This is a probability and discipline framework, not a profit promise. Broker-flow can be noisy, orderbook depth can change quickly, and small TP targets are highly sensitive to fees, slippage, spread, and hesitation. Real data adapters must be validated against actual IDX/vendor schemas before decisions are trusted.

