"""
constants.py – Centralized trading status labels and pipeline stage keys.

All string literals used as status/stage identifiers throughout the codebase
should reference these Enum members instead of bare string literals.
This makes it impossible for an LLM or developer to accidentally write a
typo like "EXECUTION_DRAFT" vs "EXECUTION_DRAFT" and ensures a single
source-of-truth for every status label.

Usage::

    from interday_liquidity_screener.constants import WatchlistStatus, PipelineStage

    if row["final_status"] == WatchlistStatus.EXECUTION_READY:
        ...

    if "stage1" in selected_stages:
        # prefer PipelineStage.STAGE1.value
        ...
"""
from __future__ import annotations

from enum import Enum


class WatchlistStatus(str, Enum):
    """
    All possible values for the ``final_status`` column produced by
    the hybrid screener (``hybrid_screener.py``).

    The ``str`` mixin makes comparison with raw DataFrame string values
    work transparently (e.g. ``row["final_status"] == WatchlistStatus.SKIP``).

    Status hierarchy (loosely best → worst):
      EXECUTION_READY > EXECUTION_CANDIDATE > EXECUTION_DRAFT
      > NEED_ORDERBOOK > READY_SOON > EARLY_WATCH
      > SKIP (neutral) > warning/rejection statuses
    """

    # --- Actionable / Positive ---
    EXECUTION_READY = "EXECUTION_READY"
    """
    All checks passed. Entry price, TP, SL, position size are set.
    Safe to place order at market open.
    """

    EXECUTION_CANDIDATE = "EXECUTION_CANDIDATE"
    """
    High score but one minor condition not confirmed yet (e.g. orderbook
    not yet checked or borderline R:R ratio). Monitor closely.
    """

    EXECUTION_DRAFT = "EXECUTION_DRAFT"
    """
    Trade plan built but awaiting live orderbook confirmation.
    Typically used in Fase Malam (H-1) runs before market opens.
    """

    NEED_ORDERBOOK = "NEED_ORDERBOOK"
    """
    Stock passed all historical-data stages but Stage 3C orderbook
    filter has not been run yet. Re-run Fase Pagi to resolve.
    """

    READY_SOON = "READY_SOON"
    """
    Conditions improving. Not yet in entry zone; worth watching.
    """

    EARLY_WATCH = "EARLY_WATCH"
    """
    Early accumulation signals detected. Low confidence; keep on radar.
    """

    # --- Neutral ---
    SKIP = "SKIP"

    # Canonical BPJS funnel labels. Legacy granular statuses remain available
    # for compatibility and are mapped to these labels in screener output.
    WATCHLIST = "WATCHLIST"
    REJECT = "REJECT"
    NO_TRADE = "NO_TRADE"
    """
    Screener ran successfully but stock did not meet minimum thresholds.
    Not a rejection due to risk — just filtered out.
    """

    # --- Risk / Rejection ---
    DANGER_CHASING = "DANGER_CHASING"
    """
    Price already extended significantly above entry zone. Entering now
    would be chasing; high loss risk.
    """

    DISTRIBUTION_WARNING = "DISTRIBUTION_WARNING"
    """
    Broker flow shows net selling / distribution pattern. Smart money
    may be exiting. Do not enter.
    """

    ORDERBOOK_WEAK = "ORDERBOOK_WEAK"
    """
    Orderbook bid depth is thin relative to offer depth. Price likely
    to slide on market orders.
    """

    ORDERBOOK_REJECT = "ORDERBOOK_REJECT"
    """
    Spread too wide, offer wall detected, or bid/offer ratio below
    threshold. Order execution risk is too high.
    """

    LOW_LIQUIDITY = "LOW_LIQUIDITY"
    """
    Average daily transaction value is below the minimum liquidity
    threshold. Hard to enter/exit without significant slippage.
    """

    NET_PROFIT_NOT_WORTH_IT = "NET_PROFIT_NOT_WORTH_IT"
    """
    Expected net profit after fees and slippage is too small to justify
    the trade (e.g. < Rp 5,000 net on 1 lot).
    """

    TOO_EXPENSIVE_FOR_CAPITAL = "TOO_EXPENSIVE_FOR_CAPITAL"
    """
    Minimum buyable quantity (1 lot = 100 shares) exceeds available
    capital or configured max_position_pct limit.
    """

    RISK_REWARD_BAD = "RISK_REWARD_BAD"
    """
    Risk-to-reward ratio is below the configured minimum (typically < 1.5).
    """

    COMMODITY_HEADWIND = "COMMODITY_HEADWIND"
    """
    The underlying global commodity is down heavily. Avoid buying this ticker now.
    """

    DATA_INSUFFICIENT = "DATA_INSUFFICIENT"
    """
    Not enough OHLCV or broker-flow data to compute a reliable score.
    Usually caused by a newly listed stock or a data API failure.
    """


class PipelineStage(str, Enum):
    """
    All valid pipeline stage keys accepted by the ``/api/run`` endpoint
    and the ``selected_stages`` UI field.

    These map 1-to-1 to the ``STAGE_FILES`` dictionary in ``pipeline.py``.
    """

    STAGE1 = "stage1"
    """Stage 1 – Liquidity screening via yfinance OHLCV data."""

    STAGE2 = "stage2"
    """Stage 2 – Technical indicator screening (MA, RSI, ATR, CLV, etc.)."""

    STAGE3A = "stage3a"
    """Stage 3A – Stockbit broker-flow collection (multi-window net buy/sell)."""

    STAGE3B = "stage3b"
    """Stage 3B – Bandarmology scoring (accumulation/distribution signals)."""

    STAGE3C = "stage3c"
    """Stage 3C – Live orderbook filter (spread, bid depth, offer walls)."""

    STAGE4 = "stage4"
    """Stage 4 – Trade plan generation (entry, TP1, TP2, SL, position size, fees)."""

    HYBRID = "hybrid"
    """Stage Hybrid – Dual flow watchlist scoring and final status assignment."""

    STAGE5 = "stage5"
    """Stage 5 – Backtest / paper trading simulation (interday or BPJS mode)."""

    STAGE6 = "stage6"
    """Stage 6 – LLM AI report generation (evidence → ranking → narrative)."""


# Convenient groupings for the Phase Preset buttons in the React UI
PHASE_MALAM_STAGES: list[str] = [
    PipelineStage.STAGE1,
    PipelineStage.STAGE2,
    PipelineStage.STAGE3A,
    PipelineStage.STAGE3B,
    PipelineStage.STAGE4,
    PipelineStage.HYBRID,
    PipelineStage.STAGE5,
    PipelineStage.STAGE6,
]
"""
Stages used in Fase Malam (H-1 evening run).
Excludes Stage 3C because the orderbook is closed at night.
"""

PHASE_PAGI_STAGES: list[str] = [
    PipelineStage.STAGE3C,
    PipelineStage.STAGE4,
    PipelineStage.HYBRID,
    PipelineStage.STAGE5,
    PipelineStage.STAGE6,
]
"""
Stages used in Fase Pagi (morning live-orderbook confirmation run).
Designed to resume from a completed Fase Malam run using ``resume_run_id``.
"""
