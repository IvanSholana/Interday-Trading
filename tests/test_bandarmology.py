from __future__ import annotations

import pandas as pd

from interday_liquidity_screener.bandarmology import (
    aggregate_multi_window_scores,
    calculate_bandarmology_score,
    calculate_buyer_seller_features,
    calculate_hhi,
    classify_bandarmology_signal,
    classify_final_bandarmology_signal,
    build_bandarmology_reason,
    run_stage3b_bandarmology_scoring,
    score_single_window,
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


def test_all_big_acc_windows_classify_final_strong_accumulation() -> None:
    row = {
        "weighted_bandarmology_score": 85,
        "accumulation_window_count": 5,
        "distribution_window_count": 0,
        "strong_distribution_window_count": 0,
        "signal_1d": "STRONG_ACCUMULATION",
        "medium_term_score": 80,
    }

    assert classify_final_bandarmology_signal(row) == "STRONG_ACCUMULATION"


def test_all_big_dist_windows_classify_final_strong_distribution() -> None:
    row = {
        "weighted_bandarmology_score": 20,
        "accumulation_window_count": 0,
        "distribution_window_count": 5,
        "strong_distribution_window_count": 5,
        "signal_1d": "STRONG_DISTRIBUTION",
        "medium_term_score": 20,
    }

    assert classify_final_bandarmology_signal(row) == "STRONG_DISTRIBUTION"


def test_short_term_accumulation_against_medium_distribution() -> None:
    row = {
        "weighted_bandarmology_score": 50,
        "accumulation_window_count": 1,
        "distribution_window_count": 3,
        "strong_distribution_window_count": 1,
        "signal_1d": "MILD_ACCUMULATION",
        "medium_term_score": 40,
    }

    assert classify_final_bandarmology_signal(row) == "SHORT_TERM_ACCUMULATION_AGAINST_MEDIUM_DISTRIBUTION"


def test_pullback_with_medium_accumulation() -> None:
    row = {
        "weighted_bandarmology_score": 62,
        "accumulation_window_count": 2,
        "distribution_window_count": 1,
        "strong_distribution_window_count": 0,
        "signal_1d": "MILD_DISTRIBUTION",
        "medium_term_score": 70,
    }

    assert classify_final_bandarmology_signal(row) == "PULLBACK_WITH_MEDIUM_ACCUMULATION"


def test_missing_window_weights_are_renormalized() -> None:
    result = aggregate_multi_window_scores({"1D": 100, "3D": None, "5D": 50})

    assert round(result["short_term_score"], 2) == 68.75


def test_no_window_scores_classify_no_broker_data() -> None:
    assert classify_final_bandarmology_signal({"weighted_bandarmology_score": None}) == "NO_BROKER_DATA"


def test_single_window_score_clamped() -> None:
    row = {
        "broker_activity_available": True,
        "broker_accdist": "Big Acc",
        "avg_accdist": "Big Acc",
        "top3_accdist": "Big Acc",
        "top5_accdist": "Big Acc",
        "avg_percent": 100,
        "avg_amount": 100,
        "relative_activity_bucket": "VERY_ACTIVE",
        "technical_context": "BREAKOUT_NEAR",
        "momentum_score": 100,
        "close_location": 1,
        "close": 100,
        "detector_average_price": 100,
    }

    assert score_single_window(row, {}) == 100


def test_stage3b_handles_empty_stage3a_csv_files(tmp_path) -> None:
    stage2_path = tmp_path / "stage2.csv"
    detector_path = tmp_path / "stage3a_bandar_detector_summary.csv"
    broker_path = tmp_path / "stage3a_broker_summary_long.csv"
    output_path = tmp_path / "stage3b.csv"

    pd.DataFrame(
        [
            {
                "ticker": "BBRI",
                "last_date": "2026-07-04",
                "close": 3000,
                "relative_activity_bucket": "NORMAL",
                "technical_context": "BREAKOUT_NEAR",
                "momentum_score": 60,
                "close_location": 0.7,
            }
        ]
    ).to_csv(stage2_path, index=False)
    detector_path.write_text("", encoding="utf-8")
    broker_path.write_text("", encoding="utf-8")

    result = run_stage3b_bandarmology_scoring(stage2_path, detector_path, broker_path, output_path)

    assert result.loc[0, "bandarmology_signal"] == "NO_BROKER_DATA"
    assert output_path.exists()
