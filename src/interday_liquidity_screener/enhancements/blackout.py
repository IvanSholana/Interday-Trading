"""BlackoutFilter — filters candidates near earnings/corporate action dates."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

import pandas as pd


@dataclass(frozen=True)
class BlackoutConfig:
    enabled: bool = True
    days_before: int = 3
    days_after: int = 1


class BlackoutFilter:
    """Filter candidates near earnings/corporate action dates."""

    def __init__(self, config: BlackoutConfig | None = None):
        self._config = config or BlackoutConfig()

    @property
    def config(self) -> BlackoutConfig:
        return self._config

    def is_in_blackout(
        self,
        ticker: str,
        decision_date: pd.Timestamp,
        events: dict[str, list[pd.Timestamp]],
    ) -> bool:
        """Check if decision_date is within blackout window of any event for ticker.

        Blackout window: [event_date - days_before, event_date + days_after]

        Args:
            ticker: Stock ticker symbol.
            decision_date: Date being evaluated.
            events: Dict mapping ticker -> list of event dates (earnings/corp action).

        Returns:
            True if in blackout period, False otherwise.
            Returns False if filter is disabled or no events for ticker.
        """
        if not self._config.enabled:
            return False

        ticker_events = events.get(ticker, [])
        if not ticker_events:
            return False

        for event_date in ticker_events:
            window_start = event_date - timedelta(days=self._config.days_before)
            window_end = event_date + timedelta(days=self._config.days_after)
            if window_start <= decision_date <= window_end:
                return True

        return False


__all__ = ["BlackoutConfig", "BlackoutFilter"]
