"""Tests for P1 Task 9 — MultiBarConfirmation."""

from __future__ import annotations

import pandas as pd
import pytest

from interday_liquidity_screener.enhancements.multibar_confirm import (
    MultiBarConfig,
    MultiBarConfirmation,
    CONFIRMED,
    PENDING_CONFIRMATION,
    NOT_APPLICABLE,
)


def _make_features(rows: list[dict], start_date: str = "2025-06-01") -> pd.DataFrame:
    """Create a features DataFrame from a list of row dicts."""
    dates = pd.date_range(start=start_date, periods=len(rows), freq="B")
    df = pd.DataFrame(rows, index=dates)
    return df


class TestBreakoutConfirmation:
    """Test breakout multi-bar confirmation."""

    def test_2_bars_confirmed(self):
        rows = [
            {"close": 1000, "high_20d": 1010, "close_location": 0.7},  # 1000 >= 1010*0.97=980
            {"close": 1020, "high_20d": 1020, "close_location": 0.8},  # 1020 >= 1020*0.97=989
        ]
        mbc = MultiBarConfirmation(MultiBarConfig(breakout_confirm_bars=2))
        assert mbc.is_breakout_confirmed(_make_features(rows)) is True

    def test_1_bar_fails_pending(self):
        rows = [
            {"close": 900, "high_20d": 1010, "close_location": 0.3},  # fails
            {"close": 1020, "high_20d": 1020, "close_location": 0.8},  # passes
        ]
        mbc = MultiBarConfirmation(MultiBarConfig(breakout_confirm_bars=2))
        assert mbc.is_breakout_confirmed(_make_features(rows)) is False

    def test_close_location_below_threshold_fails(self):
        rows = [
            {"close": 1000, "high_20d": 1000, "close_location": 0.5},  # location < 0.55
            {"close": 1020, "high_20d": 1020, "close_location": 0.8},
        ]
        mbc = MultiBarConfirmation(MultiBarConfig(breakout_confirm_bars=2))
        assert mbc.is_breakout_confirmed(_make_features(rows)) is False

    def test_insufficient_data_returns_false(self):
        rows = [{"close": 1020, "high_20d": 1020, "close_location": 0.8}]  # only 1 bar
        mbc = MultiBarConfirmation(MultiBarConfig(breakout_confirm_bars=2))
        assert mbc.is_breakout_confirmed(_make_features(rows)) is False

    def test_decision_date_slices(self):
        rows = [
            {"close": 1000, "high_20d": 1010, "close_location": 0.7},
            {"close": 1020, "high_20d": 1020, "close_location": 0.8},
            {"close": 800, "high_20d": 1020, "close_location": 0.2},  # crash on day 3
        ]
        features = _make_features(rows)
        mbc = MultiBarConfirmation(MultiBarConfig(breakout_confirm_bars=2))
        # Up to day 2: confirmed
        assert mbc.is_breakout_confirmed(features, decision_date=features.index[1]) is True
        # Up to day 3: last 2 bars are day2 (ok) + day3 (fail)
        assert mbc.is_breakout_confirmed(features, decision_date=features.index[2]) is False


class TestReboundConfirmation:
    """Test rebound multi-bar confirmation."""

    def test_2_bars_confirmed_with_close_location(self):
        rows = [
            {"distance_from_20d_low": 0.05, "close_location": 0.6, "return_1d": -0.01},
            {"distance_from_20d_low": 0.08, "close_location": 0.7, "return_1d": 0.02},
        ]
        mbc = MultiBarConfirmation(MultiBarConfig(rebound_confirm_bars=2))
        assert mbc.is_rebound_confirmed(_make_features(rows)) is True

    def test_2_bars_confirmed_with_return_1d(self):
        rows = [
            {"distance_from_20d_low": 0.05, "close_location": 0.4, "return_1d": 0.03},  # location < 0.55 but return > 0
            {"distance_from_20d_low": 0.08, "close_location": 0.4, "return_1d": 0.01},
        ]
        mbc = MultiBarConfirmation(MultiBarConfig(rebound_confirm_bars=2))
        assert mbc.is_rebound_confirmed(_make_features(rows)) is True

    def test_distance_too_far_fails(self):
        rows = [
            {"distance_from_20d_low": 0.15, "close_location": 0.7, "return_1d": 0.02},  # > 0.10
            {"distance_from_20d_low": 0.05, "close_location": 0.7, "return_1d": 0.02},
        ]
        mbc = MultiBarConfirmation(MultiBarConfig(rebound_confirm_bars=2))
        assert mbc.is_rebound_confirmed(_make_features(rows)) is False

    def test_neither_location_nor_return_fails(self):
        rows = [
            {"distance_from_20d_low": 0.05, "close_location": 0.3, "return_1d": -0.02},  # both fail
            {"distance_from_20d_low": 0.08, "close_location": 0.7, "return_1d": 0.02},
        ]
        mbc = MultiBarConfirmation(MultiBarConfig(rebound_confirm_bars=2))
        assert mbc.is_rebound_confirmed(_make_features(rows)) is False


class TestGetConfirmationStatus:
    """Test the unified get_confirmation_status method."""

    def test_breakout_confirmed(self):
        rows = [
            {"close": 1000, "high_20d": 1000, "close_location": 0.7},
            {"close": 1020, "high_20d": 1020, "close_location": 0.8},
        ]
        mbc = MultiBarConfirmation(MultiBarConfig(breakout_confirm_bars=2))
        assert mbc.get_confirmation_status("BREAKOUT_CANDIDATE", _make_features(rows)) == CONFIRMED

    def test_breakout_pending(self):
        rows = [
            {"close": 800, "high_20d": 1000, "close_location": 0.3},
            {"close": 1020, "high_20d": 1020, "close_location": 0.8},
        ]
        mbc = MultiBarConfirmation(MultiBarConfig(breakout_confirm_bars=2))
        assert mbc.get_confirmation_status("BREAKOUT_CANDIDATE", _make_features(rows)) == PENDING_CONFIRMATION

    def test_rebound_confirmed(self):
        rows = [
            {"distance_from_20d_low": 0.05, "close_location": 0.7, "return_1d": 0.02},
            {"distance_from_20d_low": 0.08, "close_location": 0.6, "return_1d": 0.01},
        ]
        mbc = MultiBarConfirmation(MultiBarConfig(rebound_confirm_bars=2))
        assert mbc.get_confirmation_status("REBOUND_CANDIDATE", _make_features(rows)) == CONFIRMED

    def test_non_applicable_setup(self):
        rows = [{"close": 1000, "high_20d": 1000, "close_location": 0.7}]
        mbc = MultiBarConfirmation()
        assert mbc.get_confirmation_status("WATCH_ENTRY", _make_features(rows)) == NOT_APPLICABLE
        assert mbc.get_confirmation_status("PULLBACK_CANDIDATE", _make_features(rows)) == NOT_APPLICABLE

    def test_empty_history_returns_pending(self):
        mbc = MultiBarConfirmation()
        assert mbc.get_confirmation_status("BREAKOUT_CANDIDATE", pd.DataFrame()) == PENDING_CONFIRMATION

    def test_none_history_returns_pending(self):
        mbc = MultiBarConfirmation()
        # None is handled gracefully
        empty_df = pd.DataFrame()
        assert mbc.get_confirmation_status("REBOUND_NEAR_LOW", empty_df) == PENDING_CONFIRMATION
