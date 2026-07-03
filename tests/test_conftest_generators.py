"""Smoke test: verify all Hypothesis generators in conftest.py work correctly."""

import sys
from pathlib import Path

import pandas as pd
from hypothesis import given, settings

# conftest.py is auto-loaded by pytest but needs explicit path for import
sys.path.insert(0, str(Path(__file__).parent))
from conftest import (  # noqa: E402
    ohlcv_dataframes,
    trade_simulations,
    bandarmology_rows,
    cost_model_configs,
    backtest_configs,
)


@given(df=ohlcv_dataframes())
@settings(max_examples=20)
def test_ohlcv_generator_constraints(df: pd.DataFrame):
    """Validate OHLCV generator produces valid data."""
    assert isinstance(df, pd.DataFrame)
    assert len(df) >= 5

    # Check columns exist
    for col in ("open", "high", "low", "close", "volume"):
        assert col in df.columns

    # Check constraints: high >= close >= low
    assert (df["high"] >= df["close"]).all(), "high must be >= close"
    assert (df["close"] >= df["low"]).all(), "close must be >= low"
    assert (df["high"] >= df["low"]).all(), "high must be >= low"

    # Volume >= 0
    assert (df["volume"] >= 0).all(), "volume must be >= 0"

    # Monotonically increasing dates
    assert df.index.is_monotonic_increasing, "dates must be monotonically increasing"


@given(trade=trade_simulations(completed=True))
@settings(max_examples=20)
def test_trade_simulation_generator_completed(trade: dict):
    """Validate completed TradeSimulation has all fields populated."""
    assert trade["ticker"] is not None
    assert trade["entry_price"] > 0
    assert trade["stop_loss"] < trade["entry_price"]
    assert trade["take_profit_1"] > trade["entry_price"]
    assert trade["take_profit_2"] > trade["take_profit_1"]
    assert trade["exit_event"] in ("TP1_HIT", "SL_HIT", "TIME_STOP")
    assert trade["exit_date"] is not None
    assert trade["exit_price"] is not None
    assert trade["holding_days"] >= 1


@given(trade=trade_simulations(completed=False))
@settings(max_examples=20)
def test_trade_simulation_generator_incomplete(trade: dict):
    """Validate incomplete TradeSimulation has None exit fields."""
    assert trade["exit_event"] is None
    assert trade["exit_date"] is None
    assert trade["exit_price"] is None


@given(row=bandarmology_rows())
@settings(max_examples=20)
def test_bandarmology_row_generator(row: dict):
    """Validate BandarmologyRow has all required fields."""
    required_fields = [
        "buyer_hhi", "top3_buyer_value", "top3_seller_value",
        "close_vs_top_buyer_avg", "broker_activity_available",
    ]
    for field in required_fields:
        assert field in row, f"Missing field: {field}"

    assert 0.0 <= row["buyer_hhi"] <= 1.0
    assert row["top3_buyer_value"] >= 0.0
    assert row["top3_seller_value"] >= 0.0
    assert isinstance(row["broker_activity_available"], bool)


@given(config=cost_model_configs())
@settings(max_examples=20)
def test_cost_model_config_generator(config: dict):
    """Validate CostModelConfig has valid ranges."""
    assert 0.0005 <= config["fee_buy_pct"] <= 0.005
    assert 0.001 <= config["fee_sell_pct"] <= 0.005
    assert 0.0005 <= config["slippage_pct"] <= 0.005
    assert isinstance(config["snap_to_tick"], bool)


@given(config=backtest_configs())
@settings(max_examples=20)
def test_backtest_config_generator(config: dict):
    """Validate BacktestConfig has valid structure."""
    assert config["start_date"] < config["end_date"]
    assert len(config["universe_tickers"]) >= 1
    assert config["time_stop_days"] >= 1
    assert config["min_sample_size"] >= 10
    assert config["warmup_days"] >= 50
    assert "cost_model" in config
