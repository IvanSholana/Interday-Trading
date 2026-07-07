"""Tests for P2-P3 enhancement modules (Tasks 5, 12-17)."""

from __future__ import annotations

import math
from datetime import date, timedelta

import pandas as pd
import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from interday_liquidity_screener.backtest.metrics import EdgeMetrics, EdgeMetricsResult
from interday_liquidity_screener.backtest.report import ReportWriter
from interday_liquidity_screener.backtest.runner import TradeLedger
from interday_liquidity_screener.backtest.simulator import TradeSimulation
from interday_liquidity_screener.enhancements.adaptive_tp import AdaptiveTakeProfit, AdaptiveTPConfig
from interday_liquidity_screener.enhancements.liquidity_sizer import LiquidityPositionSizer, LiquiditySizerConfig
from interday_liquidity_screener.enhancements.broker_window import BrokerWindowAligner, BrokerWindowConfig
from interday_liquidity_screener.enhancements.blackout import BlackoutFilter, BlackoutConfig
from interday_liquidity_screener.trade_plan import get_idx_tick_size


def _make_trade(return_net=0.02, exit_event="TP1_HIT", mfe=0.03, mae=-0.01, holding_days=3, **kwargs):
    defaults = dict(
        ticker="BBRI",
        entry_date=pd.Timestamp("2025-06-01"),
        entry_price=5000.0,
        raw_entry_price=4995.0,
        stop_loss=4800.0,
        take_profit_1=5200.0,
        take_profit_2=5400.0,
        exit_date=pd.Timestamp("2025-06-04"),
        exit_price=5200.0,
        exit_event=exit_event,
        return_gross=0.024,
        return_net=return_net,
        r_multiple=1.0,
        mfe=mfe,
        mae=mae,
        holding_days=holding_days,
        entry_setup="BREAKOUT_CANDIDATE",
        technical_context="BREAKOUT_NEAR",
        bandarmology_signal="STRONG_ACCUMULATION",
    )
    defaults.update(kwargs)
    return TradeSimulation(**defaults)


# ===== Task 5: EdgeMetrics =====

class TestEdgeMetrics:
    def test_empty_trades_returns_zero(self):
        result = EdgeMetrics().compute([])
        assert result.total_trades == 0
        assert result.is_statistically_significant is False

    def test_single_win(self):
        trades = [_make_trade(return_net=0.03, exit_event="TP1_HIT")]
        result = EdgeMetrics(min_sample_size=1).compute(trades)
        assert result.total_trades == 1
        assert result.win_rate == 1.0
        assert result.avg_win == 0.03
        assert result.tp_hit_ratio == 1.0

    def test_mixed_wins_losses(self):
        trades = [
            _make_trade(return_net=0.04, exit_event="TP1_HIT"),
            _make_trade(return_net=0.03, exit_event="TP1_HIT"),
            _make_trade(return_net=-0.02, exit_event="SL_HIT"),
        ]
        result = EdgeMetrics(min_sample_size=2).compute(trades)
        assert result.total_trades == 3
        assert abs(result.win_rate - 2 / 3) < 1e-9
        assert abs(result.avg_win - 0.035) < 1e-9
        assert abs(result.avg_loss - (-0.02)) < 1e-9
        assert result.is_statistically_significant is True

    def test_expectancy_formula(self):
        """Property 10: expectancy == (win_rate * avg_win) - (loss_rate * avg_loss)"""
        trades = [
            _make_trade(return_net=0.05),
            _make_trade(return_net=0.03),
            _make_trade(return_net=-0.02, exit_event="SL_HIT"),
            _make_trade(return_net=-0.01, exit_event="TIME_STOP"),
        ]
        result = EdgeMetrics(min_sample_size=2).compute(trades)
        expected = (result.win_rate * result.avg_win) - ((1 - result.win_rate) * abs(result.avg_loss))
        assert abs(result.expectancy - expected) < 1e-9

    def test_statistical_significance_flag(self):
        """Property 13: segments < min_sample_size → not significant"""
        trades = [_make_trade() for _ in range(5)]
        result = EdgeMetrics(min_sample_size=30).compute(trades)
        assert result.is_statistically_significant is False
        result2 = EdgeMetrics(min_sample_size=5).compute(trades)
        assert result2.is_statistically_significant is True

    def test_segmented_partition_complete(self):
        """Property 12: sum of trades across segments == total"""
        trades = [
            _make_trade(entry_setup="BREAKOUT_CANDIDATE"),
            _make_trade(entry_setup="BREAKOUT_CANDIDATE"),
            _make_trade(entry_setup="REBOUND_CANDIDATE"),
        ]
        metrics = EdgeMetrics(min_sample_size=1)
        segmented = metrics.compute_segmented(trades, "entry_setup")
        total = sum(r.total_trades for r in segmented.values())
        assert total == 3

    def test_mfe_median(self):
        """Property 11: median matches pandas quantile"""
        trades = [_make_trade(mfe=v) for v in [0.01, 0.02, 0.03, 0.04, 0.05]]
        result = EdgeMetrics(min_sample_size=1).compute(trades)
        expected_median = pd.Series([0.01, 0.02, 0.03, 0.04, 0.05]).quantile(0.5)
        assert abs(result.mfe_median - expected_median) < 1e-9


# ===== Task 5.2: ReportWriter =====

class TestReportWriter:
    def test_write_full_report(self, tmp_path):
        ledger = TradeLedger(trades=[_make_trade(), _make_trade(return_net=-0.01, exit_event="SL_HIT")])
        writer = ReportWriter(tmp_path)
        metrics = EdgeMetrics(min_sample_size=1)
        paths = writer.write_full_report(ledger, metrics)
        assert paths["ledger"].exists()
        assert paths["aggregate"].exists()
        assert paths["segmented_entry_setup"].exists()


# ===== Task 12: Adaptive Take-Profit =====

class TestAdaptiveTakeProfit:
    def test_basic_calculation(self):
        atp = AdaptiveTakeProfit(AdaptiveTPConfig())
        tp1, tp2 = atp.calculate(entry_price=1000, atr14=30)
        assert tp1 > 1000
        assert tp2 > tp1

    def test_tp_ordering_invariant(self):
        """Property 25: entry < TP1 < TP2"""
        atp = AdaptiveTakeProfit()
        tp1, tp2 = atp.calculate(entry_price=500, atr14=15)
        assert 500 < tp1 < tp2

    def test_minimum_distance(self):
        """Property 24: TP1 >= entry + 0.5*ATR, TP2 >= entry + 1.0*ATR"""
        atp = AdaptiveTakeProfit()
        entry, atr = 1000.0, 50.0
        tp1, tp2 = atp.calculate(entry_price=entry, atr14=atr)
        # After rounding, should still be at least floor distance
        assert tp1 >= entry + 0.5 * atr - get_idx_tick_size(entry)
        assert tp2 >= entry + 1.0 * atr - get_idx_tick_size(entry)

    def test_tick_validity(self):
        """Property 26: TP1 and TP2 are valid IDX tick multiples"""
        atp = AdaptiveTakeProfit()
        tp1, tp2 = atp.calculate(entry_price=3000, atr14=100)
        tick1 = get_idx_tick_size(tp1)
        tick2 = get_idx_tick_size(tp2)
        assert math.isclose(tp1 % tick1, 0, abs_tol=1e-9)
        assert math.isclose(tp2 % tick2, 0, abs_tol=1e-9)

    def test_clamping(self):
        """Property 27: results within [min_tp_pct, max_tp_pct]"""
        cfg = AdaptiveTPConfig(max_tp_pct=0.12, min_tp1_pct=0.02)
        atp = AdaptiveTakeProfit(cfg)
        # Very large ATR → should be clamped to max
        tp1, tp2 = atp.calculate(entry_price=1000, atr14=500)
        assert tp1 <= 1000 * (1 + cfg.max_tp_pct) + get_idx_tick_size(1000)
        assert tp2 <= 1000 * (1 + cfg.max_tp_pct) + get_idx_tick_size(1000)

    def test_fixed_mode_fallback(self):
        atp = AdaptiveTakeProfit(AdaptiveTPConfig(mode="fixed"))
        tp1, tp2 = atp.calculate(entry_price=1000, atr14=50)
        assert tp1 > 1000
        assert tp2 > tp1

    def test_zero_atr_uses_fixed(self):
        atp = AdaptiveTakeProfit()
        tp1, tp2 = atp.calculate(entry_price=1000, atr14=0)
        assert tp1 > 1000
        assert tp2 > tp1

    def test_nan_atr_uses_fixed(self):
        atp = AdaptiveTakeProfit()
        tp1, tp2 = atp.calculate(entry_price=1000, atr14=float("nan"))
        assert tp1 > 1000
        assert tp2 > tp1


# ===== Task 13: Liquidity Position Sizer =====

class TestLiquidityPositionSizer:
    def test_liquidity_cap(self):
        """Property 28: final position <= max_pct * avg_value_20d"""
        sizer = LiquidityPositionSizer(LiquiditySizerConfig(max_pct_of_avg_value_20d=0.10))
        final, constraint = sizer.apply_limit(
            risk_based_value=2_000_000,
            capital_based_value=3_000_000,
            avg_value_20d=10_000_000,
        )
        assert final <= 0.10 * 10_000_000

    def test_minimum_of_three(self):
        """Property 29: final == min(risk, capital, liquidity)"""
        sizer = LiquidityPositionSizer(LiquiditySizerConfig(max_pct_of_avg_value_20d=0.10))
        # Risk is smallest
        final, constraint = sizer.apply_limit(500_000, 2_000_000, 50_000_000)
        assert final == 500_000
        assert constraint == "RISK"

        # Capital is smallest
        final, constraint = sizer.apply_limit(2_000_000, 400_000, 50_000_000)
        assert final == 400_000
        assert constraint == "CAPITAL"

        # Liquidity is smallest
        final, constraint = sizer.apply_limit(2_000_000, 3_000_000, 5_000_000)
        assert final == 500_000  # 0.10 * 5M
        assert constraint == "LIQUIDITY"


# ===== Task 14: Broker Window Alignment =====

class TestBrokerWindowAligner:
    def test_alignment_uses_stage2_date(self):
        """Property 30: to_date == stage2 last_date when available"""
        aligner = BrokerWindowAligner(BrokerWindowConfig(window_days=20))
        result = aligner.align_window(
            stage2_last_dates={"BBRI": "2025-06-15", "TLKM": "2025-06-14"},
            default_end_date="2025-06-10",
        )
        assert result["BBRI"][1] == "2025-06-15"
        assert result["TLKM"][1] == "2025-06-14"

    def test_fallback_to_default(self):
        aligner = BrokerWindowAligner(BrokerWindowConfig(window_days=20))
        result = aligner.align_window(
            stage2_last_dates={"BBRI": ""},
            default_end_date="2025-06-10",
        )
        assert result["BBRI"][1] == "2025-06-10"

    def test_window_days_correct(self):
        aligner = BrokerWindowAligner(BrokerWindowConfig(window_days=10))
        result = aligner.align_window(
            stage2_last_dates={"BBRI": "2025-06-20"},
            default_end_date="2025-06-01",
        )
        from_date, to_date = result["BBRI"]
        assert to_date == "2025-06-20"
        assert from_date == "2025-06-10"


# ===== Task 17: Blackout Filter =====

class TestBlackoutFilter:
    def test_in_blackout_window(self):
        """Property 33: candidates within blackout window blocked"""
        flt = BlackoutFilter(BlackoutConfig(days_before=3, days_after=1))
        events = {"BBRI": [pd.Timestamp("2025-06-15")]}
        # 3 days before = June 12
        assert flt.is_in_blackout("BBRI", pd.Timestamp("2025-06-12"), events) is True
        assert flt.is_in_blackout("BBRI", pd.Timestamp("2025-06-15"), events) is True
        # 1 day after = June 16
        assert flt.is_in_blackout("BBRI", pd.Timestamp("2025-06-16"), events) is True

    def test_outside_blackout_window(self):
        flt = BlackoutFilter(BlackoutConfig(days_before=3, days_after=1))
        events = {"BBRI": [pd.Timestamp("2025-06-15")]}
        assert flt.is_in_blackout("BBRI", pd.Timestamp("2025-06-11"), events) is False
        assert flt.is_in_blackout("BBRI", pd.Timestamp("2025-06-17"), events) is False

    def test_disabled_returns_false(self):
        flt = BlackoutFilter(BlackoutConfig(enabled=False))
        events = {"BBRI": [pd.Timestamp("2025-06-15")]}
        assert flt.is_in_blackout("BBRI", pd.Timestamp("2025-06-15"), events) is False

    def test_no_events_returns_false(self):
        flt = BlackoutFilter()
        assert flt.is_in_blackout("BBRI", pd.Timestamp("2025-06-15"), {}) is False

    def test_ticker_not_in_events_returns_false(self):
        flt = BlackoutFilter()
        events = {"TLKM": [pd.Timestamp("2025-06-15")]}
        assert flt.is_in_blackout("BBRI", pd.Timestamp("2025-06-15"), events) is False
