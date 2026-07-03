from __future__ import annotations

import argparse

from .config import ScreenerConfig
from .downloader import download_ticker_data
from .metrics import compute_metrics
from .reporting import build_result_frame, print_summary, save_csv
from .tickers import load_tickers


def parse_args() -> argparse.Namespace:
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
    parser.add_argument("--debug", action="store_true", help="Print debug information.")
    return parser.parse_args()


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
    )


def run(args: argparse.Namespace) -> None:
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


def main() -> None:
    run(parse_args())


if __name__ == "__main__":
    main()
