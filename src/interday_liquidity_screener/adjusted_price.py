"""AdjustedPriceHandler — manages dual-price columns for corporate action safety.

When a stock has had a corporate action (stock split, dividend, etc.), the raw
close price and the adjusted close price diverge historically. This module:
- Uses adjusted_close for indicator calculations (MA, RSI, etc.) to avoid false signals
- Preserves raw close (close_raw) for IDX tick-size validation in trade plans
- Detects whether a corporate action exists in the data period
"""

from __future__ import annotations

import pandas as pd


class AdjustedPriceHandler:
    """Manage dual-price: adjusted for indicators, raw for tick validation."""

    @staticmethod
    def prepare_dual_price(df: pd.DataFrame) -> pd.DataFrame:
        """Prepare DataFrame with dual-price columns.

        Input columns expected:
        - 'close' (raw close price)
        - 'adjusted_close' (optional; if missing, fallback to close)

        Output adds/modifies:
        - 'close_raw': Always the original raw close price
        - 'close': Set to adjusted_close if corporate action detected, else unchanged
        - 'adjusted_close_available': Boolean flag

        Args:
            df: OHLCV DataFrame with at least 'close' column.

        Returns:
            DataFrame with dual-price columns. Original DataFrame is not modified.
        """
        if df is None or df.empty:
            return df if df is not None else pd.DataFrame()

        result = df.copy()

        # Preserve every tradable field explicitly. ``close_raw`` remains as a
        # public compatibility alias used by older callers.
        for column in ("open", "high", "low", "close", "volume"):
            if column in result.columns:
                result[f"raw_{column}"] = result[column].copy()
        result["close_raw"] = result["raw_close"].copy()

        has_adjusted = "adjusted_close" in result.columns
        result["adjusted_close_available"] = has_adjusted

        if has_adjusted:
            # Check if adjusted_close is actually different from close (corporate action exists)
            adj = result["adjusted_close"]
            raw = result["raw_close"]

            # Fill NaN in adjusted_close with raw close (graceful fallback)
            adj_filled = adj.fillna(raw)

            result["adjustment_factor"] = (adj_filled / raw).where(raw > 0, 1.0).fillna(1.0)
            for column in ("open", "high", "low", "close"):
                raw_column = f"raw_{column}"
                if raw_column in result.columns:
                    adjusted_column = f"adjusted_{column}"
                    if adjusted_column not in result.columns:
                        result[adjusted_column] = result[raw_column] * result["adjustment_factor"]
            if "raw_volume" in result.columns:
                valid_factor = result["adjustment_factor"].where(result["adjustment_factor"] > 0, 1.0)
                if "adjusted_volume" not in result.columns:
                    result["adjusted_volume"] = result["raw_volume"] / valid_factor

            if AdjustedPriceHandler.has_corporate_action(result):
                # Historical indicators use adjusted OHLCV; execution callers
                # retain the raw_* fields for fills, ticks and cash accounting.
                for column in ("open", "high", "low", "close", "volume"):
                    adjusted_column = f"adjusted_{column}"
                    if adjusted_column in result.columns:
                        result[column] = result[adjusted_column]
            # else: keep close as-is (no corporate action, adjusted == raw)
        else:
            result["adjustment_factor"] = 1.0
            for column in ("open", "high", "low", "close", "volume"):
                raw_column = f"raw_{column}"
                if raw_column in result.columns:
                    result[f"adjusted_{column}"] = result[raw_column]

        return result

    @staticmethod
    def has_corporate_action(df: pd.DataFrame) -> bool:
        """Detect if there's a corporate action (split/dividend) in the data period.

        Detection: If adjusted_close differs from close by more than a small tolerance
        on at least one bar, a corporate action likely exists.

        Args:
            df: DataFrame with 'close' and 'adjusted_close' columns.

        Returns:
            True if corporate action detected, False otherwise.
        """
        if df is None or df.empty:
            return False

        if "adjusted_close" not in df.columns or "close" not in df.columns:
            return False

        close = pd.to_numeric(df["close"], errors="coerce")
        adjusted = pd.to_numeric(df["adjusted_close"], errors="coerce")

        # Drop rows where either is NaN
        valid = close.notna() & adjusted.notna() & (close > 0)
        if not valid.any():
            return False

        # Check relative difference
        ratio = (adjusted[valid] / close[valid]).dropna()
        if ratio.empty:
            return False

        # If any ratio deviates > 1% from 1.0, corporate action exists
        return bool(((ratio - 1.0).abs() > 0.01).any())

    @staticmethod
    def restore_raw_close(df: pd.DataFrame) -> pd.DataFrame:
        """Restore raw close from close_raw column (for tick validation).

        Use this before trade plan price validation to ensure tick-size
        checks use actual market prices.

        Args:
            df: DataFrame that went through prepare_dual_price.

        Returns:
            DataFrame with 'close' restored to raw values.
        """
        if df is None or df.empty:
            return df if df is not None else pd.DataFrame()

        result = df.copy()
        for column in ("open", "high", "low", "close", "volume"):
            raw_column = f"raw_{column}"
            if raw_column in result.columns:
                result[column] = result[raw_column]
        if "raw_close" not in result.columns and "close_raw" in result.columns:
            result["close"] = result["close_raw"]
        return result


__all__ = ["AdjustedPriceHandler"]
