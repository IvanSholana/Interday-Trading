"""Tests for P1 Task 10 — AdjustedPriceHandler."""

from __future__ import annotations

import pandas as pd
import pytest

from interday_liquidity_screener.adjusted_price import AdjustedPriceHandler


def _make_df(close: list[float], adjusted_close: list[float] | None = None) -> pd.DataFrame:
    """Create test OHLCV DataFrame."""
    dates = pd.date_range("2025-01-01", periods=len(close), freq="B")
    data = {
        "open": close,
        "high": [c * 1.02 for c in close],
        "low": [c * 0.98 for c in close],
        "close": close,
        "volume": [1_000_000] * len(close),
    }
    if adjusted_close is not None:
        data["adjusted_close"] = adjusted_close
    return pd.DataFrame(data, index=dates)


class TestHasCorporateAction:
    """Property 21-23 related: detect corporate action from price data."""

    def test_no_adjusted_column_returns_false(self):
        df = _make_df([100, 101, 102])
        assert AdjustedPriceHandler.has_corporate_action(df) is False

    def test_same_prices_returns_false(self):
        df = _make_df([100, 101, 102], [100, 101, 102])
        assert AdjustedPriceHandler.has_corporate_action(df) is False

    def test_split_detected(self):
        # Stock split 1:2 — adjusted is half of raw before split date
        close = [1000, 1000, 500, 510, 520]
        adjusted = [500, 500, 500, 510, 520]  # adjusted accounts for split
        df = _make_df(close, adjusted)
        assert AdjustedPriceHandler.has_corporate_action(df) is True

    def test_small_rounding_difference_not_detected(self):
        # Tiny differences due to rounding — should NOT trigger
        close = [100.0, 101.0, 102.0]
        adjusted = [100.001, 101.001, 102.001]  # < 1% difference
        df = _make_df(close, adjusted)
        assert AdjustedPriceHandler.has_corporate_action(df) is False

    def test_empty_df_returns_false(self):
        assert AdjustedPriceHandler.has_corporate_action(pd.DataFrame()) is False

    def test_none_df_returns_false(self):
        assert AdjustedPriceHandler.has_corporate_action(None) is False


class TestPrepareDualPrice:
    """Test dual-price preparation logic."""

    def test_preserves_raw_close(self):
        close = [1000, 1000, 500, 510, 520]
        adjusted = [500, 500, 500, 510, 520]
        df = _make_df(close, adjusted)
        result = AdjustedPriceHandler.prepare_dual_price(df)

        # close_raw should always be the original raw close
        assert list(result["close_raw"]) == close

    def test_uses_adjusted_for_close_when_corp_action(self):
        close = [1000, 1000, 500, 510, 520]
        adjusted = [500, 500, 500, 510, 520]
        df = _make_df(close, adjusted)
        result = AdjustedPriceHandler.prepare_dual_price(df)

        # close should now be the adjusted values (for indicator calc)
        assert list(result["close"]) == adjusted

    def test_no_corp_action_keeps_close_unchanged(self):
        close = [100, 101, 102, 103, 104]
        adjusted = [100, 101, 102, 103, 104]
        df = _make_df(close, adjusted)
        result = AdjustedPriceHandler.prepare_dual_price(df)

        # No corporate action → close unchanged
        assert list(result["close"]) == close
        assert list(result["close_raw"]) == close

    def test_missing_adjusted_close_column_fallback(self):
        close = [100, 101, 102]
        df = _make_df(close)  # no adjusted_close column
        result = AdjustedPriceHandler.prepare_dual_price(df)

        # close unchanged, close_raw added
        assert list(result["close"]) == close
        assert list(result["close_raw"]) == close
        assert result["adjusted_close_available"].all() == False

    def test_does_not_modify_original_df(self):
        close = [1000, 1000, 500]
        adjusted = [500, 500, 500]
        df = _make_df(close, adjusted)
        original_close = list(df["close"])
        AdjustedPriceHandler.prepare_dual_price(df)
        assert list(df["close"]) == original_close

    def test_empty_df_returns_empty(self):
        result = AdjustedPriceHandler.prepare_dual_price(pd.DataFrame())
        assert result.empty

    def test_none_returns_empty(self):
        result = AdjustedPriceHandler.prepare_dual_price(None)
        assert result.empty


class TestRestoreRawClose:
    """Test restoring raw close for tick validation."""

    def test_restore_after_prepare(self):
        close = [1000, 1000, 500, 510, 520]
        adjusted = [500, 500, 500, 510, 520]
        df = _make_df(close, adjusted)
        prepared = AdjustedPriceHandler.prepare_dual_price(df)

        # After prepare, close == adjusted
        assert list(prepared["close"]) == adjusted

        # After restore, close == raw
        restored = AdjustedPriceHandler.restore_raw_close(prepared)
        assert list(restored["close"]) == close

    def test_restore_without_close_raw_noop(self):
        df = _make_df([100, 101, 102])
        result = AdjustedPriceHandler.restore_raw_close(df)
        assert list(result["close"]) == [100, 101, 102]


class TestBackwardCompatibility:
    """Property 23: No-Corporate-Action Backward Compatibility."""

    def test_identical_output_when_no_corp_action(self):
        close = [100, 101, 102, 103, 104]
        adjusted = [100, 101, 102, 103, 104]  # same as raw
        df = _make_df(close, adjusted)
        result = AdjustedPriceHandler.prepare_dual_price(df)

        # Close used for indicators should be unchanged
        assert list(result["close"]) == close

        # Computing MA on prepared close should be same as on original
        ma = result["close"].rolling(3).mean()
        ma_original = df["close"].rolling(3).mean()
        pd.testing.assert_series_equal(ma, ma_original)
