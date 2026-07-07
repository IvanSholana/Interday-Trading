"""Tests for Task 15 — Verify dead config enforcement (min_volume_ratio, max_return_5d)."""

from __future__ import annotations

import pytest

from interday_liquidity_screener.config import ScreenerConfig
from interday_liquidity_screener.classifier import (
    STRONG_WATCH,
    WATCH,
    AVOID_FOR_NOW,
    HIGH_LIQUIDITY,
    GOOD_LIQUIDITY,
    classify_trade_candidate,
    build_reason,
)


def _base_row(**overrides) -> dict:
    """Create a valid high-liquidity row that passes all gates by default."""
    row = {
        "is_data_valid": True,
        "data_points": 25,
        "liquidity_bucket": HIGH_LIQUIDITY,
        "relative_activity_bucket": "ACTIVE",
        "trade_candidate_bucket": None,
        "avg_value_20d": 10_000_000_000,
        "median_value_20d": 8_000_000_000,
        "active_days_20d": 18,
        "zero_volume_days_20d": 0,
        "value_consistency_ratio": 0.7,
        "value_est": 10_000_000_000,
        "volume_ratio": 1.5,
        "value_ratio": 1.5,
        "return_1d": 0.02,
        "return_3d": 0.01,
        "return_5d": 0.03,
        "return_20d": 0.05,
        "close_location": 0.7,
        "distance_to_20d_high": 0.05,
        "distance_from_20d_low": 0.15,
    }
    row.update(overrides)
    return row


class TestVolumeRatioGate:
    """Verify min_volume_ratio enforcement in Stage 1 screening."""

    def test_volume_ratio_below_threshold_returns_avoid(self):
        config = ScreenerConfig(min_volume_ratio=1.0)
        row = _base_row(volume_ratio=0.5)
        result = classify_trade_candidate(row, config)
        assert result == AVOID_FOR_NOW

    def test_volume_ratio_exactly_at_threshold_passes(self):
        config = ScreenerConfig(min_volume_ratio=1.0)
        row = _base_row(volume_ratio=1.0)
        result = classify_trade_candidate(row, config)
        assert result in {STRONG_WATCH, WATCH}

    def test_volume_ratio_above_threshold_passes(self):
        config = ScreenerConfig(min_volume_ratio=1.0)
        row = _base_row(volume_ratio=2.0)
        result = classify_trade_candidate(row, config)
        assert result in {STRONG_WATCH, WATCH}

    def test_custom_volume_ratio_threshold(self):
        config = ScreenerConfig(min_volume_ratio=2.0)
        row = _base_row(volume_ratio=1.5)
        result = classify_trade_candidate(row, config)
        assert result == AVOID_FOR_NOW


class TestReturn5dGate:
    """Verify max_return_5d enforcement in Stage 1 screening."""

    def test_return_5d_above_threshold_returns_avoid(self):
        config = ScreenerConfig(max_return_5d=0.10)
        row = _base_row(return_5d=0.15)
        result = classify_trade_candidate(row, config)
        assert result == AVOID_FOR_NOW

    def test_return_5d_exactly_at_threshold_passes(self):
        config = ScreenerConfig(max_return_5d=0.10)
        row = _base_row(return_5d=0.10)
        result = classify_trade_candidate(row, config)
        assert result in {STRONG_WATCH, WATCH}

    def test_return_5d_below_threshold_passes(self):
        config = ScreenerConfig(max_return_5d=0.10)
        row = _base_row(return_5d=0.05)
        result = classify_trade_candidate(row, config)
        assert result in {STRONG_WATCH, WATCH}

    def test_custom_return_5d_threshold(self):
        config = ScreenerConfig(max_return_5d=0.05)
        row = _base_row(return_5d=0.08)
        result = classify_trade_candidate(row, config)
        assert result == AVOID_FOR_NOW


class TestBothGatesPass:
    """Verify that a ticker passing both gates gets STRONG_WATCH or WATCH."""

    def test_passing_both_gates_with_strong_signal(self):
        config = ScreenerConfig(min_volume_ratio=1.0, max_return_5d=0.10)
        row = _base_row(volume_ratio=1.5, return_5d=0.03, value_ratio=1.5)
        result = classify_trade_candidate(row, config)
        assert result in {STRONG_WATCH, WATCH}

    def test_passing_both_gates_good_liquidity(self):
        config = ScreenerConfig(min_volume_ratio=1.0, max_return_5d=0.10)
        row = _base_row(
            liquidity_bucket=GOOD_LIQUIDITY,
            volume_ratio=1.2,
            return_5d=0.05,
        )
        result = classify_trade_candidate(row, config)
        assert result in {STRONG_WATCH, WATCH}


class TestBuildReasonGateFailures:
    """Verify build_reason() returns specific gate failure reason strings."""

    def test_reason_volume_ratio_below_min(self):
        config = ScreenerConfig(min_volume_ratio=1.0)
        row = _base_row(volume_ratio=0.5)
        reason = build_reason(row, config)
        assert reason == "volume_ratio_below_min_volume_ratio"

    def test_reason_return_5d_above_max(self):
        config = ScreenerConfig(max_return_5d=0.10)
        row = _base_row(return_5d=0.20)
        reason = build_reason(row, config)
        assert reason == "return_5d_above_max_return_5d"

    def test_reason_for_passing_ticker_is_not_gate_failure(self):
        config = ScreenerConfig(min_volume_ratio=1.0, max_return_5d=0.10)
        row = _base_row(volume_ratio=1.5, return_5d=0.03)
        reason = build_reason(row, config)
        assert reason != "volume_ratio_below_min_volume_ratio"
        assert reason != "return_5d_above_max_return_5d"
