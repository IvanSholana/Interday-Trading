"""Tests for Task 17 — BlackoutFilter."""

from __future__ import annotations

import pandas as pd
import pytest

from interday_liquidity_screener.enhancements.blackout import (
    BlackoutConfig,
    BlackoutFilter,
)


class TestBlackoutWithinWindow:
    """Decision date within blackout window returns True."""

    def test_decision_one_day_before_event(self):
        config = BlackoutConfig(days_before=3, days_after=1)
        flt = BlackoutFilter(config)
        event_date = pd.Timestamp("2025-03-15")
        decision_date = pd.Timestamp("2025-03-14")
        events = {"BBRI.JK": [event_date]}
        assert flt.is_in_blackout("BBRI.JK", decision_date, events) is True

    def test_decision_on_event_date(self):
        flt = BlackoutFilter()
        event_date = pd.Timestamp("2025-03-15")
        events = {"BBRI.JK": [event_date]}
        assert flt.is_in_blackout("BBRI.JK", event_date, events) is True

    def test_decision_one_day_after_event(self):
        config = BlackoutConfig(days_before=3, days_after=1)
        flt = BlackoutFilter(config)
        event_date = pd.Timestamp("2025-03-15")
        decision_date = pd.Timestamp("2025-03-16")
        events = {"BBRI.JK": [event_date]}
        assert flt.is_in_blackout("BBRI.JK", decision_date, events) is True


class TestBlackoutOutsideWindow:
    """Decision date outside blackout window returns False."""

    def test_decision_well_before_event(self):
        config = BlackoutConfig(days_before=3, days_after=1)
        flt = BlackoutFilter(config)
        event_date = pd.Timestamp("2025-03-15")
        decision_date = pd.Timestamp("2025-03-10")
        events = {"BBRI.JK": [event_date]}
        assert flt.is_in_blackout("BBRI.JK", decision_date, events) is False

    def test_decision_well_after_event(self):
        config = BlackoutConfig(days_before=3, days_after=1)
        flt = BlackoutFilter(config)
        event_date = pd.Timestamp("2025-03-15")
        decision_date = pd.Timestamp("2025-03-20")
        events = {"BBRI.JK": [event_date]}
        assert flt.is_in_blackout("BBRI.JK", decision_date, events) is False


class TestBlackoutDisabled:
    """Disabled filter always returns False."""

    def test_disabled_returns_false_even_on_event_date(self):
        config = BlackoutConfig(enabled=False)
        flt = BlackoutFilter(config)
        event_date = pd.Timestamp("2025-03-15")
        events = {"BBRI.JK": [event_date]}
        assert flt.is_in_blackout("BBRI.JK", event_date, events) is False

    def test_disabled_returns_false_within_window(self):
        config = BlackoutConfig(enabled=False, days_before=5, days_after=5)
        flt = BlackoutFilter(config)
        event_date = pd.Timestamp("2025-03-15")
        decision_date = pd.Timestamp("2025-03-14")
        events = {"BBRI.JK": [event_date]}
        assert flt.is_in_blackout("BBRI.JK", decision_date, events) is False


class TestBlackoutMissingTicker:
    """Missing ticker events returns False."""

    def test_ticker_not_in_events_dict(self):
        flt = BlackoutFilter()
        decision_date = pd.Timestamp("2025-03-15")
        events = {"TLKM.JK": [pd.Timestamp("2025-03-15")]}
        assert flt.is_in_blackout("BBRI.JK", decision_date, events) is False

    def test_empty_events_dict(self):
        flt = BlackoutFilter()
        decision_date = pd.Timestamp("2025-03-15")
        assert flt.is_in_blackout("BBRI.JK", decision_date, {}) is False

    def test_ticker_with_empty_event_list(self):
        flt = BlackoutFilter()
        decision_date = pd.Timestamp("2025-03-15")
        events = {"BBRI.JK": []}
        assert flt.is_in_blackout("BBRI.JK", decision_date, events) is False


class TestBlackoutMultipleEvents:
    """Multiple events are all checked."""

    def test_in_window_of_second_event(self):
        config = BlackoutConfig(days_before=2, days_after=1)
        flt = BlackoutFilter(config)
        events = {
            "BBRI.JK": [
                pd.Timestamp("2025-01-15"),
                pd.Timestamp("2025-04-15"),
            ]
        }
        # Far from first, within window of second
        decision_date = pd.Timestamp("2025-04-14")
        assert flt.is_in_blackout("BBRI.JK", decision_date, events) is True

    def test_outside_all_event_windows(self):
        config = BlackoutConfig(days_before=2, days_after=1)
        flt = BlackoutFilter(config)
        events = {
            "BBRI.JK": [
                pd.Timestamp("2025-01-15"),
                pd.Timestamp("2025-04-15"),
            ]
        }
        decision_date = pd.Timestamp("2025-03-01")
        assert flt.is_in_blackout("BBRI.JK", decision_date, events) is False


class TestBlackoutEdgeCases:
    """Edge cases: decision_date exactly on window_start and window_end."""

    def test_exactly_on_window_start(self):
        config = BlackoutConfig(days_before=3, days_after=1)
        flt = BlackoutFilter(config)
        event_date = pd.Timestamp("2025-03-15")
        # window_start = 2025-03-12
        window_start = pd.Timestamp("2025-03-12")
        events = {"BBRI.JK": [event_date]}
        assert flt.is_in_blackout("BBRI.JK", window_start, events) is True

    def test_exactly_on_window_end(self):
        config = BlackoutConfig(days_before=3, days_after=1)
        flt = BlackoutFilter(config)
        event_date = pd.Timestamp("2025-03-15")
        # window_end = 2025-03-16
        window_end = pd.Timestamp("2025-03-16")
        events = {"BBRI.JK": [event_date]}
        assert flt.is_in_blackout("BBRI.JK", window_end, events) is True

    def test_one_day_before_window_start(self):
        config = BlackoutConfig(days_before=3, days_after=1)
        flt = BlackoutFilter(config)
        event_date = pd.Timestamp("2025-03-15")
        # window_start = 2025-03-12, so 2025-03-11 is outside
        decision_date = pd.Timestamp("2025-03-11")
        events = {"BBRI.JK": [event_date]}
        assert flt.is_in_blackout("BBRI.JK", decision_date, events) is False

    def test_one_day_after_window_end(self):
        config = BlackoutConfig(days_before=3, days_after=1)
        flt = BlackoutFilter(config)
        event_date = pd.Timestamp("2025-03-15")
        # window_end = 2025-03-16, so 2025-03-17 is outside
        decision_date = pd.Timestamp("2025-03-17")
        events = {"BBRI.JK": [event_date]}
        assert flt.is_in_blackout("BBRI.JK", decision_date, events) is False

    def test_custom_window_sizes(self):
        config = BlackoutConfig(days_before=5, days_after=3)
        flt = BlackoutFilter(config)
        event_date = pd.Timestamp("2025-06-10")
        # window: [2025-06-05, 2025-06-13]
        assert flt.is_in_blackout("BBRI.JK", pd.Timestamp("2025-06-05"), {"BBRI.JK": [event_date]}) is True
        assert flt.is_in_blackout("BBRI.JK", pd.Timestamp("2025-06-13"), {"BBRI.JK": [event_date]}) is True
        assert flt.is_in_blackout("BBRI.JK", pd.Timestamp("2025-06-04"), {"BBRI.JK": [event_date]}) is False
        assert flt.is_in_blackout("BBRI.JK", pd.Timestamp("2025-06-14"), {"BBRI.JK": [event_date]}) is False
