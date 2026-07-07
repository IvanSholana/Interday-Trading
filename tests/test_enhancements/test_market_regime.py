"""Tests for P1 Task 8 — MarketRegimeFilter."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from interday_liquidity_screener.enhancements.market_regime import (
    MarketRegimeConfig,
    MarketRegimeFilter,
    MarketRegimeResult,
    REGIME_RISK_ON,
    REGIME_RISK_OFF,
    REGIME_AMBIGUOUS,
    evaluate_market_regime,
)


def _make_ohlcv(closes: list[float], start_date: str = "2025-01-01") -> pd.DataFrame:
    """Create a simple OHLCV DataFrame from a list of close prices."""
    dates = pd.date_range(start=start_date, periods=len(closes), freq="B")
    df = pd.DataFrame(
        {
            "open": closes,
            "high": [c * 1.01 for c in closes],
            "low": [c * 0.99 for c in closes],
            "close": closes,
            "volume": [1_000_000] * len(closes),
        },
        index=dates,
    )
    return df


class TestMarketRegimeFilterIHSG:
    """Test IHSG trend evaluation."""

    def test_ihsg_above_ma_is_risk_on(self):
        # 60 days trending up — close > MA50
        closes = list(range(100, 160))  # steadily increasing
        ihsg = _make_ohlcv(closes)
        config = MarketRegimeConfig(ihsg_ma_period=50)
        result = MarketRegimeFilter(config).evaluate(ihsg)
        assert result.ihsg_above_ma is True
        assert result.regime in {REGIME_RISK_ON, REGIME_AMBIGUOUS}

    def test_ihsg_below_ma_is_risk_off(self):
        # 60 days trending down — close < MA50
        closes = list(range(200, 140, -1))  # steadily decreasing
        ihsg = _make_ohlcv(closes)
        config = MarketRegimeConfig(ihsg_ma_period=50)
        result = MarketRegimeFilter(config).evaluate(ihsg)
        assert result.ihsg_above_ma is False
        assert result.regime in {REGIME_RISK_OFF, REGIME_AMBIGUOUS}

    def test_insufficient_ihsg_data_returns_ambiguous(self):
        closes = [100.0] * 10  # only 10 bars, need 50
        ihsg = _make_ohlcv(closes)
        config = MarketRegimeConfig(ihsg_ma_period=50)
        result = MarketRegimeFilter(config).evaluate(ihsg)
        assert result.ihsg_above_ma is None
        assert result.regime == REGIME_AMBIGUOUS

    def test_none_ihsg_data_returns_ambiguous(self):
        result = MarketRegimeFilter().evaluate(None)
        assert result.regime == REGIME_AMBIGUOUS
        assert result.warning is not None

    def test_decision_date_slices_data(self):
        # First 55 bars up, then 5 bars crash
        closes = list(range(100, 155)) + [80, 75, 70, 65, 60]
        ihsg = _make_ohlcv(closes)
        dates = ihsg.index

        # Before crash: IHSG above MA
        config = MarketRegimeConfig(ihsg_ma_period=50)
        result_before = MarketRegimeFilter(config).evaluate(ihsg, decision_date=dates[54])
        assert result_before.ihsg_above_ma is True

        # After crash: IHSG below MA
        result_after = MarketRegimeFilter(config).evaluate(ihsg, decision_date=dates[-1])
        assert result_after.ihsg_above_ma is False


class TestMarketRegimeFilterBreadth:
    """Test breadth calculation."""

    def test_high_breadth_contributes_to_risk_on(self):
        # 5 stocks, all trending up — all above MA50
        universe = {}
        for i in range(5):
            universe[f"STOCK{i}"] = _make_ohlcv(list(range(100 + i, 160 + i)))
        config = MarketRegimeConfig(ihsg_ma_period=50, breadth_threshold=0.50)
        flt = MarketRegimeFilter(config)
        result = flt.evaluate(None, universe_data=universe)
        assert result.breadth_pct is not None
        assert result.breadth_pct >= 0.5
        assert result.regime == REGIME_RISK_ON

    def test_low_breadth_contributes_to_risk_off(self):
        # 5 stocks, all trending down
        universe = {}
        for i in range(5):
            universe[f"STOCK{i}"] = _make_ohlcv(list(range(200, 140, -1)))
        config = MarketRegimeConfig(ihsg_ma_period=50, breadth_threshold=0.50)
        flt = MarketRegimeFilter(config)
        result = flt.evaluate(None, universe_data=universe)
        assert result.breadth_pct is not None
        assert result.breadth_pct < 0.5
        assert result.regime == REGIME_RISK_OFF

    def test_empty_universe_returns_none_breadth(self):
        result = MarketRegimeFilter().evaluate(None, universe_data={})
        assert result.breadth_pct is None
        assert result.regime == REGIME_AMBIGUOUS


class TestMarketRegimeCombined:
    """Test combined IHSG + breadth regime classification."""

    def test_both_positive_is_risk_on(self):
        ihsg = _make_ohlcv(list(range(100, 160)))
        universe = {f"S{i}": _make_ohlcv(list(range(100, 160))) for i in range(5)}
        config = MarketRegimeConfig(ihsg_ma_period=50, breadth_threshold=0.50)
        result = MarketRegimeFilter(config).evaluate(ihsg, universe, decision_date=ihsg.index[-1])
        assert result.regime == REGIME_RISK_ON

    def test_both_negative_is_risk_off(self):
        ihsg = _make_ohlcv(list(range(200, 140, -1)))
        universe = {f"S{i}": _make_ohlcv(list(range(200, 140, -1))) for i in range(5)}
        config = MarketRegimeConfig(ihsg_ma_period=50, breadth_threshold=0.50)
        result = MarketRegimeFilter(config).evaluate(ihsg, universe, decision_date=ihsg.index[-1])
        assert result.regime == REGIME_RISK_OFF

    def test_mixed_signals_is_ambiguous(self):
        # IHSG up but all stocks down
        ihsg = _make_ohlcv(list(range(100, 160)))
        universe = {f"S{i}": _make_ohlcv(list(range(200, 140, -1))) for i in range(5)}
        config = MarketRegimeConfig(ihsg_ma_period=50, breadth_threshold=0.50)
        result = MarketRegimeFilter(config).evaluate(ihsg, universe, decision_date=ihsg.index[-1])
        assert result.regime == REGIME_AMBIGUOUS


class TestMarketRegimeDisabled:
    """Test that disabled filter always returns RISK_ON."""

    def test_disabled_returns_risk_on(self):
        config = MarketRegimeConfig(enabled=False)
        result = MarketRegimeFilter(config).evaluate(None)
        assert result.regime == REGIME_RISK_ON
        assert result.warning == "market_regime_filter_disabled"


class TestConvenienceFunction:
    """Test the evaluate_market_regime shortcut."""

    def test_convenience_function_works(self):
        ihsg = _make_ohlcv(list(range(100, 160)))
        result = evaluate_market_regime(ihsg_data=ihsg)
        assert result.regime in {REGIME_RISK_ON, REGIME_RISK_OFF, REGIME_AMBIGUOUS}
