"""MultiBarConfirmation — confirms breakout/rebound setups across multiple bars.

Instead of relying on a single bar's classification, this module checks if
the last N bars consistently satisfy the setup criteria, reducing false signals.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


CONFIRMED = "CONFIRMED"
PENDING_CONFIRMATION = "PENDING_CONFIRMATION"
NOT_APPLICABLE = "NOT_APPLICABLE"

BREAKOUT_SETUPS = {"BREAKOUT_CANDIDATE", "BREAKOUT_NEAR"}
REBOUND_SETUPS = {"REBOUND_CANDIDATE", "REBOUND_NEAR_LOW"}


@dataclass(frozen=True)
class MultiBarConfig:
    """Configuration for multi-bar confirmation.

    Attributes:
        breakout_confirm_bars: Number of consecutive bars required for breakout confirmation.
        rebound_confirm_bars: Number of consecutive bars required for rebound confirmation.
    """

    breakout_confirm_bars: int = 2
    rebound_confirm_bars: int = 2


class MultiBarConfirmation:
    """Confirms entry setups by requiring criteria to hold across N consecutive bars.

    For BREAKOUT: close >= high_20d * 0.97 AND close_location >= 0.55
    For REBOUND: distance_from_20d_low <= 0.10 AND (close_location >= 0.55 OR return_1d > 0)
    """

    def __init__(self, config: MultiBarConfig | None = None) -> None:
        self._config = config or MultiBarConfig()

    @property
    def config(self) -> MultiBarConfig:
        return self._config

    def is_breakout_confirmed(
        self,
        features_history: pd.DataFrame,
        decision_date: pd.Timestamp | None = None,
    ) -> bool:
        """Check if last N bars meet breakout criteria.

        Criteria per bar:
        - close >= high_20d * 0.97
        - close_location >= 0.55

        Args:
            features_history: DataFrame with technical features (close, high_20d, close_location).
                              Index must be DatetimeIndex.
            decision_date: Only use data up to this date. If None, use all data.

        Returns:
            True if all N bars satisfy breakout criteria.
        """
        bars = self._get_tail_bars(features_history, decision_date, self._config.breakout_confirm_bars)
        if bars is None:
            return False

        for _, bar in bars.iterrows():
            close = _safe_float(bar.get("close"))
            high_20d = _safe_float(bar.get("high_20d"))
            close_location = _safe_float(bar.get("close_location"), 0.5)

            if close is None or high_20d is None:
                return False
            if close < high_20d * 0.97:
                return False
            if close_location < 0.55:
                return False

        return True

    def is_rebound_confirmed(
        self,
        features_history: pd.DataFrame,
        decision_date: pd.Timestamp | None = None,
    ) -> bool:
        """Check if last N bars meet rebound criteria.

        Criteria per bar:
        - distance_from_20d_low <= 0.10
        - close_location >= 0.55 OR return_1d > 0

        Args:
            features_history: DataFrame with technical features.
            decision_date: Only use data up to this date.

        Returns:
            True if all N bars satisfy rebound criteria.
        """
        bars = self._get_tail_bars(features_history, decision_date, self._config.rebound_confirm_bars)
        if bars is None:
            return False

        for _, bar in bars.iterrows():
            distance_from_low = _safe_float(bar.get("distance_from_20d_low"))
            close_location = _safe_float(bar.get("close_location"), 0.5)
            return_1d = _safe_float(bar.get("return_1d"), 0.0)

            if distance_from_low is None:
                return False
            if distance_from_low > 0.10:
                return False
            if close_location < 0.55 and (return_1d is None or return_1d <= 0):
                return False

        return True

    def get_confirmation_status(
        self,
        setup: str,
        features_history: pd.DataFrame,
        decision_date: pd.Timestamp | None = None,
    ) -> str:
        """Get confirmation status for a given setup.

        Args:
            setup: The entry setup type (e.g., BREAKOUT_CANDIDATE, REBOUND_CANDIDATE).
            features_history: DataFrame with technical features.
            decision_date: Only use data up to this date.

        Returns:
            CONFIRMED: All N bars meet criteria.
            PENDING_CONFIRMATION: Setup applies but not all bars confirm.
            NOT_APPLICABLE: Setup type doesn't require multi-bar confirmation.
        """
        if setup in BREAKOUT_SETUPS:
            if self.is_breakout_confirmed(features_history, decision_date):
                return CONFIRMED
            return PENDING_CONFIRMATION

        if setup in REBOUND_SETUPS:
            if self.is_rebound_confirmed(features_history, decision_date):
                return CONFIRMED
            return PENDING_CONFIRMATION

        return NOT_APPLICABLE

    def _get_tail_bars(
        self,
        features_history: pd.DataFrame,
        decision_date: pd.Timestamp | None,
        n_bars: int,
    ) -> pd.DataFrame | None:
        """Get the last N bars up to decision_date.

        Returns None if insufficient data.
        """
        if features_history is None or features_history.empty:
            return None

        data = features_history
        if decision_date is not None:
            data = data[data.index <= decision_date]

        if len(data) < n_bars:
            return None

        return data.tail(n_bars)


def _safe_float(value, default: float | None = None) -> float | None:
    """Safely convert to float, returning default on failure."""
    if value is None:
        return default
    try:
        if pd.isna(value):
            return default
    except (TypeError, ValueError):
        pass
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


__all__ = [
    "MultiBarConfig",
    "MultiBarConfirmation",
    "CONFIRMED",
    "PENDING_CONFIRMATION",
    "NOT_APPLICABLE",
]
