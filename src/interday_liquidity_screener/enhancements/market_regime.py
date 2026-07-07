"""MarketRegimeFilter — evaluates market risk-on/risk-off condition.

Uses IHSG (^JKSE) trend and market breadth to determine if the overall market
environment is supportive for trade entry.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd


REGIME_RISK_ON = "RISK_ON"
REGIME_RISK_OFF = "RISK_OFF"
REGIME_AMBIGUOUS = "AMBIGUOUS"


@dataclass(frozen=True)
class MarketRegimeConfig:
    """Configuration for market regime filter.

    Attributes:
        enabled: Whether the filter is active.
        ihsg_ticker: Yahoo ticker for IHSG index.
        ihsg_ma_period: Moving average period for IHSG trend.
        breadth_ma_period: Moving average period for breadth calculation.
        breadth_threshold: Min % of stocks above their MA to qualify RISK_ON.
        regime_lookback_days: Days to confirm regime (consecutive).
    """

    enabled: bool = True
    ihsg_ticker: str = "^JKSE"
    ihsg_ma_period: int = 50
    breadth_ma_period: int = 50
    breadth_threshold: float = 0.50
    regime_lookback_days: int = 5


@dataclass
class MarketRegimeResult:
    """Result of market regime evaluation.

    Attributes:
        regime: RISK_ON, RISK_OFF, or AMBIGUOUS.
        ihsg_above_ma: Whether IHSG is above its MA.
        breadth_pct: Percentage of stocks above their MA.
        decision_date: Date the evaluation was made.
        warning: Optional warning message if data was insufficient.
    """

    regime: str
    ihsg_above_ma: bool | None
    breadth_pct: float | None
    decision_date: pd.Timestamp | None
    warning: str | None = None


class MarketRegimeFilter:
    """Evaluates whether the market is in a risk-on condition.

    Logic:
    - RISK_ON: IHSG above MA AND breadth >= threshold
    - RISK_OFF: IHSG below MA AND breadth < threshold
    - AMBIGUOUS: Mixed signals or insufficient data
    """

    def __init__(self, config: MarketRegimeConfig | None = None) -> None:
        self._config = config or MarketRegimeConfig()

    @property
    def config(self) -> MarketRegimeConfig:
        return self._config

    def evaluate(
        self,
        ihsg_data: pd.DataFrame | None,
        universe_data: dict[str, pd.DataFrame] | None = None,
        decision_date: pd.Timestamp | None = None,
    ) -> MarketRegimeResult:
        """Evaluate market regime using only data up to decision_date.

        Args:
            ihsg_data: OHLCV DataFrame for IHSG with DatetimeIndex.
                       Must have 'close' column.
            universe_data: Dict of ticker -> OHLCV DataFrames for breadth calc.
                           Optional; if None, only IHSG trend is used.
            decision_date: Date to evaluate. Uses only data <= this date.
                           If None, uses the latest available date.

        Returns:
            MarketRegimeResult with regime classification.
        """
        if not self._config.enabled:
            return MarketRegimeResult(
                regime=REGIME_RISK_ON,
                ihsg_above_ma=None,
                breadth_pct=None,
                decision_date=decision_date,
                warning="market_regime_filter_disabled",
            )

        # Evaluate IHSG trend
        ihsg_above_ma = self._evaluate_ihsg(ihsg_data, decision_date)

        # Evaluate breadth
        breadth_pct = self._evaluate_breadth(universe_data, decision_date)

        # Classify regime
        regime = self._classify(ihsg_above_ma, breadth_pct)

        warning = None
        if ihsg_above_ma is None and breadth_pct is None:
            warning = "insufficient_data_for_regime_evaluation"
        elif ihsg_above_ma is None:
            warning = "ihsg_data_unavailable_using_breadth_only"
        elif breadth_pct is None:
            warning = "breadth_data_unavailable_using_ihsg_only"

        return MarketRegimeResult(
            regime=regime,
            ihsg_above_ma=ihsg_above_ma,
            breadth_pct=breadth_pct,
            decision_date=decision_date,
            warning=warning,
        )

    def _evaluate_ihsg(
        self, ihsg_data: pd.DataFrame | None, decision_date: pd.Timestamp | None
    ) -> bool | None:
        """Check if IHSG is above its MA on the decision date."""
        if ihsg_data is None or ihsg_data.empty:
            return None

        close_col = "close" if "close" in ihsg_data.columns else "Close"
        if close_col not in ihsg_data.columns:
            return None

        data = ihsg_data.copy()
        if decision_date is not None:
            data = data[data.index <= decision_date]

        if len(data) < self._config.ihsg_ma_period:
            return None

        ma = data[close_col].rolling(self._config.ihsg_ma_period).mean()
        if ma.empty or pd.isna(ma.iloc[-1]):
            return None

        latest_close = data[close_col].iloc[-1]
        latest_ma = ma.iloc[-1]

        if pd.isna(latest_close) or pd.isna(latest_ma):
            return None

        return float(latest_close) > float(latest_ma)

    def _evaluate_breadth(
        self,
        universe_data: dict[str, pd.DataFrame] | None,
        decision_date: pd.Timestamp | None,
    ) -> float | None:
        """Calculate % of stocks above their MA50."""
        if not universe_data:
            return None

        above_count = 0
        total_count = 0

        for ticker, df in universe_data.items():
            if df is None or df.empty:
                continue

            close_col = "close" if "close" in df.columns else "Close"
            if close_col not in df.columns:
                continue

            data = df.copy()
            if decision_date is not None:
                data = data[data.index <= decision_date]

            if len(data) < self._config.breadth_ma_period:
                continue

            ma = data[close_col].rolling(self._config.breadth_ma_period).mean()
            if ma.empty or pd.isna(ma.iloc[-1]):
                continue

            latest_close = data[close_col].iloc[-1]
            latest_ma = ma.iloc[-1]

            if pd.isna(latest_close) or pd.isna(latest_ma):
                continue

            total_count += 1
            if float(latest_close) > float(latest_ma):
                above_count += 1

        if total_count == 0:
            return None

        return above_count / total_count

    def _classify(self, ihsg_above_ma: bool | None, breadth_pct: float | None) -> str:
        """Classify regime based on IHSG trend and breadth.

        Rules:
        - Both available: RISK_ON if both positive, RISK_OFF if both negative, AMBIGUOUS otherwise
        - Only IHSG: RISK_ON if above MA, RISK_OFF otherwise
        - Only breadth: RISK_ON if >= threshold, RISK_OFF otherwise
        - Neither: AMBIGUOUS
        """
        if ihsg_above_ma is None and breadth_pct is None:
            return REGIME_AMBIGUOUS

        if ihsg_above_ma is not None and breadth_pct is not None:
            breadth_ok = breadth_pct >= self._config.breadth_threshold
            if ihsg_above_ma and breadth_ok:
                return REGIME_RISK_ON
            if not ihsg_above_ma and not breadth_ok:
                return REGIME_RISK_OFF
            return REGIME_AMBIGUOUS

        # Only one signal available
        if ihsg_above_ma is not None:
            return REGIME_RISK_ON if ihsg_above_ma else REGIME_RISK_OFF

        # Only breadth
        breadth_ok = breadth_pct >= self._config.breadth_threshold
        return REGIME_RISK_ON if breadth_ok else REGIME_RISK_OFF


def evaluate_market_regime(
    ihsg_data: pd.DataFrame | None = None,
    universe_data: dict[str, pd.DataFrame] | None = None,
    decision_date: pd.Timestamp | None = None,
    config: MarketRegimeConfig | None = None,
) -> MarketRegimeResult:
    """Convenience function to evaluate market regime."""
    flt = MarketRegimeFilter(config)
    return flt.evaluate(ihsg_data, universe_data, decision_date)


__all__ = [
    "MarketRegimeConfig",
    "MarketRegimeFilter",
    "MarketRegimeResult",
    "evaluate_market_regime",
    "REGIME_RISK_ON",
    "REGIME_RISK_OFF",
    "REGIME_AMBIGUOUS",
]
