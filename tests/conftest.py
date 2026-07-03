"""Shared test fixtures and Hypothesis generators for property-based testing.

Provides strategies for generating:
- OHLCV DataFrames with valid price constraints
- TradeSimulation instances with realistic IDX stock parameters
- BandarmologyRow dicts with all scoring fields
- BacktestConfig and CostModelConfig instances

Validates: Requirements 1.1, 3.1
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

import pandas as pd
import pytest
from hypothesis import settings, HealthCheck
from hypothesis import strategies as st

# ---------------------------------------------------------------------------
# Hypothesis profiles: max_examples=100
# ---------------------------------------------------------------------------
settings.register_profile(
    "default",
    max_examples=100,
    suppress_health_check=[HealthCheck.too_slow],
)
settings.register_profile(
    "ci",
    max_examples=100,
    suppress_health_check=[HealthCheck.too_slow],
)
settings.load_profile("default")


# ---------------------------------------------------------------------------
# OHLCV DataFrame Generator
# ---------------------------------------------------------------------------

@st.composite
def ohlcv_dataframes(
    draw: st.DrawFn,
    min_rows: int = 5,
    max_rows: int = 60,
    min_price: float = 50.0,
    max_price: float = 20000.0,
) -> pd.DataFrame:
    """Generate a valid OHLCV DataFrame.

    Constraints:
    - high >= open, high >= close
    - low <= open, low <= close
    - volume >= 0
    - Dates are monotonically increasing business days
    """
    n_rows = draw(st.integers(min_value=min_rows, max_value=max_rows))

    # Generate a start date (business day)
    start_year = draw(st.integers(min_value=2020, max_value=2024))
    start_month = draw(st.integers(min_value=1, max_value=12))
    start_day = draw(st.integers(min_value=1, max_value=28))
    start_date = pd.Timestamp(year=start_year, month=start_month, day=start_day)

    # Generate monotonically increasing business day dates
    dates = pd.bdate_range(start=start_date, periods=n_rows, freq="B")

    rows = []
    for _ in range(n_rows):
        # Generate open price
        open_price = draw(
            st.floats(min_value=min_price, max_value=max_price, allow_nan=False, allow_infinity=False)
        )
        # Generate close price
        close_price = draw(
            st.floats(min_value=min_price, max_value=max_price, allow_nan=False, allow_infinity=False)
        )
        # high must be >= max(open, close)
        high_floor = max(open_price, close_price)
        high_price = draw(
            st.floats(min_value=high_floor, max_value=high_floor * 1.15, allow_nan=False, allow_infinity=False)
        )
        # low must be <= min(open, close)
        low_ceil = min(open_price, close_price)
        low_price = draw(
            st.floats(min_value=max(min_price * 0.5, low_ceil * 0.85), max_value=low_ceil, allow_nan=False, allow_infinity=False)
        )
        # volume >= 0
        volume = draw(st.integers(min_value=0, max_value=500_000_000))

        rows.append({
            "open": open_price,
            "high": high_price,
            "low": low_price,
            "close": close_price,
            "volume": volume,
        })

    df = pd.DataFrame(rows, index=dates[:n_rows])
    df.index.name = "date"
    return df


# ---------------------------------------------------------------------------
# TradeSimulation Generator
# ---------------------------------------------------------------------------

# IDX tickers for realistic generation
_IDX_TICKERS = [
    "BBRI.JK", "BBCA.JK", "BMRI.JK", "TLKM.JK", "ASII.JK",
    "UNTR.JK", "BBNI.JK", "INDF.JK", "KLBF.JK", "ANTM.JK",
    "MYOR.JK", "CPIN.JK", "JPFA.JK", "MEDC.JK", "PGAS.JK",
]

_EXIT_EVENTS = ["TP1_HIT", "SL_HIT", "TIME_STOP"]

_ENTRY_SETUPS = ["BREAKOUT", "REBOUND", "PULLBACK_TO_MA", "VOLUME_SPIKE", None]

_TECHNICAL_CONTEXTS = [
    "BREAKOUT_NEAR", "REBOUND_NEAR_LOW", "PULLBACK_TO_MA",
    "UPTREND_CONTINUATION", "VOLUME_SPIKE", None,
]

_BANDARMOLOGY_SIGNALS = [
    "STRONG_ACCUMULATION", "MILD_ACCUMULATION", "NEUTRAL_FLOW",
    "MILD_DISTRIBUTION", "STRONG_DISTRIBUTION", "NO_BROKER_DATA", None,
]


@st.composite
def trade_simulations(
    draw: st.DrawFn,
    completed: bool = True,
) -> dict:
    """Generate a valid TradeSimulation as a dict with realistic IDX stock parameters.

    Returns a dict matching the TradeSimulation dataclass fields.
    If completed=True, exit fields are populated; otherwise they remain None.
    """
    ticker = draw(st.sampled_from(_IDX_TICKERS))

    # Entry price in IDX range (Rp 50 - Rp 20,000)
    entry_price = draw(
        st.floats(min_value=100.0, max_value=15000.0, allow_nan=False, allow_infinity=False)
    )
    # Raw entry price slightly lower (before slippage)
    raw_entry_price = entry_price * draw(
        st.floats(min_value=0.990, max_value=0.999, allow_nan=False, allow_infinity=False)
    )

    # Stop loss below entry (2-8% below)
    sl_pct = draw(st.floats(min_value=0.02, max_value=0.08, allow_nan=False, allow_infinity=False))
    stop_loss = entry_price * (1.0 - sl_pct)

    # Take profit above entry (2-12% above)
    tp1_pct = draw(st.floats(min_value=0.02, max_value=0.08, allow_nan=False, allow_infinity=False))
    tp2_pct = draw(st.floats(min_value=tp1_pct + 0.01, max_value=0.15, allow_nan=False, allow_infinity=False))
    take_profit_1 = entry_price * (1.0 + tp1_pct)
    take_profit_2 = entry_price * (1.0 + tp2_pct)

    # Entry date
    entry_year = draw(st.integers(min_value=2021, max_value=2024))
    entry_month = draw(st.integers(min_value=1, max_value=12))
    entry_day = draw(st.integers(min_value=1, max_value=28))
    entry_date = pd.Timestamp(year=entry_year, month=entry_month, day=entry_day)

    result = {
        "ticker": ticker,
        "entry_date": entry_date,
        "entry_price": round(entry_price, 2),
        "raw_entry_price": round(raw_entry_price, 2),
        "stop_loss": round(stop_loss, 2),
        "take_profit_1": round(take_profit_1, 2),
        "take_profit_2": round(take_profit_2, 2),
        "exit_date": None,
        "exit_price": None,
        "exit_event": None,
        "return_gross": None,
        "return_net": None,
        "r_multiple": None,
        "mfe": None,
        "mae": None,
        "holding_days": None,
        "entry_setup": draw(st.sampled_from(_ENTRY_SETUPS)),
        "technical_context": draw(st.sampled_from(_TECHNICAL_CONTEXTS)),
        "bandarmology_signal": draw(st.sampled_from(_BANDARMOLOGY_SIGNALS)),
    }

    if completed:
        exit_event = draw(st.sampled_from(_EXIT_EVENTS))
        holding_days = draw(st.integers(min_value=1, max_value=15))
        exit_date = entry_date + pd.Timedelta(days=holding_days)

        # Exit price depends on event
        if exit_event == "TP1_HIT":
            exit_price = take_profit_1
        elif exit_event == "SL_HIT":
            exit_price = stop_loss
        else:  # TIME_STOP
            # Exit at some price between SL and TP
            exit_price = draw(
                st.floats(
                    min_value=stop_loss,
                    max_value=take_profit_1,
                    allow_nan=False,
                    allow_infinity=False,
                )
            )

        return_gross = (exit_price / entry_price) - 1.0
        return_net = return_gross - 0.0015 - 0.0025  # fee_buy + fee_sell
        risk = entry_price - stop_loss
        r_multiple = (exit_price - entry_price) / risk if risk > 0 else 0.0

        # MFE/MAE as percentages
        mfe = draw(st.floats(min_value=0.0, max_value=0.15, allow_nan=False, allow_infinity=False))
        mae = draw(st.floats(min_value=0.0, max_value=0.10, allow_nan=False, allow_infinity=False))

        result.update({
            "exit_date": exit_date,
            "exit_price": round(exit_price, 2),
            "exit_event": exit_event,
            "return_gross": round(return_gross, 6),
            "return_net": round(return_net, 6),
            "r_multiple": round(r_multiple, 4),
            "mfe": round(mfe, 6),
            "mae": round(mae, 6),
            "holding_days": holding_days,
        })

    return result


# ---------------------------------------------------------------------------
# BandarmologyRow Generator
# ---------------------------------------------------------------------------

@st.composite
def bandarmology_rows(draw: st.DrawFn) -> dict:
    """Generate a dict representing a bandarmology scoring row.

    Keys include: buyer_hhi, seller_hhi, top3_buyer_value, top3_seller_value,
    close_vs_top_buyer_avg, broker_activity_available, and other scoring fields.
    """
    broker_activity_available = draw(st.booleans())

    # HHI values (0 to 1)
    buyer_hhi = draw(
        st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False)
    )
    seller_hhi = draw(
        st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False)
    )

    # Top3 values in IDX rupiah range
    top3_buyer_value = draw(
        st.floats(min_value=0.0, max_value=100_000_000_000.0, allow_nan=False, allow_infinity=False)
    )
    top3_seller_value = draw(
        st.floats(min_value=0.0, max_value=100_000_000_000.0, allow_nan=False, allow_infinity=False)
    )

    # Close vs top buyer avg: relative difference (can be negative or positive)
    close_vs_top_buyer_avg = draw(
        st.floats(min_value=-0.5, max_value=0.5, allow_nan=False, allow_infinity=False)
    )

    # Existing scoring fields
    broker_accdist = draw(st.sampled_from(["big acc", "acc", "big dist", "dist", "neutral", None]))
    avg_accdist = draw(st.sampled_from(["big acc", "acc", "big dist", "dist", "neutral", None]))
    top3_accdist = draw(st.sampled_from(["big acc", "acc", "big dist", "dist", "neutral", None]))
    top5_accdist = draw(st.sampled_from(["big acc", "acc", "big dist", "dist", "neutral", None]))
    avg_percent = draw(
        st.one_of(
            st.none(),
            st.floats(min_value=-50.0, max_value=50.0, allow_nan=False, allow_infinity=False),
        )
    )
    avg_amount = draw(
        st.one_of(
            st.none(),
            st.floats(min_value=-1e10, max_value=1e10, allow_nan=False, allow_infinity=False),
        )
    )
    relative_activity_bucket = draw(
        st.sampled_from(["NORMAL", "ACTIVE", "VERY_ACTIVE", "INACTIVE", None])
    )
    close_location = draw(
        st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False)
    )
    momentum_score = draw(
        st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False)
    )
    technical_context = draw(
        st.sampled_from([
            "BREAKOUT_NEAR", "REBOUND_NEAR_LOW", "PULLBACK_TO_MA",
            "UPTREND_CONTINUATION", "VOLUME_SPIKE",
            "TOO_VOLATILE", "TOO_QUIET_ABSOLUTE", "NEUTRAL", None,
        ])
    )
    close = draw(
        st.floats(min_value=50.0, max_value=20000.0, allow_nan=False, allow_infinity=False)
    )
    detector_average_price = draw(
        st.floats(min_value=50.0, max_value=20000.0, allow_nan=False, allow_infinity=False)
    )

    return {
        "broker_activity_available": broker_activity_available,
        "buyer_hhi": buyer_hhi,
        "seller_hhi": seller_hhi,
        "top3_buyer_value": top3_buyer_value,
        "top3_seller_value": top3_seller_value,
        "close_vs_top_buyer_avg": close_vs_top_buyer_avg,
        "broker_accdist": broker_accdist,
        "avg_accdist": avg_accdist,
        "top3_accdist": top3_accdist,
        "top5_accdist": top5_accdist,
        "avg_percent": avg_percent,
        "avg_amount": avg_amount,
        "relative_activity_bucket": relative_activity_bucket,
        "close_location": close_location,
        "momentum_score": momentum_score,
        "technical_context": technical_context,
        "close": close,
        "detector_average_price": detector_average_price,
    }


# ---------------------------------------------------------------------------
# Config Generators
# ---------------------------------------------------------------------------

@st.composite
def cost_model_configs(draw: st.DrawFn) -> dict:
    """Generate valid CostModelConfig parameters."""
    return {
        "fee_buy_pct": draw(
            st.floats(min_value=0.0005, max_value=0.005, allow_nan=False, allow_infinity=False)
        ),
        "fee_sell_pct": draw(
            st.floats(min_value=0.001, max_value=0.005, allow_nan=False, allow_infinity=False)
        ),
        "slippage_pct": draw(
            st.floats(min_value=0.0005, max_value=0.005, allow_nan=False, allow_infinity=False)
        ),
        "snap_to_tick": draw(st.booleans()),
    }


@st.composite
def backtest_configs(draw: st.DrawFn) -> dict:
    """Generate valid BacktestConfig parameters."""
    # Generate start date
    start_year = draw(st.integers(min_value=2020, max_value=2023))
    start_month = draw(st.integers(min_value=1, max_value=12))
    start_date = f"{start_year}-{start_month:02d}-01"

    # End date is 1-12 months after start
    end_offset_months = draw(st.integers(min_value=1, max_value=12))
    end_month = start_month + end_offset_months
    end_year = start_year + (end_month - 1) // 12
    end_month = ((end_month - 1) % 12) + 1
    end_date = f"{end_year}-{end_month:02d}-28"

    # Universe tickers (1-10 tickers)
    n_tickers = draw(st.integers(min_value=1, max_value=10))
    universe_tickers = draw(
        st.lists(
            st.sampled_from(_IDX_TICKERS),
            min_size=n_tickers,
            max_size=n_tickers,
            unique=True,
        )
    )

    time_stop_days = draw(st.integers(min_value=1, max_value=30))
    min_sample_size = draw(st.integers(min_value=10, max_value=100))
    warmup_days = draw(st.integers(min_value=50, max_value=300))

    cost_model = draw(cost_model_configs())

    return {
        "start_date": start_date,
        "end_date": end_date,
        "universe_tickers": universe_tickers,
        "time_stop_days": time_stop_days,
        "cost_model": cost_model,
        "min_sample_size": min_sample_size,
        "warmup_days": warmup_days,
        "output_dir": "data/output/backtest",
    }


# ---------------------------------------------------------------------------
# Convenience fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_ohlcv_df() -> pd.DataFrame:
    """A fixed sample OHLCV DataFrame for deterministic unit tests."""
    dates = pd.bdate_range(start="2023-01-02", periods=10, freq="B")
    data = {
        "open": [1000, 1010, 1020, 1015, 1030, 1025, 1040, 1035, 1050, 1045],
        "high": [1020, 1025, 1035, 1030, 1045, 1040, 1055, 1050, 1065, 1060],
        "low": [990, 1000, 1010, 1005, 1020, 1015, 1030, 1025, 1040, 1035],
        "close": [1010, 1020, 1015, 1030, 1025, 1040, 1035, 1050, 1045, 1055],
        "volume": [1000000, 1200000, 900000, 1500000, 1100000, 1300000, 950000, 1400000, 1050000, 1250000],
    }
    df = pd.DataFrame(data, index=dates)
    df.index.name = "date"
    return df


@pytest.fixture
def sample_trade_simulation() -> dict:
    """A fixed sample TradeSimulation dict for deterministic unit tests."""
    return {
        "ticker": "BBRI.JK",
        "entry_date": pd.Timestamp("2023-06-01"),
        "entry_price": 4500.0,
        "raw_entry_price": 4490.0,
        "stop_loss": 4275.0,
        "take_profit_1": 4725.0,
        "take_profit_2": 4950.0,
        "exit_date": pd.Timestamp("2023-06-08"),
        "exit_price": 4725.0,
        "exit_event": "TP1_HIT",
        "return_gross": 0.05,
        "return_net": 0.046,
        "r_multiple": 1.0,
        "mfe": 0.06,
        "mae": 0.02,
        "holding_days": 5,
        "entry_setup": "BREAKOUT",
        "technical_context": "BREAKOUT_NEAR",
        "bandarmology_signal": "STRONG_ACCUMULATION",
    }
