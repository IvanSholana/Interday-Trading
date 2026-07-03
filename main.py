from __future__ import annotations

import argparse

from interday_liquidity_screener.cli import run as run_stage_1
from interday_liquidity_screener.bandarmology import run_stage3b_bandarmology_scoring
from interday_liquidity_screener.stockbit_collector import StockbitCollectorConfig, run_stage3a_broker_collector
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
    stage1.add_argument("--debug", action="store_true")

    stage2 = subparsers.add_parser("stage2", help="Run stage 2 technical screening.")
    stage2.add_argument("--input", required=True, help="Stage 1 liquidity CSV path.")
    stage2.add_argument("--output", default="results/screening_stage_2_technical.csv")
    stage2.add_argument("--period", default="1y", help="Yahoo history period. Default: 1y")

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
    stage3a.add_argument("--output", default="data/output/stage3a_broker_summary_raw.csv")
    stage3a.add_argument("--raw-dir", default="data/raw_stockbit")
    stage3a.add_argument("--from-date", required=True)
    stage3a.add_argument("--to-date", required=True)
    stage3a.add_argument("--limit", type=int, default=25)
    stage3a.add_argument("--sleep-seconds", type=float, default=3.0)
    stage3a.add_argument("--max-retries", type=int, default=3)
    stage3a.add_argument("--retry-backoff-seconds", type=float, default=10.0)

    stage3b = subparsers.add_parser("stage3b", help="Score bandarmology from Stage 2 context and broker summary.")
    stage3b.add_argument("--stage2", required=True)
    stage3b.add_argument("--detector-summary", required=True)
    stage3b.add_argument("--broker-summary", required=True)
    stage3b.add_argument("--output", default="data/output/stage3b_bandarmology_score.csv")

    stage4 = subparsers.add_parser("stage4", help="Run final trade plan with bandarmology confirmation.")
    stage4.add_argument("--stage2", required=True)
    stage4.add_argument("--bandarmology", required=True)
    stage4.add_argument("--output", default="data/output/stage4_trade_plan.csv")
    stage4.add_argument("--capital", type=float, default=10_000_000)
    stage4.add_argument("--risk-per-trade-pct", type=float, default=0.005)
    stage4.add_argument("--max-risk-per-trade-pct", type=float, default=0.01)
    stage4.add_argument("--max-position-pct", type=float, default=0.20)
    stage4.add_argument("--tp1-pct", type=float, default=0.05)
    stage4.add_argument("--tp2-pct", type=float, default=0.08)
    stage4.add_argument("--max-stop-loss-pct", type=float, default=0.06)
    stage4.add_argument("--min-rr-tp1", type=float, default=1.2)
    stage4.add_argument("--min-rr-tp2", type=float, default=1.8)
    stage4.add_argument("--rebound-min-rr-tp1", type=float, default=1.3)
    stage4.add_argument("--rebound-min-rr-tp2", type=float, default=2.0)
    stage4.add_argument("--time-stop-days", type=int, default=10)
    stage4.add_argument("--lot-size", type=int, default=100)
    stage4.add_argument("--bandarmology-min-score", type=int, default=60)
    stage4.add_argument("--allow-trade-without-broker-data", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "stage1":
        run_stage_1(args)
    elif args.command == "stage2":
        run_stage_2_technical_screening(args.input, args.output, period=args.period)
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
        run_stage3a_broker_collector(args.input, args.output, args.raw_dir, args.from_date, args.to_date, config)
    elif args.command == "stage3b":
        run_stage3b_bandarmology_scoring(args.stage2, args.detector_summary, args.broker_summary, args.output)
    elif args.command == "stage4":
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
            bandarmology_min_score=args.bandarmology_min_score,
            allow_trade_without_broker_data=args.allow_trade_without_broker_data,
        )
        run_stage_4_trade_plan(args.stage2, args.bandarmology, args.output, config=config)


if __name__ == "__main__":
    main()
