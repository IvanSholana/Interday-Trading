"""Tests for P2 enhancement modules: AdaptiveTakeProfit, LiquidityPositionSizer, BrokerWindowAligner."""

from __future__ import annotations

import math

import pytest

from interday_liquidity_screener.enhancements.adaptive_tp import (
    AdaptiveTakeProfit,
    AdaptiveTPConfig,
)
from interday_liquidity_screener.enhancements.broker_window import (
    BrokerWindowAligner,
    BrokerWindowConfig,
)
from interday_liquidity_screener.enhancements.liquidity_sizer import (
    LiquidityPositionSizer,
    LiquiditySizerConfig,
)
from interday_liquidity_screener.trade_plan import _price_is_tick_valid


# ===========================================================================
# AdaptiveTakeProfit Tests
# ===========================================================================


class TestAdaptiveTakeProfit:
    """Tests for AdaptiveTakeProfit."""

    def test_tp_ordering_entry_less_tp1_less_tp2(self):
        """TP1 and TP2 must be ordered: entry < tp1 < tp2."""
        atp = AdaptiveTakeProfit()
        entry = 1000.0
        atr14 = 50.0
        tp1, tp2 = atp.calculate(entry, atr14)
        assert entry < tp1 < tp2

    def test_tp_ordering_with_high_resistance(self):
        """Even with a resistance level, ordering must hold."""
        atp = AdaptiveTakeProfit()
        entry = 500.0
        atr14 = 20.0
        tp1, tp2 = atp.calculate(entry, atr14, high_20d=600.0)
        assert entry < tp1 < tp2

    def test_tp_ordering_low_price_stock(self):
        """TP ordering on a low-price stock (tick=1)."""
        atp = AdaptiveTakeProfit()
        entry = 100.0
        atr14 = 5.0
        tp1, tp2 = atp.calculate(entry, atr14)
        assert entry < tp1 < tp2

    def test_tick_validity(self):
        """Both TP values must be valid IDX tick prices."""
        atp = AdaptiveTakeProfit()
        entry = 2500.0
        atr14 = 100.0
        tp1, tp2 = atp.calculate(entry, atr14)
        assert _price_is_tick_valid(tp1), f"tp1={tp1} is not tick-valid"
        assert _price_is_tick_valid(tp2), f"tp2={tp2} is not tick-valid"

    def test_tick_validity_various_price_bands(self):
        """Tick validity across different IDX price bands."""
        atp = AdaptiveTakeProfit()
        test_cases = [
            (150.0, 8.0),    # tick=1 band
            (350.0, 15.0),   # tick=2 band
            (1200.0, 60.0),  # tick=5 band
            (3000.0, 150.0), # tick=10 band
            (8000.0, 400.0), # tick=25 band
        ]
        for entry, atr14 in test_cases:
            tp1, tp2 = atp.calculate(entry, atr14)
            assert _price_is_tick_valid(tp1), f"entry={entry}, tp1={tp1} not tick-valid"
            assert _price_is_tick_valid(tp2), f"entry={entry}, tp2={tp2} not tick-valid"

    def test_clamping_max_tp_pct(self):
        """TP1 should not exceed max_tp_pct above entry (tp2 may exceed by one tick for ordering)."""
        cfg = AdaptiveTPConfig(max_tp_pct=0.12)
        atp = AdaptiveTakeProfit(config=cfg)
        entry = 1000.0
        atr14 = 500.0  # Very large ATR to trigger ceiling
        tp1, tp2 = atp.calculate(entry, atr14)
        max_allowed = entry * (1 + cfg.max_tp_pct)
        # tp1 should respect the ceiling (floor-rounded, so always <=)
        assert tp1 <= max_allowed
        # tp2 may exceed by at most one tick to guarantee tp1 < tp2 ordering
        from interday_liquidity_screener.trade_plan import get_idx_tick_size
        tick = get_idx_tick_size(tp2)
        assert tp2 <= max_allowed + tick

    def test_clamping_min_tp1_pct(self):
        """TP1 should not be below min_tp1_pct above entry (after rounding)."""
        cfg = AdaptiveTPConfig(min_tp1_pct=0.02)
        atp = AdaptiveTakeProfit(config=cfg)
        entry = 1000.0
        atr14 = 2.0  # Very small ATR, should trigger min_tp1_pct floor
        tp1, tp2 = atp.calculate(entry, atr14)
        # tp1 should be at least entry * (1 + min_tp1_pct) - tick tolerance
        min_expected = entry * (1 + cfg.min_tp1_pct)
        # Floor rounding may reduce slightly but should be close
        assert tp1 >= min_expected - 5  # tick-size tolerance

    def test_fixed_mode_fallback(self):
        """When mode is fixed, use fixed percentages."""
        cfg = AdaptiveTPConfig(mode="fixed", fixed_tp1_pct=0.05, fixed_tp2_pct=0.08)
        atp = AdaptiveTakeProfit(config=cfg)
        entry = 1000.0
        atr14 = 50.0  # Should be ignored in fixed mode
        tp1, tp2 = atp.calculate(entry, atr14)
        assert entry < tp1 < tp2
        # Check approximate percentages (floor-rounded)
        assert tp1 <= entry * 1.05 + 1
        assert tp2 <= entry * 1.08 + 1

    def test_atr_zero_fallback(self):
        """When ATR is 0, falls back to fixed mode."""
        atp = AdaptiveTakeProfit()
        entry = 1000.0
        tp1, tp2 = atp.calculate(entry, atr14=0.0)
        assert entry < tp1 < tp2
        assert _price_is_tick_valid(tp1)
        assert _price_is_tick_valid(tp2)

    def test_atr_nan_fallback(self):
        """When ATR is NaN, falls back to fixed mode."""
        atp = AdaptiveTakeProfit()
        entry = 1000.0
        tp1, tp2 = atp.calculate(entry, atr14=float("nan"))
        assert entry < tp1 < tp2
        assert _price_is_tick_valid(tp1)
        assert _price_is_tick_valid(tp2)

    def test_high_60d_used_when_high_20d_is_none(self):
        """When high_20d is None, high_60d is used for resistance."""
        atp = AdaptiveTakeProfit()
        entry = 1000.0
        atr14 = 30.0
        tp1_no_res, tp2_no_res = atp.calculate(entry, atr14)
        tp1_res, tp2_res = atp.calculate(entry, atr14, high_60d=1200.0)
        # With a high resistance, tp2 should be at least as high
        assert tp2_res >= tp2_no_res or tp2_res == tp2_no_res  # May be clamped


# ===========================================================================
# LiquidityPositionSizer Tests
# ===========================================================================


class TestLiquidityPositionSizer:
    """Tests for LiquidityPositionSizer."""

    def test_calculate_max_position_value(self):
        """Max position is avg_value_20d * max_pct."""
        sizer = LiquidityPositionSizer()
        avg_value = 10_000_000_000.0  # 10B IDR
        max_pos = sizer.calculate_max_position_value(avg_value)
        assert max_pos == pytest.approx(1_000_000_000.0)  # 10%

    def test_liquidity_cap_is_binding(self):
        """When liquidity limit is the smallest, it should be binding."""
        cfg = LiquiditySizerConfig(max_pct_of_avg_value_20d=0.05)
        sizer = LiquidityPositionSizer(config=cfg)
        avg_value = 1_000_000_000.0  # 1B IDR -> liquidity limit = 50M
        risk_based = 200_000_000.0  # 200M
        capital_based = 100_000_000.0  # 100M
        final, constraint = sizer.apply_limit(risk_based, capital_based, avg_value)
        assert final == pytest.approx(50_000_000.0)
        assert constraint == "LIQUIDITY"

    def test_risk_is_binding(self):
        """When risk-based value is the smallest, it should be binding."""
        sizer = LiquidityPositionSizer()
        avg_value = 50_000_000_000.0  # 50B -> liquidity = 5B
        risk_based = 50_000_000.0  # 50M (smallest)
        capital_based = 100_000_000.0  # 100M
        final, constraint = sizer.apply_limit(risk_based, capital_based, avg_value)
        assert final == pytest.approx(50_000_000.0)
        assert constraint == "RISK"

    def test_capital_is_binding(self):
        """When capital-based value is the smallest, it should be binding."""
        sizer = LiquidityPositionSizer()
        avg_value = 50_000_000_000.0  # 50B -> liquidity = 5B
        risk_based = 200_000_000.0  # 200M
        capital_based = 80_000_000.0  # 80M (smallest)
        final, constraint = sizer.apply_limit(risk_based, capital_based, avg_value)
        assert final == pytest.approx(80_000_000.0)
        assert constraint == "CAPITAL"

    def test_min_of_three_limits(self):
        """Final value is always the minimum of three limits."""
        sizer = LiquidityPositionSizer(LiquiditySizerConfig(max_pct_of_avg_value_20d=0.10))
        test_cases = [
            (100, 200, 5000, 100, "RISK"),      # risk smallest
            (200, 100, 5000, 100, "CAPITAL"),    # capital smallest
            (200, 300, 1000, 100, "LIQUIDITY"),  # liquidity smallest (1000*0.10=100)
        ]
        for risk, cap, avg_val, expected_val, expected_constraint in test_cases:
            final, constraint = sizer.apply_limit(risk, cap, avg_val)
            assert final == pytest.approx(expected_val)
            assert constraint == expected_constraint

    def test_custom_config(self):
        """Custom max_pct_of_avg_value_20d is respected."""
        cfg = LiquiditySizerConfig(max_pct_of_avg_value_20d=0.25)
        sizer = LiquidityPositionSizer(config=cfg)
        max_pos = sizer.calculate_max_position_value(1_000_000.0)
        assert max_pos == pytest.approx(250_000.0)


# ===========================================================================
# BrokerWindowAligner Tests
# ===========================================================================


class TestBrokerWindowAligner:
    """Tests for BrokerWindowAligner."""

    def test_alignment_uses_stage2_date(self):
        """to_date should use the stage2 last_date for each ticker."""
        aligner = BrokerWindowAligner()
        stage2_dates = {"BBRI": "2024-06-15", "TLKM": "2024-06-14"}
        result = aligner.align_window(stage2_dates, default_end_date="2024-06-10")

        assert result["BBRI"] == ("2024-05-26", "2024-06-15")
        assert result["TLKM"] == ("2024-05-25", "2024-06-14")

    def test_fallback_to_default_end_date(self, caplog):
        """When a ticker has empty last_date, uses default_end_date and logs warning."""
        aligner = BrokerWindowAligner()
        stage2_dates = {"BBRI": "2024-06-15", "TLKM": ""}
        with caplog.at_level("WARNING"):
            result = aligner.align_window(stage2_dates, default_end_date="2024-06-10")

        # TLKM should use default
        assert result["TLKM"] == ("2024-05-21", "2024-06-10")
        # BBRI should use its own date
        assert result["BBRI"] == ("2024-05-26", "2024-06-15")
        # Warning should be logged
        assert "TLKM" in caplog.text

    def test_custom_window_days(self):
        """Custom window_days config is respected."""
        cfg = BrokerWindowConfig(window_days=10)
        aligner = BrokerWindowAligner(config=cfg)
        stage2_dates = {"BBRI": "2024-06-15"}
        result = aligner.align_window(stage2_dates, default_end_date="2024-06-10")

        assert result["BBRI"] == ("2024-06-05", "2024-06-15")

    def test_empty_stage2_dates(self):
        """Empty input dict returns empty result."""
        aligner = BrokerWindowAligner()
        result = aligner.align_window({}, default_end_date="2024-06-10")
        assert result == {}

    def test_from_date_calculation_across_month_boundary(self):
        """Window calculation correctly crosses month boundaries."""
        aligner = BrokerWindowAligner(BrokerWindowConfig(window_days=20))
        stage2_dates = {"BBRI": "2024-03-05"}
        result = aligner.align_window(stage2_dates, default_end_date="2024-03-01")

        # 2024-03-05 - 20 days = 2024-02-14
        assert result["BBRI"] == ("2024-02-14", "2024-03-05")
