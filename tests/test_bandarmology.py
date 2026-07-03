from __future__ import annotations

import pandas as pd

from interday_liquidity_screener.bandarmology import (
    calculate_bandarmology_score,
    calculate_buyer_seller_features,
    calculate_hhi,
    classify_bandarmology_signal,
    build_bandarmology_reason,
)


def test_calculate_hhi_simple_distribution() -> None:
    assert round(calculate_hhi([50, 50]), 2) == 0.50


def test_empty_broker_data_classifies_no_broker_data() -> None:
    assert classify_bandarmology_signal(None, False) == "NO_BROKER_DATA"


def test_top_buyer_seller_features_from_long_sample_data() -> None:
    df = pd.DataFrame(
        [
            {"ticker": "BBRI", "side": "BUY", "broker_code": "YP", "net_value": 100, "net_lot": 10, "avg_price": 2700},
            {"ticker": "BBRI", "side": "BUY", "broker_code": "AK", "net_value": 80, "net_lot": 8, "avg_price": 2690},
            {"ticker": "BBRI", "side": "SELL", "broker_code": "CC", "net_value": 50, "net_lot": 5, "avg_price": 2710},
        ]
    )
    features = calculate_buyer_seller_features(df).iloc[0]

    assert features["top_buyer_1_code"] == "YP"
    assert features["top_seller_1_code"] == "CC"
    assert features["top3_buyer_value"] == 180


def test_accumulation_score_and_classification() -> None:
    row = {
        "broker_activity_available": True,
        "broker_accdist": "Big Acc",
        "avg_accdist": "Acc",
        "top3_accdist": "Acc",
        "top5_accdist": "Acc",
        "avg_percent": 25,
        "avg_amount": 100,
        "relative_activity_bucket": "ACTIVE",
        "technical_context": "BREAKOUT_NEAR",
        "momentum_score": 70,
        "close_location": 0.7,
        "close": 100,
        "detector_average_price": 100,
    }

    score = calculate_bandarmology_score(row)
    assert 0 <= score <= 100
    assert classify_bandarmology_signal(score, True) == "STRONG_ACCUMULATION"


def test_distribution_detector_does_not_classify_accumulation() -> None:
    row = {
        "broker_activity_available": True,
        "broker_accdist": "Dist",
        "avg_accdist": "Big Dist",
        "avg_amount": -1140144500000,
        "avg_percent": -30.7,
        "top3_accdist": "Big Dist",
        "top5_accdist": "Big Dist",
        "relative_activity_bucket": "NORMAL",
        "technical_context": "REBOUND_NEAR_LOW",
        "momentum_score": 45,
        "close_location": 0.6,
        "close": 2690,
        "detector_average_price": 2812,
    }

    score = calculate_bandarmology_score(row)
    signal = classify_bandarmology_signal(score, True)
    row["bandarmology_signal"] = signal

    assert signal in {"STRONG_DISTRIBUTION", "MILD_DISTRIBUTION"}
    assert signal not in {"STRONG_ACCUMULATION", "MILD_ACCUMULATION"}
    assert "distribution" in build_bandarmology_reason(row)
