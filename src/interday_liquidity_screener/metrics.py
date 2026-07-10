from __future__ import annotations

from typing import Any

import pandas as pd

from .classifier import (
    INVALID_DATA,
    QUIET,
    build_reason,
    build_signal_summary,
    calculate_liquidity_score,
    classify_liquidity_bucket,
    classify_relative_activity,
    classify_trade_candidate,
)
from .config import ScreenerConfig
from .utils import safe_float, safe_pct_change


def empty_metrics(ticker: str, reason: str = "") -> dict[str, Any]:
    return {
        "ticker": ticker.replace(".JK", ""),
        "yahoo_ticker": ticker,
        "last_date": None,
        "close": None,
        "volume": None,
        "value_est": None,
        "avg_volume_20d": None,
        "avg_value_20d": None,
        "median_value_20d": None,
        "avg_value_5d": None,
        "return_1d": None,
        "return_3d": None,
        "return_5d": None,
        "return_20d": None,
        "volume_ratio": None,
        "value_ratio": None,
        "high_20d": None,
        "distance_to_20d_high": None,
        "low_20d": None,
        "distance_from_20d_low": None,
        "close_location": None,
        "active_days_20d": None,
        "zero_volume_days_20d": None,
        "value_consistency_ratio": None,
        "data_points": 0,
        "is_data_valid": False,
        "liquidity_score": 0,
        "liquidity_bucket": "ILLIQUID",
        "relative_activity_bucket": QUIET,
        "trade_candidate_bucket": INVALID_DATA,
        "reason": reason,
        "signal_summary": "Invalid or insufficient data. Skip this ticker until a full 20-day history is available.",
    }


def apply_screening_labels(metrics: dict[str, Any], config: ScreenerConfig) -> dict[str, Any]:
    score = calculate_liquidity_score(metrics, config)
    metrics["liquidity_score"] = score
    metrics["liquidity_bucket"] = classify_liquidity_bucket(score)
    metrics["relative_activity_bucket"] = classify_relative_activity(metrics)
    metrics["trade_candidate_bucket"] = classify_trade_candidate(metrics, config)
    metrics["reason"] = build_reason(metrics, config)
    metrics["signal_summary"] = build_signal_summary(metrics, config)
    return metrics


def compute_metrics(ticker: str, df: pd.DataFrame | None, config: ScreenerConfig) -> dict[str, Any]:
    result = empty_metrics(ticker)
    try:
        if df is None or df.empty:
            result["reason"] = "empty_data"
            return apply_screening_labels(result, config)

        required_columns = {"Close", "High", "Low", "Volume"}
        missing_columns = required_columns.difference(df.columns)
        if missing_columns:
            result["reason"] = f"missing_columns: {', '.join(sorted(missing_columns))}"
            return apply_screening_labels(result, config)

        clean_df = df.dropna(subset=["Close"]).copy()
        if clean_df.empty:
            result["reason"] = "no_close_data"
            return apply_screening_labels(result, config)

        clean_df["Volume"] = clean_df["Volume"].fillna(0)
        clean_df["value_est"] = clean_df["Close"] * clean_df["Volume"]

        latest = clean_df.iloc[-1]
        data_points = len(clean_df)
        # Prior-only baseline: the latest row is the decision bar and must not
        # contribute to the rolling reference used to score itself.
        last_20 = clean_df.iloc[:-1].tail(20)

        close = safe_float(latest["Close"])
        high = safe_float(latest["High"])
        low = safe_float(latest["Low"])
        volume = float(latest["Volume"]) if pd.notna(latest["Volume"]) else 0.0
        value_est = float(latest["value_est"]) if pd.notna(latest["value_est"]) else 0.0

        avg_volume_20d = float(last_20["Volume"].mean())
        avg_value_20d = float(last_20["value_est"].mean())
        median_value_20d = float(last_20["value_est"].median())
        avg_value_5d = float(clean_df["value_est"].tail(5).mean())
        active_days_20d = int((last_20["Volume"] > 0).sum())
        zero_volume_days_20d = int((last_20["Volume"] <= 0).sum())

        volume_ratio = volume / avg_volume_20d if avg_volume_20d > 0 else None
        value_ratio = value_est / avg_value_20d if avg_value_20d > 0 else None
        # Consistency describes the observed 20-session distribution (including
        # the decision bar), while relative-activity baselines above remain
        # strictly prior-only.
        observed_20 = clean_df.tail(20)
        observed_avg_value = float(observed_20["value_est"].mean())
        observed_median_value = float(observed_20["value_est"].median())
        consistency = observed_median_value / observed_avg_value if observed_avg_value > 0 else None

        high_20d = float(last_20["High"].max())
        low_20d = float(last_20["Low"].min())
        distance_to_20d_high = (high_20d - close) / close if close and close > 0 else None
        distance_from_20d_low = (close - low_20d) / close if close and close > 0 else None

        if close is not None and high is not None and low is not None and high != low:
            close_location = (close - low) / (high - low)
        else:
            close_location = 0.5

        result.update(
            {
                "last_date": str(clean_df.index[-1].date()),
                "close": close,
                "volume": volume,
                "value_est": value_est,
                "avg_volume_20d": avg_volume_20d,
                "avg_value_20d": avg_value_20d,
                "median_value_20d": median_value_20d,
                "avg_value_5d": avg_value_5d,
                "return_1d": safe_pct_change(clean_df["Close"], 1),
                "return_3d": safe_pct_change(clean_df["Close"], 3),
                "return_5d": safe_pct_change(clean_df["Close"], 5),
                "return_20d": safe_pct_change(clean_df["Close"], 20),
                "volume_ratio": volume_ratio,
                "value_ratio": value_ratio,
                "high_20d": high_20d,
                "distance_to_20d_high": distance_to_20d_high,
                "low_20d": low_20d,
                "distance_from_20d_low": distance_from_20d_low,
                "close_location": close_location,
                "active_days_20d": active_days_20d,
                "zero_volume_days_20d": zero_volume_days_20d,
                "value_consistency_ratio": consistency,
                "data_points": data_points,
                "is_data_valid": data_points >= 21,
            }
        )

        if data_points < 21:
            result["reason"] = "insufficient_history"

        return apply_screening_labels(result, config)
    except Exception as exc:
        result["reason"] = f"error: {exc}"
        return apply_screening_labels(result, config)
