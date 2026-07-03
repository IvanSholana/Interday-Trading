from __future__ import annotations

import pandas as pd

from interday_liquidity_screener.classifier import (
    AVOID_FOR_NOW,
    HIGH_LIQUIDITY,
    ILLIQUID,
    INVALID_DATA,
    QUIET,
    STRONG_WATCH,
    WATCH,
    calculate_liquidity_score,
    classify_liquidity_bucket,
    classify_relative_activity,
    classify_trade_candidate,
)
from interday_liquidity_screener.config import ScreenerConfig
from interday_liquidity_screener.metrics import compute_metrics


def make_price_frame(
    days: int = 25,
    close: float = 10_000,
    volume: float = 1_000_000,
    zero_volume_days: int = 0,
    spike_last_day: bool = False,
) -> pd.DataFrame:
    index = pd.date_range("2026-01-01", periods=days, freq="B")
    closes = [close + i for i in range(days)]
    volumes = [volume for _ in range(days)]
    for i in range(min(zero_volume_days, days)):
        volumes[i] = 0
    if spike_last_day:
        volumes = [10_000 for _ in range(days)]
        volumes[-1] = 20_000_000

    return pd.DataFrame(
        {
            "Open": closes,
            "High": [price * 1.01 for price in closes],
            "Low": [price * 0.99 for price in closes],
            "Close": closes,
            "Volume": volumes,
        },
        index=index,
    )


def high_liquidity_row(**overrides) -> dict:
    row = {
        "is_data_valid": True,
        "data_points": 25,
        "avg_value_20d": 100_000_000_000,
        "median_value_20d": 90_000_000_000,
        "active_days_20d": 20,
        "zero_volume_days_20d": 0,
        "value_consistency_ratio": 0.90,
        "value_ratio": 1.2,
        "volume_ratio": 1.2,
        "return_1d": 0.01,
        "return_3d": 0.02,
        "return_5d": 0.03,
        "return_20d": 0.04,
        "close_location": 0.70,
        "distance_to_20d_high": 0.03,
        "distance_from_20d_low": 0.15,
        "liquidity_score": 100,
        "liquidity_bucket": HIGH_LIQUIDITY,
    }
    row.update(overrides)
    return row


def test_score_100_bucket_is_not_watch() -> None:
    score = 100

    assert classify_liquidity_bucket(score) == HIGH_LIQUIDITY
    assert classify_liquidity_bucket(score) != WATCH


def test_big_avg_value_and_full_active_days_is_high_liquidity() -> None:
    row = high_liquidity_row()

    score = calculate_liquidity_score(row, ScreenerConfig())

    assert score == 100
    assert classify_liquidity_bucket(score) == HIGH_LIQUIDITY


def test_quiet_relative_activity_when_value_and_volume_ratios_are_low() -> None:
    row = high_liquidity_row(value_ratio=0.49, volume_ratio=0.49)

    assert classify_relative_activity(row) == QUIET


def test_liquid_stock_closing_at_low_is_not_strong_watch_or_buy() -> None:
    row = high_liquidity_row(close_location=0.0)

    assert classify_trade_candidate(row) == AVOID_FOR_NOW
    assert classify_trade_candidate(row) != STRONG_WATCH


def test_invalid_data_produces_invalid_trade_candidate() -> None:
    row = high_liquidity_row(is_data_valid=False, data_points=0)

    assert calculate_liquidity_score(row, ScreenerConfig()) == 0
    assert classify_liquidity_bucket(0) == ILLIQUID
    assert classify_trade_candidate(row) == INVALID_DATA


def test_compute_metrics_classifies_consistent_liquid_stock() -> None:
    metrics = compute_metrics("BBCA.JK", make_price_frame(), ScreenerConfig())

    assert metrics["liquidity_bucket"] == HIGH_LIQUIDITY
    assert metrics["trade_candidate_bucket"] in {STRONG_WATCH, WATCH, AVOID_FOR_NOW}
    assert metrics["active_days_20d"] == 20
    assert metrics["zero_volume_days_20d"] == 0
    assert metrics["median_value_20d"] >= 3_000_000_000


def test_short_history_is_invalid_for_trade_candidate() -> None:
    metrics = compute_metrics("TEST.JK", make_price_frame(days=10), ScreenerConfig())

    assert metrics["liquidity_bucket"] == ILLIQUID
    assert metrics["trade_candidate_bucket"] == INVALID_DATA
    assert metrics["reason"] == "invalid_data_insufficient_history"


def test_many_zero_volume_days_reduces_absolute_liquidity_score() -> None:
    metrics = compute_metrics(
        "SLEEP.JK",
        make_price_frame(volume=1_000_000, zero_volume_days=16),
        ScreenerConfig(),
    )

    assert metrics["liquidity_bucket"] != HIGH_LIQUIDITY


def test_spike_driven_value_is_not_high_liquidity() -> None:
    metrics = compute_metrics(
        "SPIKE.JK",
        make_price_frame(spike_last_day=True),
        ScreenerConfig(),
    )

    assert metrics["liquidity_bucket"] != HIGH_LIQUIDITY
    assert metrics["value_consistency_ratio"] < 0.50
