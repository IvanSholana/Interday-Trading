"""
P6 Adaptive Threshold — Day-of-week and market regime adaptive thresholds.

Static thresholds like min_volume_ratio=1.0 fail on low-activity days (Fridays,
post-holiday). This module computes historical percentile-based thresholds per
day-of-week so the pipeline adjusts automatically.

Usage:
    from enhancements.adaptive_threshold import AdaptiveThreshold
    at = AdaptiveThreshold(enabled=True)
    adjusted_config = at.adjust_config(base_config, ohlcv_history, run_date)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

import pandas as pd


@dataclass
class AdaptiveThreshold:
    """Adjusts screener thresholds based on day-of-week historical distribution."""
    enabled: bool = True
    # Percentile to use for threshold (30th = lenient, 50th = median, 70th = strict)
    volume_ratio_percentile: float = 30.0
    value_ratio_percentile: float = 30.0
    # Minimum floor (never go below this even on quietest days)
    min_volume_ratio_floor: float = 0.3
    min_value_ratio_floor: float = 0.3
    # Lookback for computing day-of-week stats
    lookback_bars: int = 60

    def compute_day_of_week_thresholds(
        self,
        volume_ratios: pd.Series,
        dates: pd.DatetimeIndex | pd.Series,
    ) -> dict[int, float]:
        """Compute volume_ratio threshold per day-of-week (0=Mon, 4=Fri).

        Returns dict mapping weekday number to adaptive threshold.
        """
        if not self.enabled or volume_ratios.empty:
            return {i: 1.0 for i in range(5)}

        df = pd.DataFrame({"volume_ratio": volume_ratios.values, "weekday": dates.weekday})
        thresholds = {}
        for day in range(5):
            day_data = df[df["weekday"] == day]["volume_ratio"].dropna()
            if len(day_data) >= 4:
                pct = day_data.quantile(self.volume_ratio_percentile / 100)
                thresholds[day] = max(float(pct), self.min_volume_ratio_floor)
            else:
                thresholds[day] = self.min_volume_ratio_floor
        return thresholds

    def get_adjusted_min_volume_ratio(
        self,
        history_df: pd.DataFrame,
        run_date: date | None = None,
        default: float = 1.0,
    ) -> float:
        """Return an adjusted min_volume_ratio for the given run_date's weekday.

        Args:
            history_df: DataFrame with DatetimeIndex containing 'volume_ratio' column.
            run_date: The date of the pipeline run. Defaults to today.
            default: Fallback if disabled or insufficient data.
        """
        if not self.enabled:
            return default
        if run_date is None:
            run_date = date.today()

        if "volume_ratio" not in history_df.columns:
            return default

        recent = history_df.tail(self.lookback_bars)
        if len(recent) < 20:
            return default

        thresholds = self.compute_day_of_week_thresholds(
            recent["volume_ratio"],
            recent.index,
        )
        weekday = run_date.weekday()
        return thresholds.get(weekday, default)

    def get_adjusted_min_value(
        self,
        history_df: pd.DataFrame,
        run_date: date | None = None,
        default: float = 5_000_000_000,
    ) -> float:
        """Return an adjusted min_value threshold based on weekday patterns."""
        if not self.enabled:
            return default
        if run_date is None:
            run_date = date.today()

        if "value_est" not in history_df.columns:
            return default

        recent = history_df.tail(self.lookback_bars)
        if len(recent) < 20:
            return default

        df = pd.DataFrame({"value": recent["value_est"].values, "weekday": recent.index.weekday})
        day_data = df[df["weekday"] == run_date.weekday()]["value"].dropna()
        if len(day_data) >= 4:
            return max(float(day_data.quantile(0.25)), default * 0.3)
        return default
