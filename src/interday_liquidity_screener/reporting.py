from __future__ import annotations

from pathlib import Path

import pandas as pd


DISPLAY_COLUMNS = [
    "ticker",
    "close",
    "value_est",
    "avg_value_20d",
    "median_value_20d",
    "volume_ratio",
    "value_ratio",
    "return_5d",
    "active_days_20d",
    "relative_activity_bucket",
    "liquidity_bucket",
    "liquidity_score",
    "trade_candidate_bucket",
]

OUTPUT_COLUMNS = [
    "ticker",
    "yahoo_ticker",
    "last_date",
    "close",
    "volume",
    "value_est",
    "avg_volume_20d",
    "avg_value_20d",
    "median_value_20d",
    "avg_value_5d",
    "return_1d",
    "return_3d",
    "return_5d",
    "return_20d",
    "volume_ratio",
    "value_ratio",
    "high_20d",
    "distance_to_20d_high",
    "low_20d",
    "distance_from_20d_low",
    "close_location",
    "active_days_20d",
    "zero_volume_days_20d",
    "value_consistency_ratio",
    "data_points",
    "is_data_valid",
    "liquidity_score",
    "liquidity_bucket",
    "relative_activity_bucket",
    "trade_candidate_bucket",
    "reason",
    "signal_summary",
]


def build_result_frame(results: list[dict]) -> pd.DataFrame:
    result_df = pd.DataFrame(results)
    for column in OUTPUT_COLUMNS:
        if column not in result_df.columns:
            result_df[column] = None

    return result_df[OUTPUT_COLUMNS].sort_values(
        by=["liquidity_score", "avg_value_20d"],
        ascending=[False, False],
        na_position="last",
    )


def save_csv(result_df: pd.DataFrame, output_path: str | Path) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    result_df.to_csv(path, index=False)


def print_summary(result_df: pd.DataFrame, top: int) -> None:
    print("\n=== Liquidity Screening Summary ===")
    print(f"Total tickers : {len(result_df)}")

    bucket_counts = result_df["liquidity_bucket"].value_counts().to_dict()
    for bucket in ["HIGH_LIQUIDITY", "GOOD_LIQUIDITY", "MEDIUM_LIQUIDITY", "LOW_LIQUIDITY", "ILLIQUID"]:
        print(f"{bucket:10s}: {bucket_counts.get(bucket, 0)}")

    trade_counts = result_df["trade_candidate_bucket"].value_counts().to_dict()
    print("\n=== Trade Candidate Buckets ===")
    for bucket in ["STRONG_WATCH", "WATCH", "AVOID_FOR_NOW", "INVALID_DATA"]:
        print(f"{bucket:14s}: {trade_counts.get(bucket, 0)}")

    top_df = result_df[result_df["liquidity_bucket"].isin(["HIGH_LIQUIDITY", "GOOD_LIQUIDITY"])].head(top)
    print(f"\n=== Top {top} HIGH/GOOD LIQUIDITY ===")
    if top_df.empty:
        print("No HIGH/GOOD liquidity tickers found.")
        return

    print(top_df[DISPLAY_COLUMNS].to_string(index=False))
