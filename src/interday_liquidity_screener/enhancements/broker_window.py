"""BrokerWindowAligner — aligns broker flow collection window with Stage 2."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BrokerWindowConfig:
    """Configuration for broker window alignment."""

    window_days: int = 20


class BrokerWindowAligner:
    """Aligns broker flow data collection window with Stage 2 last dates."""

    def __init__(self, config: BrokerWindowConfig | None = None) -> None:
        self.config = config or BrokerWindowConfig()

    def align_window(
        self,
        stage2_last_dates: dict[str, str],
        default_end_date: str,
    ) -> dict[str, tuple[str, str]]:
        """Return dict[ticker -> (from_date, to_date)].

        to_date = stage2_last_dates[ticker] if available, else default_end_date.
        from_date = to_date - window_days (calendar days).
        Logs a warning when using the default fallback.
        """
        result: dict[str, tuple[str, str]] = {}

        for ticker, last_date_str in stage2_last_dates.items():
            if last_date_str:
                to_date = date.fromisoformat(last_date_str)
            else:
                logger.warning(
                    "Ticker %s has empty last_date, using default_end_date=%s",
                    ticker,
                    default_end_date,
                )
                to_date = date.fromisoformat(default_end_date)

            from_date = to_date - timedelta(days=self.config.window_days)
            result[ticker] = (from_date.isoformat(), to_date.isoformat())

        return result


__all__ = ["BrokerWindowAligner", "BrokerWindowConfig"]
