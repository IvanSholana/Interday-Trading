"""Tests for P1 Task 7 — Enhanced Bandarmology Scoring (HHI, Top3 Dominance, Close vs Top Buyer Avg)."""

from __future__ import annotations

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from interday_liquidity_screener.bandarmology import (
    score_single_window,
    calculate_broker_features,
    calculate_hhi,
)
import pandas as pd


def _base_row(**overrides) -> dict:
    """Create a minimal bandarmology row with moderate/neutral defaults so new contributions are visible."""
    row = {
        "broker_activity_available": True,
        "broker_accdist": None,  # neutral — no acc/dist label
        "avg_accdist": None,
        "top3_accdist": None,
        "top5_accdist": None,
        "avg_percent": 0.0,  # neutral
        "avg_amount": 0.0,  # neutral
        "relative_activity_bucket": "QUIET",  # no bonus
        "close_location": 0.4,  # below 0.6, no bonus
        "momentum_score": 40,  # below 60, no bonus
        "technical_context": "TECHNICALLY_WEAK_BUT_LIQUID",  # no bonus
        "detector_average_price": 1000,
        "close": 1050,  # not > 1.10 * detector so no penalty
        # New P1 fields
        "buyer_hhi": None,
        "top3_buyer_value": None,
        "top3_seller_value": None,
        "close_vs_top_buyer_avg": None,
    }
    row.update(overrides)
    return row


class TestBuyerHHIContribution:
    """Property 15: Buyer HHI Contribution — setting buyer_hhi >= 0.25 increases score."""

    def test_high_hhi_increases_score(self):
        base_score = score_single_window(_base_row(buyer_hhi=0.0))
        high_hhi_score = score_single_window(_base_row(buyer_hhi=0.25))
        assert high_hhi_score > base_score

    def test_medium_hhi_increases_score(self):
        base_score = score_single_window(_base_row(buyer_hhi=0.0))
        medium_hhi_score = score_single_window(_base_row(buyer_hhi=0.15))
        assert medium_hhi_score > base_score

    def test_low_hhi_no_change(self):
        base_score = score_single_window(_base_row(buyer_hhi=0.0))
        low_hhi_score = score_single_window(_base_row(buyer_hhi=0.10))
        assert low_hhi_score == base_score

    def test_missing_hhi_no_change(self):
        with_none = score_single_window(_base_row(buyer_hhi=None))
        with_zero = score_single_window(_base_row(buyer_hhi=0.0))
        assert with_none == with_zero


class TestTop3DominanceContribution:
    """Property 16: Top3 Dominance Contribution — ratio >= 2.0 increases score."""

    def test_strong_buyer_dominance_increases_score(self):
        base_score = score_single_window(_base_row(top3_buyer_value=100, top3_seller_value=100))
        dominant_score = score_single_window(_base_row(top3_buyer_value=200, top3_seller_value=100))
        assert dominant_score > base_score

    def test_moderate_buyer_dominance_increases_score(self):
        base_score = score_single_window(_base_row(top3_buyer_value=100, top3_seller_value=100))
        moderate_score = score_single_window(_base_row(top3_buyer_value=140, top3_seller_value=100))
        assert moderate_score > base_score

    def test_strong_seller_dominance_decreases_score(self):
        base_score = score_single_window(_base_row(top3_buyer_value=100, top3_seller_value=100))
        seller_dom_score = score_single_window(_base_row(top3_buyer_value=40, top3_seller_value=100))
        assert seller_dom_score < base_score

    def test_moderate_seller_dominance_decreases_score(self):
        base_score = score_single_window(_base_row(top3_buyer_value=100, top3_seller_value=100))
        seller_score = score_single_window(_base_row(top3_buyer_value=70, top3_seller_value=100))
        assert seller_score < base_score

    def test_missing_top3_no_crash(self):
        score = score_single_window(_base_row(top3_buyer_value=None, top3_seller_value=None))
        assert score is not None and 0 <= score <= 100

    def test_zero_seller_no_crash(self):
        score = score_single_window(_base_row(top3_buyer_value=100, top3_seller_value=0))
        assert score is not None and 0 <= score <= 100


class TestCloseVsTopBuyerAvg:
    """Property 17: Close vs Top Buyer Avg Penalty — exceeding threshold decreases score."""

    def test_high_close_vs_buyer_decreases_score(self):
        base_score = score_single_window(_base_row(close_vs_top_buyer_avg=0.0))
        high_score = score_single_window(_base_row(close_vs_top_buyer_avg=0.12))
        assert high_score < base_score

    def test_moderate_close_vs_buyer_decreases_score(self):
        base_score = score_single_window(_base_row(close_vs_top_buyer_avg=0.0))
        moderate_score = score_single_window(_base_row(close_vs_top_buyer_avg=0.07))
        assert moderate_score < base_score

    def test_low_close_vs_buyer_no_penalty(self):
        base_score = score_single_window(_base_row(close_vs_top_buyer_avg=0.0))
        low_score = score_single_window(_base_row(close_vs_top_buyer_avg=0.03))
        assert low_score == base_score

    def test_missing_close_vs_buyer_no_crash(self):
        score = score_single_window(_base_row(close_vs_top_buyer_avg=None))
        assert score is not None and 0 <= score <= 100


class TestBandarmologyScoreBoundedRange:
    """Property 14: Bandarmology Score always in [0, 100]."""

    @given(
        buyer_hhi=st.one_of(st.none(), st.floats(min_value=0, max_value=1.0)),
        top3_buyer=st.one_of(st.none(), st.floats(min_value=0, max_value=1e12)),
        top3_seller=st.one_of(st.none(), st.floats(min_value=0, max_value=1e12)),
        close_vs_buyer=st.one_of(st.none(), st.floats(min_value=-1.0, max_value=2.0)),
    )
    @settings(max_examples=200)
    def test_score_always_bounded(self, buyer_hhi, top3_buyer, top3_seller, close_vs_buyer):
        assume(buyer_hhi is None or not pd.isna(buyer_hhi))
        assume(top3_buyer is None or not pd.isna(top3_buyer))
        assume(top3_seller is None or not pd.isna(top3_seller))
        assume(close_vs_buyer is None or not pd.isna(close_vs_buyer))
        row = _base_row(
            buyer_hhi=buyer_hhi,
            top3_buyer_value=top3_buyer,
            top3_seller_value=top3_seller,
            close_vs_top_buyer_avg=close_vs_buyer,
        )
        score = score_single_window(row)
        assert score is not None
        assert 0 <= score <= 100


class TestGracefulDegradation:
    """Property 18: Missing fields produce valid [0,100] score without exception."""

    def test_all_new_fields_none(self):
        row = _base_row(buyer_hhi=None, top3_buyer_value=None, top3_seller_value=None, close_vs_top_buyer_avg=None)
        score = score_single_window(row)
        assert score is not None and 0 <= score <= 100

    def test_all_new_fields_nan(self):
        row = _base_row(buyer_hhi=float("nan"), top3_buyer_value=float("nan"), top3_seller_value=float("nan"), close_vs_top_buyer_avg=float("nan"))
        score = score_single_window(row)
        assert score is not None and 0 <= score <= 100

    def test_backward_compatibility_without_new_fields(self):
        """Row without any new fields still produces a valid score (no regression)."""
        row = {
            "broker_activity_available": True,
            "broker_accdist": "Acc",
            "avg_accdist": "Acc",
            "avg_percent": 10.0,
            "avg_amount": 50_000_000,
            "relative_activity_bucket": "ACTIVE",
            "close_location": 0.7,
            "momentum_score": 65,
            "technical_context": "BREAKOUT_NEAR",
            "detector_average_price": 1000,
            "close": 1050,
        }
        score = score_single_window(row)
        assert score is not None and 0 <= score <= 100


class TestCalculateBrokerFeaturesDominance:
    """Test that calculate_broker_features outputs top3_buyer_dominance."""

    def test_dominance_ratio_computed(self):
        df = pd.DataFrame([
            {"ticker": "BBRI", "side": "BUY", "net_value": 1_000_000_000, "broker_code": "YP", "avg_price": 5000},
            {"ticker": "BBRI", "side": "BUY", "net_value": 500_000_000, "broker_code": "DB", "avg_price": 5100},
            {"ticker": "BBRI", "side": "BUY", "net_value": 300_000_000, "broker_code": "GX", "avg_price": 4900},
            {"ticker": "BBRI", "side": "SELL", "net_value": -200_000_000, "broker_code": "KS", "avg_price": 5200},
            {"ticker": "BBRI", "side": "SELL", "net_value": -100_000_000, "broker_code": "MS", "avg_price": 5300},
        ])
        features = calculate_broker_features(df)
        assert not features.empty
        row = features.iloc[0]
        assert "top3_buyer_dominance" in row.index
        assert row["top3_buyer_dominance"] is not None
        # top3_buyer_value = 1B + 500M + 300M = 1.8B
        # top3_seller_value = 200M + 100M = 300M (abs values)
        assert row["top3_buyer_dominance"] == 1_800_000_000 / 300_000_000
