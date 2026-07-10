from __future__ import annotations

import argparse

from interday_liquidity_screener.cli import run as run_stage_1
from interday_liquidity_screener.bandarmology import run_stage3b_bandarmology_scoring
from interday_liquidity_screener.backtest_interday import InterdayBacktestConfig, run_stage5_backtest_interday
from interday_liquidity_screener.llm_analyst import run_llm_report, run_stage6_build_evidence
from interday_liquidity_screener.orderbook_filter import OrderbookFilterConfig, run_stage3c_orderbook_filter
from interday_liquidity_screener.paper_bpjs import BpjsPaperConfig, run_stage5_paper_bpjs, run_stage5_update_bpjs_paper
from interday_liquidity_screener.stockbit_collector import StockbitCollectorConfig, run_stage3a_broker_collector
from interday_liquidity_screener.stockbit_collector import parse_windows_arg, run_stage3a_broker_collector_multi_window
from interday_liquidity_screener.technical import run_stage_2_technical_screening
from interday_liquidity_screener.trade_plan import TradePlanConfig, run_stage_3_trade_plan, run_stage_4_trade_plan


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="IDX interday trading screening CLI.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    stage1 = subparsers.add_parser("stage1", help="Run stage 1 liquidity screening.")
    stage1.add_argument("--tickers-file", required=True, help="Path to TXT/CSV ticker file.")
    stage1.add_argument("--period", default="3mo", help="Yahoo period. Default: 3mo")
    stage1.add_argument("--interval", default="1d", help="Yahoo interval. Default: 1d")
    stage1.add_argument("--min-value", type=float, default=5_000_000_000)
    stage1.add_argument("--min-avg-value-20d", type=float, default=5_000_000_000)
    stage1.add_argument("--min-median-value-20d", type=float, default=3_000_000_000)
    stage1.add_argument("--min-volume-ratio", type=float, default=1.0)
    stage1.add_argument("--min-active-days-20d", type=int, default=15)
    stage1.add_argument("--max-zero-volume-days-20d", type=int, default=3)
    stage1.add_argument("--max-return-5d", type=float, default=0.10)
    stage1.add_argument("--output", default="results/screening_stage_1_liquidity.csv")
    stage1.add_argument("--top", type=int, default=30)
    stage1.add_argument("--batch-size", type=int, default=50)
    stage1.add_argument("--sleep", type=float, default=0.0)
    stage1.add_argument("--market-data-db", default="data/cache/market_data.sqlite")
    stage1.add_argument("--refresh-market-data", action="store_true")
    stage1.add_argument("--debug", action="store_true")

    stage2 = subparsers.add_parser("stage2", help="Run stage 2 technical screening.")
    stage2.add_argument("--input", required=True, help="Stage 1 liquidity CSV path.")
    stage2.add_argument("--output", default="results/screening_stage_2_technical.csv")
    stage2.add_argument("--period", default="1y", help="Yahoo history period. Default: 1y")
    stage2.add_argument("--market-data-db", default="data/cache/market_data.sqlite")
    stage2.add_argument("--refresh-market-data", action="store_true")

    stage3 = subparsers.add_parser("stage3", help="Run stage 3 trade plan and risk management.")
    stage3.add_argument("--input", required=True, help="Stage 2 technical CSV path.")
    stage3.add_argument("--output", default="results/screening_stage_3_trade_plan.csv")
    stage3.add_argument("--capital", type=float, default=10_000_000)
    stage3.add_argument("--risk-per-trade-pct", type=float, default=0.005)
    stage3.add_argument("--max-risk-per-trade-pct", type=float, default=0.01)
    stage3.add_argument("--max-position-pct", type=float, default=0.20)
    stage3.add_argument("--tp1-pct", type=float, default=0.05)
    stage3.add_argument("--tp2-pct", type=float, default=0.08)
    stage3.add_argument("--max-stop-loss-pct", type=float, default=0.06)
    stage3.add_argument("--min-rr-tp1", type=float, default=1.2)
    stage3.add_argument("--min-rr-tp2", type=float, default=1.8)
    stage3.add_argument("--rebound-min-rr-tp1", type=float, default=1.3)
    stage3.add_argument("--rebound-min-rr-tp2", type=float, default=2.0)
    stage3.add_argument("--time-stop-days", type=int, default=10)
    stage3.add_argument("--lot-size", type=int, default=100)

    stage3a = subparsers.add_parser("stage3a", help="Collect Stockbit broker summary for Stage 2 bandar watchlist.")
    stage3a.add_argument("--input", required=True, help="Stage 2 technical context CSV path.")
    stage3a.add_argument("--output", default=None)
    stage3a.add_argument("--output-dir", default=None)
    stage3a.add_argument("--raw-dir", default="data/raw_stockbit")
    stage3a.add_argument("--from-date")
    stage3a.add_argument("--to-date")
    stage3a.add_argument("--as-of-date")
    stage3a.add_argument("--windows", default="1D,3D,5D,10D,20D")
    stage3a.add_argument("--limit", type=int, default=25)
    stage3a.add_argument("--sleep-seconds", type=float, default=3.0)
    stage3a.add_argument("--max-retries", type=int, default=3)
    stage3a.add_argument("--retry-backoff-seconds", type=float, default=10.0)

    stage3b = subparsers.add_parser("stage3b", help="Score bandarmology from Stage 2 context and broker summary.")
    stage3b.add_argument("--stage2", required=True)
    stage3b.add_argument("--detector-summary", required=True)
    stage3b.add_argument("--broker-summary", required=True)
    stage3b.add_argument("--output", default="data/output/stage3b_bandarmology_score.csv")

    stage3c = subparsers.add_parser("stage3c", help="Run Stockbit orderbook execution-quality filter.")
    stage3c.add_argument("--stage2", required=True)
    stage3c.add_argument("--bandarmology", required=True)
    stage3c.add_argument("--output", default="data/output/stage3c_orderbook_filter.csv")
    stage3c.add_argument("--raw-dir", default="data/raw_stockbit_orderbook")
    stage3c.add_argument("--sleep-seconds", type=float, default=2.0)
    stage3c.add_argument("--max-retries", type=int, default=3)
    stage3c.add_argument("--retry-backoff-seconds", type=float, default=10.0)

    stage4 = subparsers.add_parser("stage4", help="Run final trade plan with bandarmology confirmation.")
    stage4.add_argument("--stage2", required=True)
    stage4.add_argument("--bandarmology", required=True)
    stage4.add_argument("--orderbook", default=None)
    stage4.add_argument("--output", default="data/output/stage4_trade_plan.csv")
    stage4.add_argument("--strategy-mode", choices=["interday", "bpjs"], default="interday")
    stage4.add_argument("--capital", type=float, default=10_000_000)
    stage4.add_argument("--risk-per-trade-pct", type=float, default=0.005)
    stage4.add_argument("--max-risk-per-trade-pct", type=float, default=0.01)
    stage4.add_argument("--max-position-pct", type=float, default=0.20)
    stage4.add_argument("--tp1-pct", type=float, default=None)
    stage4.add_argument("--tp2-pct", type=float, default=None)
    stage4.add_argument("--max-stop-loss-pct", type=float, default=None)
    stage4.add_argument("--min-rr-tp1", type=float, default=1.2)
    stage4.add_argument("--min-rr-tp2", type=float, default=1.8)
    stage4.add_argument("--rebound-min-rr-tp1", type=float, default=1.3)
    stage4.add_argument("--rebound-min-rr-tp2", type=float, default=2.0)
    stage4.add_argument("--time-stop-days", type=int, default=None)
    stage4.add_argument("--lot-size", type=int, default=100)
    stage4.add_argument("--bandarmology-min-score", type=int, default=60)
    stage4.add_argument("--allow-trade-without-broker-data", action="store_true")
    stage4.add_argument("--require-orderbook-confirmation", action="store_true", default=None)
    stage4.add_argument("--strict-corporate-action-filter", action="store_true")

    stage5a = subparsers.add_parser("stage5-backtest-interday", help="Backtest valid Stage 4 interday trade plans with daily OHLCV.")
    stage5a.add_argument("--signals", required=True, help="Stage 4 trade plan CSV path.")
    stage5a.add_argument("--output", default="data/output/stage5_interday_trades.csv")
    stage5a.add_argument("--metrics-output", default="data/output/stage5_interday_metrics.json")
    stage5a.add_argument("--equity-output", default="data/output/stage5_interday_equity_curve.csv")
    stage5a.add_argument("--price-cache-dir", default="data/cache/ohlcv")
    stage5a.add_argument("--market-data-db", default="data/cache/market_data.sqlite")
    stage5a.add_argument("--period", default="1y")
    stage5a.add_argument("--entry-mode", choices=["next_open", "next_day_entry_zone"], default="next_open")
    stage5a.add_argument("--time-stop-days", type=int, default=10)
    stage5a.add_argument("--buy-fee-pct", type=float, default=0.0015)
    stage5a.add_argument("--sell-fee-pct", type=float, default=0.0025)
    stage5a.add_argument("--slippage-pct", type=float, default=0.001)
    stage5a.add_argument("--initial-capital", type=float, default=10_000_000)
    stage5a.add_argument("--max-entry-gap-pct", type=float, default=0.03)
    stage5a.add_argument("--allow-entry-gap-too-high", action="store_true")
    stage5a.add_argument("--same-day-ambiguous-policy", choices=["stop_first", "tp_first", "skip_trade"], default="stop_first")
    stage5a.add_argument("--refresh-price-cache", action="store_true")

    stage5b = subparsers.add_parser("stage5-paper-bpjs", help="Create BPJS forward paper trading journal from Stage 4.")
    stage5b.add_argument("--stage4", required=True, help="Stage 4 BPJS trade plan CSV path.")
    stage5b.add_argument("--orderbook", default=None, help="Stage 3C orderbook CSV path.")
    stage5b.add_argument("--output", default="data/output/stage5_bpjs_paper_trades.csv")
    stage5b.add_argument("--summary-output", default=None)
    stage5b.add_argument("--date", required=True)
    stage5b.add_argument("--entry-time", default="09:15")
    stage5b.add_argument("--exit-time", default="15:45")
    stage5b.add_argument("--lot-size", type=int, default=100)

    stage5_update = subparsers.add_parser("stage5-update-bpjs-paper", help="Update BPJS paper journal with manual actual exits.")
    stage5_update.add_argument("--paper", required=True, help="Existing BPJS paper trades CSV.")
    stage5_update.add_argument("--actual-exit", required=True, help="Actual exit CSV with ticker, exit_price, exit_time, exit_reason.")
    stage5_update.add_argument("--output", default="data/output/stage5_bpjs_paper_trades_updated.csv")
    stage5_update.add_argument("--summary-output", default=None)

    stage6_evidence = subparsers.add_parser("stage6-build-evidence", help="Build sanitized Stage 6 evidence pack for LLM review.")
    stage6_evidence.add_argument("--stage2", default=None)
    stage6_evidence.add_argument("--bandarmology", default=None)
    stage6_evidence.add_argument("--orderbook", default=None)
    stage6_evidence.add_argument("--stage4", required=True)
    stage6_evidence.add_argument("--backtest-metrics", default=None)
    stage6_evidence.add_argument("--bpjs-summary", default=None)
    stage6_evidence.add_argument("--output", default="data/output/stage6_evidence_pack.json")
    stage6_evidence.add_argument("--strategy-mode", choices=["interday", "bpjs"], default="interday")
    stage6_evidence.add_argument("--run-date", required=True)
    stage6_evidence.add_argument("--max-candidates", type=int, default=30)

    stage6_report = subparsers.add_parser("stage6-llm-report", help="Generate Stage 6 LLM analyst report from evidence pack.")
    stage6_report.add_argument("--evidence", required=True)
    stage6_report.add_argument("--report-output", default="data/output/stage6_llm_daily_report.md")
    stage6_report.add_argument("--ranking-output", default="data/output/stage6_llm_candidate_ranking.json")
    stage6_report.add_argument("--watchlist-output", default="data/output/stage6_llm_watchlist_notes.csv")
    stage6_report.add_argument("--raw-output", default="data/output/stage6_llm_raw_response.json")
    stage6_report.add_argument("--strategy-mode", choices=["interday", "bpjs"], default="interday")
    stage6_report.add_argument("--dry-run", action="store_true")

    stage6 = subparsers.add_parser("stage6", help="Build Stage 6 evidence and generate LLM analyst report.")
    stage6.add_argument("--stage2", default=None)
    stage6.add_argument("--bandarmology", default=None)
    stage6.add_argument("--orderbook", default=None)
    stage6.add_argument("--stage4", required=True)
    stage6.add_argument("--backtest-metrics", default=None)
    stage6.add_argument("--bpjs-summary", default=None)
    stage6.add_argument("--evidence-output", default="data/output/stage6_evidence_pack.json")
    stage6.add_argument("--report-output", default="data/output/stage6_llm_daily_report.md")
    stage6.add_argument("--ranking-output", default="data/output/stage6_llm_candidate_ranking.json")
    stage6.add_argument("--watchlist-output", default="data/output/stage6_llm_watchlist_notes.csv")
    stage6.add_argument("--raw-output", default="data/output/stage6_llm_raw_response.json")
    stage6.add_argument("--strategy-mode", choices=["interday", "bpjs"], default="interday")
    stage6.add_argument("--run-date", required=True)
    stage6.add_argument("--max-candidates", type=int, default=30)
    stage6.add_argument("--dry-run", action="store_true")

    scheduler = subparsers.add_parser("scheduler", help="Run flexible automated pipeline scheduler daemon.")
    scheduler.add_argument("--config", default="config/schedule.json", help="Path to schedule JSON config.")
    scheduler.add_argument("--one-shot", action="store_true", help="Run all tasks immediately once and exit.")
    scheduler.add_argument("--check-interval", type=float, default=30.0, help="Daemon check interval in seconds.")

    monitor = subparsers.add_parser("monitor", help="Run live market monitor for watchlist candidates.")
    monitor.add_argument("--watchlist", default="data/output/stage4_today.csv", help="Path to watchlist CSV.")
    monitor.add_argument("--output", default="data/output/live_monitor_status.json", help="Path to write JSON status output.")
    monitor.add_argument("--interval", type=float, default=300.0, help="Scan interval in seconds (default: 300s).")
    monitor.add_argument("--bypass-market-hours", action="store_true", help="Bypass market hours check for testing.")

    scan_bandar = subparsers.add_parser("scan-bandar", help="Scan and track smart money (bandar) accumulation flow.")
    scan_bandar.add_argument("--config", default="config/bandar_tracker.json", help="Path to bandar tracker JSON config.")
    scan_bandar.add_argument("--output", default="data/output/bandar_scan_results.csv", help="Path to output candidates CSV.")
    scan_bandar.add_argument("--investor-type", help="Override investor type to track.")
    scan_bandar.add_argument("--period", help="Override tracking period.")
    scan_bandar.add_argument("--force-refresh", action="store_true", help="Force refresh and bypass daily cache.")



    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "stage1":
        run_stage_1(args)
    elif args.command == "stage2":
        run_stage_2_technical_screening(
            args.input,
            args.output,
            period=args.period,
            market_data_db=args.market_data_db,
            refresh_market_data=args.refresh_market_data,
        )
    elif args.command == "stage3":
        config = TradePlanConfig(
            capital=args.capital,
            risk_per_trade_pct=args.risk_per_trade_pct,
            max_risk_per_trade_pct=args.max_risk_per_trade_pct,
            max_position_pct=args.max_position_pct,
            tp1_pct=args.tp1_pct,
            tp2_pct=args.tp2_pct,
            max_stop_loss_pct=args.max_stop_loss_pct,
            min_rr_tp1=args.min_rr_tp1,
            min_rr_tp2=args.min_rr_tp2,
            rebound_min_rr_tp1=args.rebound_min_rr_tp1,
            rebound_min_rr_tp2=args.rebound_min_rr_tp2,
            time_stop_days=args.time_stop_days,
            lot_size=args.lot_size,
        )
        run_stage_3_trade_plan(args.input, args.output, config=config)
    elif args.command == "stage3a":
        config = StockbitCollectorConfig(
            limit=args.limit,
            sleep_seconds=args.sleep_seconds,
            max_retries=args.max_retries,
            retry_backoff_seconds=args.retry_backoff_seconds,
        )
        if args.as_of_date:
            if args.from_date or args.to_date:
                raise SystemExit("Use either --as-of-date/--windows or --from-date/--to-date, not both.")
            output_dir = args.output_dir or "data/output/stockbit"
            windows = parse_windows_arg(args.windows)
            run_stage3a_broker_collector_multi_window(args.input, output_dir, args.raw_dir, args.as_of_date, windows, config)
        else:
            if not args.from_date or not args.to_date:
                raise SystemExit("Single-window mode requires --from-date and --to-date. Multi-window mode requires --as-of-date.")
            output = args.output or "data/output/stage3a_broker_summary_long.csv"
            run_stage3a_broker_collector(args.input, output, args.raw_dir, args.from_date, args.to_date, config)
    elif args.command == "stage3b":
        run_stage3b_bandarmology_scoring(args.stage2, args.detector_summary, args.broker_summary, args.output)
    elif args.command == "stage3c":
        config = OrderbookFilterConfig(
            sleep_seconds=args.sleep_seconds,
            max_retries=args.max_retries,
            retry_backoff_seconds=args.retry_backoff_seconds,
        )
        run_stage3c_orderbook_filter(args.stage2, args.bandarmology, args.output, args.raw_dir, config)
    elif args.command == "stage4":
        config = TradePlanConfig(
            strategy_mode=args.strategy_mode,
            capital=args.capital,
            risk_per_trade_pct=args.risk_per_trade_pct,
            max_risk_per_trade_pct=args.max_risk_per_trade_pct,
            max_position_pct=args.max_position_pct,
            tp1_pct=args.tp1_pct,
            tp2_pct=args.tp2_pct,
            max_stop_loss_pct=args.max_stop_loss_pct,
            min_rr_tp1=args.min_rr_tp1,
            min_rr_tp2=args.min_rr_tp2,
            rebound_min_rr_tp1=args.rebound_min_rr_tp1,
            rebound_min_rr_tp2=args.rebound_min_rr_tp2,
            time_stop_days=args.time_stop_days,
            lot_size=args.lot_size,
            bandarmology_min_score=args.bandarmology_min_score,
            allow_trade_without_broker_data=args.allow_trade_without_broker_data,
            require_orderbook_confirmation=args.require_orderbook_confirmation,
            strict_corporate_action_filter=args.strict_corporate_action_filter,
        )
        run_stage_4_trade_plan(args.stage2, args.bandarmology, args.output, config=config, orderbook_path=args.orderbook)
    elif args.command == "stage5-backtest-interday":
        config = InterdayBacktestConfig(
            price_cache_dir=args.price_cache_dir,
            period=args.period,
            entry_mode=args.entry_mode,
            time_stop_days=args.time_stop_days,
            buy_fee_pct=args.buy_fee_pct,
            sell_fee_pct=args.sell_fee_pct,
            slippage_pct=args.slippage_pct,
            initial_capital=args.initial_capital,
            max_entry_gap_pct=args.max_entry_gap_pct,
            reject_if_entry_gap_too_high=not args.allow_entry_gap_too_high,
            same_day_ambiguous_policy=args.same_day_ambiguous_policy,
            refresh_price_cache=args.refresh_price_cache,
            market_data_db=args.market_data_db,
        )
        run_stage5_backtest_interday(args.signals, args.output, args.metrics_output, args.equity_output, config)
    elif args.command == "stage5-paper-bpjs":
        config = BpjsPaperConfig(
            date=args.date,
            entry_time=args.entry_time,
            exit_time=args.exit_time,
            lot_size=args.lot_size,
        )
        run_stage5_paper_bpjs(args.stage4, args.orderbook, args.output, config, summary_output_path=args.summary_output)
    elif args.command == "stage5-update-bpjs-paper":
        run_stage5_update_bpjs_paper(args.paper, args.actual_exit, args.output, summary_output_path=args.summary_output)
    elif args.command == "stage6-build-evidence":
        run_stage6_build_evidence(
            args.stage2,
            args.bandarmology,
            args.orderbook,
            args.stage4,
            args.backtest_metrics,
            args.bpjs_summary,
            args.output,
            args.strategy_mode,
            args.run_date,
            args.max_candidates,
        )
    elif args.command == "stage6-llm-report":
        run_llm_report(args.evidence, args.report_output, args.ranking_output, args.watchlist_output, args.raw_output, args.strategy_mode, dry_run=args.dry_run)
    elif args.command == "stage6":
        run_stage6_build_evidence(
            args.stage2,
            args.bandarmology,
            args.orderbook,
            args.stage4,
            args.backtest_metrics,
            args.bpjs_summary,
            args.evidence_output,
            args.strategy_mode,
            args.run_date,
            args.max_candidates,
        )
        run_llm_report(args.evidence_output, args.report_output, args.ranking_output, args.watchlist_output, args.raw_output, args.strategy_mode, dry_run=args.dry_run)
    elif args.command == "scheduler":
        from interday_liquidity_screener.scheduler import PipelineScheduler
        sched = PipelineScheduler(args.config)
        if args.one_shot:
            sched.check_and_run(one_shot=True)
        else:
            sched.start_loop(check_interval_seconds=args.check_interval)
    elif args.command == "monitor":
        from interday_liquidity_screener.monitor import LiveTickerMonitor
        mon = LiveTickerMonitor(watchlist_path=args.watchlist, status_output_path=args.output)
        mon.start_monitoring_loop(interval_seconds=args.interval, bypass_market_hours=args.bypass_market_hours)
    elif args.command == "scan-bandar":
        from interday_liquidity_screener.bandar_tracker import run_bandar_scan
        print("\n=== Running Bandar Tracker (Smart Money Scan) ===")
        df = run_bandar_scan(
            config_path=args.config,
            output_path=args.output,
            force_refresh=args.force_refresh,
            override_investor_type=args.investor_type,
            override_period=args.period
        )
        if df.empty:
            print("No candidates found or error occurred.")
        else:
            print(f"\nScan complete! Found {len(df)} accumulated tickers:")
            df_disp = df.copy()
            df_disp["net_buy_value_idr"] = df_disp["net_buy_value"].apply(
                lambda val: f"Rp {val/1_000_000_000:.2f} B" if val >= 1_000_000_000 else f"Rp {val/1_000_000:.2f} M"
            )
            print(df_disp[["ticker", "net_buy_value_idr", "avg_price", "frequency", "corp_action_active", "special_notations"]].to_string(index=False))
            print(f"\nSaved candidates list to: {args.output}")





if __name__ == "__main__":
    main()
