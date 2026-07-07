from __future__ import annotations

import argparse
from pathlib import Path
import sys

import pandas as pd

from .config import ScreenerConfig
from .downloader import download_ticker_data
from .hybrid_backtest import compare_hybrid_modes
from .hybrid_screener import explain_candidate, run_hybrid_screener
from .journal import append_journal_entry
from .metrics import compute_metrics
from .reporting import build_result_frame, print_summary, save_csv
from .tickers import load_tickers


MODERN_COMMANDS = {"run", "backtest", "journal", "explain"}


def parse_legacy_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="IDX liquidity screener using Yahoo Finance/yfinance."
    )
    parser.add_argument("--tickers-file", required=True, help="Path to TXT/CSV ticker file.")
    parser.add_argument("--period", default=ScreenerConfig.period, help="Yahoo period. Default: 3mo")
    parser.add_argument("--interval", default=ScreenerConfig.interval, help="Yahoo interval. Default: 1d")
    parser.add_argument("--min-value", type=float, default=ScreenerConfig.min_value)
    parser.add_argument("--min-avg-value-20d", type=float, default=ScreenerConfig.min_avg_value_20d)
    parser.add_argument("--min-median-value-20d", type=float, default=ScreenerConfig.min_median_value_20d)
    parser.add_argument("--min-volume-ratio", type=float, default=ScreenerConfig.min_volume_ratio)
    parser.add_argument("--min-active-days-20d", type=int, default=ScreenerConfig.min_active_days_20d)
    parser.add_argument("--max-zero-volume-days-20d", type=int, default=ScreenerConfig.max_zero_volume_days_20d)
    parser.add_argument("--max-return-5d", type=float, default=ScreenerConfig.max_return_5d)
    parser.add_argument("--output", default="results/liquidity_screen_result.csv", help="Output CSV path.")
    parser.add_argument("--top", type=int, default=30, help="Number of top tickers to display.")
    parser.add_argument("--batch-size", type=int, default=ScreenerConfig.batch_size)
    parser.add_argument("--sleep", type=float, default=ScreenerConfig.sleep)
    parser.add_argument("--market-data-db", default=ScreenerConfig.market_data_db)
    parser.add_argument("--refresh-market-data", action="store_true")
    parser.add_argument("--debug", action="store_true", help="Print debug information.")
    args = parser.parse_args(argv)
    args.command = "legacy"
    return args


def parse_modern_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="IDX hybrid stock screening toolkit.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run the hybrid dual-flow screener.")
    run_parser.add_argument("--input", required=True, help="Candidate CSV, usually Stage 2 or Stage 4 output.")
    run_parser.add_argument("--broker-flow", help="Optional broker-flow/bandarmology CSV to merge.")
    run_parser.add_argument("--orderbook", help="Optional normalized orderbook CSV to merge.")
    run_parser.add_argument("--mode", default="normal_execution")
    run_parser.add_argument("--date")
    run_parser.add_argument("--capital-profile", default="capital_1m")
    run_parser.add_argument("--config", default="config/screener.yml")
    run_parser.add_argument("--output", default="results/hybrid_watchlist.csv")
    run_parser.add_argument("--max-candidates", type=int)

    backtest_parser = subparsers.add_parser("backtest", help="Compare hybrid modes on local OHLCV CSV data.")
    backtest_parser.add_argument("--input", required=True, help="Candidate CSV.")
    backtest_parser.add_argument("--price-dir", required=True, help="Directory containing SYMBOL.csv OHLCV files.")
    backtest_parser.add_argument("--capital-profile", default="capital_1m")
    backtest_parser.add_argument("--config", default="config/screener.yml")
    backtest_parser.add_argument("--output", default="results/hybrid_backtest_comparison.csv")

    journal_parser = subparsers.add_parser("journal", help="Manage the paper journal.")
    journal_subparsers = journal_parser.add_subparsers(dest="journal_command", required=True)
    add_parser = journal_subparsers.add_parser("add", help="Append one journal row.")
    add_parser.add_argument("--path", default="data/journal/paper_journal.csv")
    add_parser.add_argument("--date", required=True)
    add_parser.add_argument("--symbol", required=True)
    add_parser.add_argument("--mode", default="bpjs_live")
    add_parser.add_argument("--status-before-entry", default="EXECUTION_DRAFT")
    add_parser.add_argument("--entry-time")
    add_parser.add_argument("--entry-price", type=float, required=True)
    add_parser.add_argument("--lot", type=int, required=True)
    add_parser.add_argument("--tp1", type=float)
    add_parser.add_argument("--tp2", type=float)
    add_parser.add_argument("--stop-loss", type=float)
    add_parser.add_argument("--exit-time")
    add_parser.add_argument("--exit-price", type=float)
    add_parser.add_argument("--exit-reason")
    add_parser.add_argument("--fees", type=float)
    add_parser.add_argument("--slippage", type=float)
    add_parser.add_argument("--mistake-tag")
    add_parser.add_argument("--review-note")

    explain_parser = subparsers.add_parser("explain", help="Print one candidate explanation from a watchlist CSV.")
    explain_parser.add_argument("--input", required=True, help="Hybrid watchlist CSV.")
    explain_parser.add_argument("--symbol", required=True)
    explain_parser.add_argument("--date")

    return parser.parse_args(argv)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in MODERN_COMMANDS:
        return parse_modern_args(argv)
    return parse_legacy_args(argv)


def config_from_args(args: argparse.Namespace) -> ScreenerConfig:
    return ScreenerConfig(
        period=args.period,
        interval=args.interval,
        min_value=args.min_value,
        min_avg_value_20d=args.min_avg_value_20d,
        min_median_value_20d=args.min_median_value_20d,
        min_volume_ratio=args.min_volume_ratio,
        min_active_days_20d=args.min_active_days_20d,
        max_zero_volume_days_20d=args.max_zero_volume_days_20d,
        max_return_5d=args.max_return_5d,
        batch_size=args.batch_size,
        sleep=args.sleep,
        market_data_db=args.market_data_db,
        refresh_market_data=args.refresh_market_data,
    )


def run_legacy(args: argparse.Namespace) -> None:
    config = config_from_args(args)
    tickers = load_tickers(args.tickers_file)

    if args.debug:
        print(f"Loaded tickers: {tickers}")
    print(f"Total tickers loaded: {len(tickers)}")

    data_map = download_ticker_data(tickers, config)
    results = [compute_metrics(ticker, data_map.get(ticker), config) for ticker in tickers]
    result_df = build_result_frame(results)

    save_csv(result_df, args.output)
    print_summary(result_df, args.top)
    print(f"\nOutput saved to: {args.output}")


def run(args: argparse.Namespace) -> None:
    run_legacy(args)


def _load_price_dir(price_dir: str | Path) -> dict[str, pd.DataFrame]:
    root = Path(price_dir)
    price_data: dict[str, pd.DataFrame] = {}
    for path in root.glob("*.csv"):
        symbol = path.stem.replace(".JK", "")
        frame = pd.read_csv(path)
        date_column = "date" if "date" in frame.columns else frame.columns[0]
        frame[date_column] = pd.to_datetime(frame[date_column])
        frame = frame.set_index(date_column).sort_index()
        frame.columns = [str(column).lower() for column in frame.columns]
        price_data[symbol] = frame
    return price_data


def run_hybrid_command(args: argparse.Namespace) -> None:
    output = run_hybrid_screener(
        input_path=args.input,
        output_path=args.output,
        mode=args.mode,
        capital_profile=args.capital_profile,
        config_path=args.config,
        broker_flow_path=args.broker_flow,
        orderbook_path=args.orderbook,
        date=args.date,
        max_candidates=args.max_candidates,
    )
    print(output.to_string(index=False))
    print(f"\nOutput saved to: {args.output}")


def run_backtest_command(args: argparse.Namespace) -> None:
    from .hybrid_screener import load_hybrid_config

    candidates = pd.read_csv(args.input)
    price_data = _load_price_dir(args.price_dir)
    result = compare_hybrid_modes(
        candidates,
        price_data,
        screener_config=load_hybrid_config(args.config),
        capital_profile=args.capital_profile,
    )
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(output_path, index=False)
    print(result.to_string(index=False))
    print(f"\nBacktest comparison saved to: {output_path}")


def run_journal_command(args: argparse.Namespace) -> None:
    if args.journal_command != "add":
        raise ValueError(f"Unsupported journal command: {args.journal_command}")
    entry = {
        "date": args.date,
        "symbol": args.symbol,
        "mode": args.mode,
        "status_before_entry": args.status_before_entry,
        "entry_time": args.entry_time,
        "entry_price": args.entry_price,
        "lot": args.lot,
        "tp1": args.tp1,
        "tp2": args.tp2,
        "stop_loss": args.stop_loss,
        "exit_time": args.exit_time,
        "exit_price": args.exit_price,
        "exit_reason": args.exit_reason,
        "fees": args.fees,
        "slippage": args.slippage,
        "mistake_tag": args.mistake_tag,
        "review_note": args.review_note,
    }
    journal = append_journal_entry(args.path, entry)
    print(journal.tail(1).to_string(index=False))
    print(f"\nJournal saved to: {args.path}")


def run_explain_command(args: argparse.Namespace) -> None:
    print(explain_candidate(args.input, args.symbol, args.date))


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    if args.command == "legacy":
        run_legacy(args)
    elif args.command == "run":
        run_hybrid_command(args)
    elif args.command == "backtest":
        run_backtest_command(args)
    elif args.command == "journal":
        run_journal_command(args)
    elif args.command == "explain":
        run_explain_command(args)
    else:
        raise ValueError(f"Unsupported command: {args.command}")


if __name__ == "__main__":
    main()
