"""Tests for Stage 5A same_day_ambiguous_policy.

Validates:
- stop_first: SL assumed hit first (conservative, default)
- tp_first: TP assumed hit first (optimistic)
- skip_trade: trade is not counted as normal closed trade
"""
from __future__ import annotations

import math

import pandas as pd
import pytest

from interday_liquidity_screener.backtest_interday import (
    InterdayBacktestConfig,
    calculate_backtest_metrics,
    simulate_interday_signal,
)


def _signal_row(**overrides):
    row = {
        "ticker": "TEST",
        "yahoo_ticker": "TEST.JK",
        "last_date": "2026-01-01",
        "strategy_mode": "interday",
        "trade_status": "VALID_TRADE_PLAN",
        "is_plan_valid": True,
        "entry_price": 1000.0,
        "entry_trigger_price": 1000.0,
        "entry_zone_low": 990.0,
        "entry_zone_high": 1010.0,
        "stop_loss": 950.0,
        "take_profit_1": 1050.0,
        "take_profit_2": 1100.0,
        "time_stop_days": 5,
        "executable_position_size_lots": 1,
        "technical_context": "BREAKOUT_NEAR",
        "bandarmology_signal": "STRONG_ACCUMULATION",
        "bandarmology_score": 80,
    }
    row.update(overrides)
    return row


def _ambiguous_history():
    """Price history where TP1=1050 and SL=950 are both hit on the same day."""
    dates = pd.to_datetime(["2026-01-01", "2026-01-02"])
    return pd.DataFrame(
        [
            {"open": 990, "high": 1000, "low": 980, "close": 995, "volume": 1_000_000},
            # Day 2: high >= 1050 AND low <= 950
            {"open": 1000, "high": 1060, "low": 940, "close": 1020, "volume": 2_000_000},
        ],
        index=dates,
    )


# -----------------------------------------------------------------------
# stop_first policy (default)
# -----------------------------------------------------------------------


def test_stop_first_policy_exit_reason() -> None:
    """Default policy: SL hit assumed first, exit reason includes AMBIGUOUS."""
    config = InterdayBacktestConfig(
        slippage_pct=0, buy_fee_pct=0, sell_fee_pct=0,
        same_day_ambiguous_policy="stop_first",
    )
    result = simulate_interday_signal(_signal_row(), _ambiguous_history(), config)

    assert result["exit_reason"] == "SL_HIT_SAME_DAY_AMBIGUOUS"
    assert result["same_day_ambiguous"] is True
    assert result["backtest_status"] == "CLOSED_TRADE"
    assert result["net_return_pct"] < 0


def test_stop_first_policy_exit_price_uses_stop_loss() -> None:
    """Stop first means exit price is stop_loss."""
    config = InterdayBacktestConfig(slippage_pct=0, buy_fee_pct=0, sell_fee_pct=0)
    result = simulate_interday_signal(_signal_row(), _ambiguous_history(), config)

    assert result["exit_price"] == 950.0


# -----------------------------------------------------------------------
# tp_first policy (optimistic)
# -----------------------------------------------------------------------


def test_tp_first_policy_exit_reason() -> None:
    """tp_first: TP hit assumed first, exit reason is TP1_HIT_SAME_DAY_AMBIGUOUS."""
    config = InterdayBacktestConfig(
        slippage_pct=0, buy_fee_pct=0, sell_fee_pct=0,
        same_day_ambiguous_policy="tp_first",
    )
    result = simulate_interday_signal(_signal_row(), _ambiguous_history(), config)

    assert result["exit_reason"] == "TP1_HIT_SAME_DAY_AMBIGUOUS"
    assert result["same_day_ambiguous"] is True
    assert result["backtest_status"] == "CLOSED_TRADE"
    assert result["net_return_pct"] > 0


def test_tp_first_policy_exit_price_uses_tp1() -> None:
    """tp_first means exit price is TP1."""
    config = InterdayBacktestConfig(
        slippage_pct=0, buy_fee_pct=0, sell_fee_pct=0,
        same_day_ambiguous_policy="tp_first",
    )
    result = simulate_interday_signal(_signal_row(), _ambiguous_history(), config)

    assert result["exit_price"] == 1050.0


# -----------------------------------------------------------------------
# skip_trade policy
# -----------------------------------------------------------------------


def test_skip_trade_policy_status_is_ambiguous_skipped() -> None:
    """skip_trade: trade is not CLOSED_TRADE, status is AMBIGUOUS_SKIPPED."""
    config = InterdayBacktestConfig(
        slippage_pct=0, buy_fee_pct=0, sell_fee_pct=0,
        same_day_ambiguous_policy="skip_trade",
    )
    result = simulate_interday_signal(_signal_row(), _ambiguous_history(), config)

    assert result["backtest_status"] == "AMBIGUOUS_SKIPPED"
    assert result["same_day_ambiguous"] is True
    assert result["exit_reason"] == "AMBIGUOUS_SKIPPED"


def test_skip_trade_policy_does_not_count_as_win_or_loss() -> None:
    """AMBIGUOUS_SKIPPED should not have net_return_pct counted."""
    config = InterdayBacktestConfig(
        slippage_pct=0, buy_fee_pct=0, sell_fee_pct=0,
        same_day_ambiguous_policy="skip_trade",
    )
    result = simulate_interday_signal(_signal_row(), _ambiguous_history(), config)

    assert pd.isna(result["net_return_pct"])
    assert pd.isna(result["net_pnl_amount"])


def test_skip_trade_not_counted_in_metrics_win_loss() -> None:
    """Metrics should not count AMBIGUOUS_SKIPPED in win_count or loss_count."""
    trades = pd.DataFrame([
        {
            "backtest_status": "AMBIGUOUS_SKIPPED",
            "net_return_pct": pd.NA,
            "net_pnl_amount": pd.NA,
            "tp1_hit": True,
            "tp2_hit": False,
            "sl_hit": True,
            "time_stop_exit": False,
            "holding_days": 1,
            "mfe_pct": 0.05,
            "mae_pct": -0.05,
            "exit_date": "2026-01-02",
            "same_day_ambiguous": True,
        },
        {
            "backtest_status": "CLOSED_TRADE",
            "net_return_pct": 0.04,
            "net_pnl_amount": 40,
            "tp1_hit": True,
            "tp2_hit": False,
            "sl_hit": False,
            "time_stop_exit": False,
            "holding_days": 2,
            "mfe_pct": 0.05,
            "mae_pct": -0.01,
            "exit_date": "2026-01-03",
            "same_day_ambiguous": False,
        },
    ])

    metrics = calculate_backtest_metrics(trades, initial_capital=1000)

    assert metrics["ambiguous_trade_count"] == 1
    assert metrics["entry_triggered_count"] == 1  # Only CLOSED_TRADE
    assert metrics["win_count"] == 1
    assert metrics["loss_count"] == 0


# -----------------------------------------------------------------------
# Config validation
# -----------------------------------------------------------------------


def test_invalid_ambiguous_policy_raises_error() -> None:
    """Invalid same_day_ambiguous_policy should raise ValueError."""
    with pytest.raises(ValueError, match="same_day_ambiguous_policy"):
        InterdayBacktestConfig(same_day_ambiguous_policy="random_value")


# -----------------------------------------------------------------------
# Non-ambiguous trades unaffected by policy
# -----------------------------------------------------------------------


def test_non_ambiguous_tp_hit_unaffected_by_policy() -> None:
    """When only TP1 is hit (no SL), all policies produce the same result."""
    dates = pd.to_datetime(["2026-01-01", "2026-01-02"])
    history = pd.DataFrame(
        [
            {"open": 990, "high": 1000, "low": 980, "close": 995, "volume": 1_000_000},
            {"open": 1000, "high": 1060, "low": 960, "close": 1050, "volume": 2_000_000},
        ],
        index=dates,
    )

    for policy in ["stop_first", "tp_first", "skip_trade"]:
        config = InterdayBacktestConfig(
            slippage_pct=0, buy_fee_pct=0, sell_fee_pct=0,
            same_day_ambiguous_policy=policy,
        )
        result = simulate_interday_signal(_signal_row(stop_loss=955), history, config)

        assert result["exit_reason"] == "TP1_HIT", f"Failed for policy={policy}"
        assert result["same_day_ambiguous"] is False, f"Failed for policy={policy}"
        assert result["backtest_status"] == "CLOSED_TRADE", f"Failed for policy={policy}"


# -----------------------------------------------------------------------
# ambiguous_trade_count counts same_day_ambiguous=True across all policies
# -----------------------------------------------------------------------


def test_ambiguous_count_stop_first_increments() -> None:
    """stop_first ambiguous closed trade increments ambiguous_trade_count."""
    config = InterdayBacktestConfig(
        slippage_pct=0, buy_fee_pct=0, sell_fee_pct=0,
        same_day_ambiguous_policy="stop_first",
    )
    result = simulate_interday_signal(_signal_row(), _ambiguous_history(), config)

    trades = pd.DataFrame([result])
    metrics = calculate_backtest_metrics(trades, initial_capital=1000)

    assert result["same_day_ambiguous"] is True
    assert result["backtest_status"] == "CLOSED_TRADE"
    assert metrics["ambiguous_trade_count"] == 1


def test_ambiguous_count_tp_first_increments() -> None:
    """tp_first ambiguous closed trade increments ambiguous_trade_count."""
    config = InterdayBacktestConfig(
        slippage_pct=0, buy_fee_pct=0, sell_fee_pct=0,
        same_day_ambiguous_policy="tp_first",
    )
    result = simulate_interday_signal(_signal_row(), _ambiguous_history(), config)

    trades = pd.DataFrame([result])
    metrics = calculate_backtest_metrics(trades, initial_capital=1000)

    assert result["same_day_ambiguous"] is True
    assert result["backtest_status"] == "CLOSED_TRADE"
    assert metrics["ambiguous_trade_count"] == 1


def test_ambiguous_count_skip_trade_increments() -> None:
    """skip_trade ambiguous skipped trade also increments ambiguous_trade_count."""
    config = InterdayBacktestConfig(
        slippage_pct=0, buy_fee_pct=0, sell_fee_pct=0,
        same_day_ambiguous_policy="skip_trade",
    )
    result = simulate_interday_signal(_signal_row(), _ambiguous_history(), config)

    trades = pd.DataFrame([result])
    metrics = calculate_backtest_metrics(trades, initial_capital=1000)

    assert result["same_day_ambiguous"] is True
    assert result["backtest_status"] == "AMBIGUOUS_SKIPPED"
    assert metrics["ambiguous_trade_count"] == 1


def test_ambiguous_count_non_ambiguous_is_zero() -> None:
    """Non-ambiguous trade should not increment ambiguous_trade_count."""
    dates = pd.to_datetime(["2026-01-01", "2026-01-02"])
    history = pd.DataFrame(
        [
            {"open": 990, "high": 1000, "low": 980, "close": 995, "volume": 1_000_000},
            {"open": 1000, "high": 1060, "low": 960, "close": 1050, "volume": 2_000_000},
        ],
        index=dates,
    )
    config = InterdayBacktestConfig(slippage_pct=0, buy_fee_pct=0, sell_fee_pct=0)
    result = simulate_interday_signal(_signal_row(stop_loss=955), history, config)

    trades = pd.DataFrame([result])
    metrics = calculate_backtest_metrics(trades, initial_capital=1000)

    assert result["same_day_ambiguous"] is False
    assert metrics["ambiguous_trade_count"] == 0
