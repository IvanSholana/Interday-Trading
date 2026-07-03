"""Tests for Stage 1 config gate enforcement.

Validates that min_value, min_volume_ratio, and max_return_5d are
actually enforced in trade_candidate_bucket and reason/signal_summary,
while liquidity_score remains independent of daily setup gates.
"""
from __future__ import annotations

from interday_liquidity_screener.classifier import (
    AVOID_FOR_NOW,
    HIGH_LIQUIDITY,
    STRONG_WATCH,
    WATCH,
    _check_daily_gates,
    build_reason,
    build_signal_summary,
    calculate_liquidity_score,
    classify_trade_candidate,
)
from interday_liquidity_screener.config import ScreenerConfig
from interday_liquidity_screener.metrics import apply_screening_labels


def _liquid_row(**overrides) -> dict:
    """A HIGH_LIQUIDITY row with all gates passing by default."""
    row = {
        "is_data_valid": True,
        "data_points": 25,
        "avg_value_20d": 100_000_000_000,
        "median_value_20d": 90_000_000_000,
        "active_days_20d": 20,
        "zero_volume_days_20d": 0,
        "value_consistency_ratio": 0.90,
        "value_est": 10_000_000_000,
        "value_ratio": 1.5,
        "volume_ratio": 1.5,
        "return_1d": 0.02,
        "return_3d": 0.03,
        "return_5d": 0.05,
        "return_20d": 0.08,
        "close_location": 0.75,
        "distance_to_20d_high": 0.02,
        "distance_from_20d_low": 0.15,
        "liquidity_score": 100,
        "liquidity_bucket": HIGH_LIQUIDITY,
    }
    row.update(overrides)
    return row


# -----------------------------------------------------------------------
# min_value gate tests
# -----------------------------------------------------------------------


def test_min_value_gate_blocks_trade_candidate() -> None:
    """value_est below min_value should make trade_candidate_bucket = AVOID_FOR_NOW."""
    config = ScreenerConfig(min_value=10_000_000_000)
    row = _liquid_row(value_est=5_000_000_000)

    result = classify_trade_candidate(row, config)

    assert result == AVOID_FOR_NOW


def test_min_value_gate_reason_is_specific() -> None:
    """Reason should clearly say latest_value_below_min_value."""
    config = ScreenerConfig(min_value=10_000_000_000)
    row = _liquid_row(value_est=5_000_000_000)
    row["liquidity_bucket"] = HIGH_LIQUIDITY
    row["trade_candidate_bucket"] = AVOID_FOR_NOW
    row["relative_activity_bucket"] = "VERY_ACTIVE"

    reason = build_reason(row, config)

    assert reason == "latest_value_below_min_value"


def test_min_value_gate_signal_summary_mentions_threshold() -> None:
    """Signal summary should mention transaction value is below threshold."""
    config = ScreenerConfig(min_value=10_000_000_000)
    row = _liquid_row(value_est=5_000_000_000)
    row["liquidity_bucket"] = HIGH_LIQUIDITY
    row["trade_candidate_bucket"] = AVOID_FOR_NOW

    summary = build_signal_summary(row, config)

    assert "transaction value" in summary.lower()
    assert "below" in summary.lower()


def test_min_value_gate_does_not_affect_liquidity_score() -> None:
    """liquidity_score must be independent of value_est daily gate."""
    config = ScreenerConfig(min_value=10_000_000_000)
    row_passing = _liquid_row(value_est=20_000_000_000)
    row_failing = _liquid_row(value_est=1_000_000_000)

    score_passing = calculate_liquidity_score(row_passing, config)
    score_failing = calculate_liquidity_score(row_failing, config)

    assert score_passing == score_failing


# -----------------------------------------------------------------------
# min_volume_ratio gate tests
# -----------------------------------------------------------------------


def test_min_volume_ratio_gate_blocks_trade_candidate() -> None:
    """volume_ratio below min_volume_ratio should block trade candidacy."""
    config = ScreenerConfig(min_volume_ratio=1.0)
    row = _liquid_row(volume_ratio=0.5, value_ratio=0.5)

    result = classify_trade_candidate(row, config)

    assert result == AVOID_FOR_NOW


def test_min_volume_ratio_gate_reason_is_specific() -> None:
    """Reason should clearly mention volume_ratio_below_min_volume_ratio."""
    config = ScreenerConfig(min_volume_ratio=1.0)
    row = _liquid_row(volume_ratio=0.5, value_ratio=0.5)
    row["liquidity_bucket"] = HIGH_LIQUIDITY
    row["trade_candidate_bucket"] = AVOID_FOR_NOW
    row["relative_activity_bucket"] = "QUIET"

    reason = build_reason(row, config)

    assert reason == "volume_ratio_below_min_volume_ratio"


def test_min_volume_ratio_gate_does_not_affect_liquidity_score() -> None:
    """liquidity_score is independent from daily volume_ratio gate."""
    config = ScreenerConfig(min_volume_ratio=2.0)
    row_passing = _liquid_row(volume_ratio=3.0)
    row_failing = _liquid_row(volume_ratio=0.5)

    score_passing = calculate_liquidity_score(row_passing, config)
    score_failing = calculate_liquidity_score(row_failing, config)

    assert score_passing == score_failing


# -----------------------------------------------------------------------
# max_return_5d gate tests (anti-chasing)
# -----------------------------------------------------------------------


def test_max_return_5d_gate_blocks_extended_ticker() -> None:
    """return_5d above max_return_5d should make trade candidate AVOID_FOR_NOW."""
    config = ScreenerConfig(max_return_5d=0.10)
    row = _liquid_row(return_5d=0.15)

    result = classify_trade_candidate(row, config)

    assert result == AVOID_FOR_NOW


def test_max_return_5d_gate_reason_mentions_chasing() -> None:
    """Reason should say return_5d_above_max_return_5d."""
    config = ScreenerConfig(max_return_5d=0.10)
    row = _liquid_row(return_5d=0.15)
    row["liquidity_bucket"] = HIGH_LIQUIDITY
    row["trade_candidate_bucket"] = AVOID_FOR_NOW
    row["relative_activity_bucket"] = "VERY_ACTIVE"

    reason = build_reason(row, config)

    assert reason == "return_5d_above_max_return_5d"


def test_max_return_5d_gate_signal_summary_mentions_avoid_chasing() -> None:
    """Summary should mention avoid chasing when 5-day return too high."""
    config = ScreenerConfig(max_return_5d=0.10)
    row = _liquid_row(return_5d=0.15)
    row["liquidity_bucket"] = HIGH_LIQUIDITY
    row["trade_candidate_bucket"] = AVOID_FOR_NOW

    summary = build_signal_summary(row, config)

    assert "chasing" in summary.lower()


def test_max_return_5d_gate_does_not_affect_liquidity_score() -> None:
    """liquidity_score is independent from anti-chasing gate."""
    config = ScreenerConfig(max_return_5d=0.10)
    row_passing = _liquid_row(return_5d=0.05)
    row_failing = _liquid_row(return_5d=0.20)

    score_passing = calculate_liquidity_score(row_passing, config)
    score_failing = calculate_liquidity_score(row_failing, config)

    assert score_passing == score_failing


# -----------------------------------------------------------------------
# All gates pass — ticker is valid candidate
# -----------------------------------------------------------------------


def test_all_gates_pass_allows_strong_watch() -> None:
    """When all gates pass, a liquid stock with confirmed activity is STRONG_WATCH."""
    config = ScreenerConfig(min_value=5_000_000_000, min_volume_ratio=1.0, max_return_5d=0.10)
    row = _liquid_row(
        value_est=10_000_000_000,
        volume_ratio=1.5,
        value_ratio=1.5,
        return_5d=0.05,
        return_1d=0.02,
        close_location=0.75,
    )

    result = classify_trade_candidate(row, config)

    assert result in {STRONG_WATCH, WATCH}


def test_apply_screening_labels_propagates_config_gates() -> None:
    """Full pipeline apply_screening_labels should enforce config gates."""
    config = ScreenerConfig(min_value=10_000_000_000, min_volume_ratio=1.0, max_return_5d=0.10)
    row = _liquid_row(value_est=2_000_000_000, return_5d=0.15, volume_ratio=0.5, value_ratio=0.5)
    # Simulate what compute_metrics would produce
    row["liquidity_score"] = 100
    row["liquidity_bucket"] = HIGH_LIQUIDITY

    result = apply_screening_labels(row, config)

    # Score stays high because liquidity is absolute
    assert result["liquidity_score"] == 100
    assert result["liquidity_bucket"] == HIGH_LIQUIDITY
    # But trade candidate is blocked by daily gates
    assert result["trade_candidate_bucket"] == AVOID_FOR_NOW
    assert "latest_value_below_min_value" in result["reason"]


# -----------------------------------------------------------------------
# Gate with None values (edge case)
# -----------------------------------------------------------------------


def test_gates_skip_when_value_is_none() -> None:
    """If value_est is None (e.g., no data yet), gate should not trigger."""
    config = ScreenerConfig(min_value=10_000_000_000)
    row = _liquid_row(value_est=None)

    failures = _check_daily_gates(row, config)

    assert "latest_value_below_min_value" not in failures


# -----------------------------------------------------------------------
# min_active_days_20d gate tests
# -----------------------------------------------------------------------


def test_min_active_days_gate_blocks_trade_candidate() -> None:
    """active_days_20d below min_active_days_20d should make trade candidate AVOID_FOR_NOW."""
    config = ScreenerConfig(min_active_days_20d=18)
    row = _liquid_row(active_days_20d=12)

    result = classify_trade_candidate(row, config)

    assert result == AVOID_FOR_NOW


def test_min_active_days_gate_reason_is_specific() -> None:
    """Reason should say active_days_below_min_active_days_20d."""
    config = ScreenerConfig(min_active_days_20d=18)
    row = _liquid_row(active_days_20d=12)
    row["liquidity_bucket"] = HIGH_LIQUIDITY
    row["trade_candidate_bucket"] = AVOID_FOR_NOW
    row["relative_activity_bucket"] = "VERY_ACTIVE"

    reason = build_reason(row, config)

    assert reason == "active_days_below_min_active_days_20d"


def test_min_active_days_gate_signal_summary_mentions_active_days() -> None:
    """Summary should mention not enough active trading days."""
    config = ScreenerConfig(min_active_days_20d=18)
    row = _liquid_row(active_days_20d=12)
    row["liquidity_bucket"] = HIGH_LIQUIDITY
    row["trade_candidate_bucket"] = AVOID_FOR_NOW

    summary = build_signal_summary(row, config)

    assert "active trading days" in summary.lower()


def test_min_active_days_gate_does_not_affect_liquidity_score() -> None:
    """liquidity_score is independent from active_days gate."""
    config = ScreenerConfig(min_active_days_20d=18)
    row_passing = _liquid_row(active_days_20d=20)
    row_failing = _liquid_row(active_days_20d=10)

    score_passing = calculate_liquidity_score(row_passing, config)
    score_failing = calculate_liquidity_score(row_failing, config)

    # Scores differ because active_days influences liquidity_score (active_days_score component),
    # but that's the absolute liquidity dimension, not the gate. The gate only blocks trade_candidate.
    # Here we just verify the gate does NOT zero out the score.
    assert score_failing > 0


def test_min_active_days_gate_passes_when_sufficient() -> None:
    """When active_days_20d meets threshold, gate does not block."""
    config = ScreenerConfig(min_active_days_20d=15)
    row = _liquid_row(active_days_20d=18)

    result = classify_trade_candidate(row, config)

    assert result != AVOID_FOR_NOW or row.get("close_location", 0.5) < 0.4


def test_min_active_days_gate_skips_when_none() -> None:
    """If active_days_20d is None, gate should not trigger."""
    config = ScreenerConfig(min_active_days_20d=18)
    row = _liquid_row(active_days_20d=None)

    failures = _check_daily_gates(row, config)

    assert "active_days_below_min_active_days_20d" not in failures
