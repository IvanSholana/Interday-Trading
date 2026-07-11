from __future__ import annotations

import math

import pandas as pd

from interday_liquidity_screener.backtest_interday import (
    InterdayBacktestConfig,
    calculate_backtest_metrics,
    simulate_interday_signal,
)


def signal_row(**overrides):
    row = {
        "ticker": "TEST",
        "yahoo_ticker": "TEST.JK",
        "last_date": "2026-01-01",
        "strategy_mode": "interday",
        "trade_status": "VALID_TRADE_PLAN",
        "is_plan_valid": True,
        "entry_price": 100.0,
        "entry_trigger_price": 100.0,
        "entry_zone_low": 99.0,
        "entry_zone_high": 101.0,
        "stop_loss": 98.0,
        "take_profit_1": 102.0,
        "take_profit_2": 104.0,
        "time_stop_days": 3,
        "executable_position_size_lots": 1,
        "technical_context": "BREAKOUT_NEAR",
        "bandarmology_signal": "STRONG_ACCUMULATION",
        "bandarmology_score": 80,
    }
    row.update(overrides)
    return row


def price_history(rows):
    dates = pd.to_datetime([row[0] for row in rows])
    return pd.DataFrame(
        [
            {
                "open": row[1],
                "high": row[2],
                "low": row[3],
                "close": row[4],
                "volume": row[5] if len(row) > 5 else 1_000_000,
            }
            for row in rows
        ],
        index=dates,
    )


def test_trade_tp1_hit() -> None:
    # TP1=102, entry via next_open=99 (slippage 0). Trail activates at 99*1.02=100.98.
    # Day 2 high=102.5 > trail activation. Trail SL = 102.5*0.985=100.96.
    # Day 2 low=101 > trail SL 100.96, so no SL hit. TP1=102 hit cleanly.
    history = price_history(
        [
            ("2026-01-01", 99, 100, 98, 99),
            ("2026-01-02", 100, 102.5, 101, 102),
        ]
    )

    result = simulate_interday_signal(signal_row(), history, InterdayBacktestConfig(slippage_pct=0, buy_fee_pct=0, sell_fee_pct=0))

    assert "TP1" in result["exit_reason"]
    assert result["net_return_pct"] > 0
    assert result["tp1_hit"] is True


def test_trade_sl_hit() -> None:
    history = price_history(
        [
            ("2026-01-01", 99, 100, 98, 99),
            ("2026-01-02", 100, 101, 97.5, 98),
        ]
    )

    result = simulate_interday_signal(signal_row(), history, InterdayBacktestConfig(slippage_pct=0, buy_fee_pct=0, sell_fee_pct=0))

    assert result["exit_reason"] == "SL_HIT"
    assert result["net_return_pct"] < 0
    assert result["sl_hit"] is True


def test_same_day_tp_and_sl_uses_conservative_stop_first() -> None:
    # With trailing stop: high=103 triggers trail (103*0.985=101.46).
    # Low=97 < trail SL 101.46, AND high=103 ≥ TP1=102 → ambiguous.
    # stop_first policy: exit at trail SL with profit (trailing locked gain).
    history = price_history(
        [
            ("2026-01-01", 99, 100, 98, 99),
            ("2026-01-02", 100, 103, 97, 101),
        ]
    )

    result = simulate_interday_signal(signal_row(), history, InterdayBacktestConfig(slippage_pct=0, buy_fee_pct=0, sell_fee_pct=0))

    assert result["same_day_ambiguous"] is True
    # Trailing stop makes the exit profitable even with stop_first
    assert result["net_return_pct"] > 0


def test_time_stop() -> None:
    # Keep all prices within 1% of entry (99) so trailing stop never activates
    # (needs 2% move to activate). This tests pure time-stop behavior.
    history = price_history(
        [
            ("2026-01-01", 99, 99.5, 98.5, 99),
            ("2026-01-02", 99, 99.8, 98.5, 99.2),
            ("2026-01-05", 99.2, 99.9, 98.5, 99.5),
            ("2026-01-06", 99.5, 100, 98.5, 99.8),
        ]
    )

    result = simulate_interday_signal(
        signal_row(time_stop_days=3),
        history,
        InterdayBacktestConfig(slippage_pct=0, buy_fee_pct=0, sell_fee_pct=0),
    )

    assert result["exit_reason"] == "TIME_STOP"
    assert result["time_stop_exit"] is True
    assert result["holding_days"] == 3


def test_entry_not_triggered_for_next_day_entry_zone() -> None:
    history = price_history(
        [
            ("2026-01-01", 99, 100, 98, 99),
            ("2026-01-02", 105, 106, 104, 105),
        ]
    )

    result = simulate_interday_signal(
        signal_row(entry_zone_low=99, entry_zone_high=101),
        history,
        InterdayBacktestConfig(entry_mode="next_day_entry_zone", slippage_pct=0),
    )

    assert result["backtest_status"] == "ENTRY_NOT_TRIGGERED"


def test_entry_gap_too_high() -> None:
    history = price_history(
        [
            ("2026-01-01", 99, 100, 98, 99),
            ("2026-01-02", 105, 106, 104, 105),
        ]
    )

    result = simulate_interday_signal(
        signal_row(entry_price=100),
        history,
        InterdayBacktestConfig(slippage_pct=0, max_entry_gap_pct=0.03),
    )

    assert result["backtest_status"] == "ENTRY_REJECTED_GAP_TOO_HIGH"


def test_mfe_mae_are_calculated_until_exit_date() -> None:
    history = price_history(
        [
            ("2026-01-01", 99, 100, 98, 99),
            ("2026-01-02", 100, 101, 99, 100.5),
            ("2026-01-05", 100.5, 103, 97.5, 102.5),
        ]
    )

    result = simulate_interday_signal(signal_row(), history, InterdayBacktestConfig(slippage_pct=0, buy_fee_pct=0, sell_fee_pct=0))

    assert result["exit_reason"] == "SL_HIT_SAME_DAY_AMBIGUOUS"
    assert math.isclose(result["mfe_pct"], 0.03)
    assert math.isclose(result["mae_pct"], -0.025)


def test_metrics_profit_factor_and_win_rate() -> None:
    trades = pd.DataFrame(
        [
            {"backtest_status": "CLOSED_TRADE", "net_return_pct": 0.05, "net_pnl_amount": 50, "tp1_hit": True, "tp2_hit": False, "sl_hit": False, "time_stop_exit": False, "holding_days": 2, "mfe_pct": 0.06, "mae_pct": -0.01, "exit_date": "2026-01-02"},
            {"backtest_status": "CLOSED_TRADE", "net_return_pct": -0.02, "net_pnl_amount": -20, "tp1_hit": False, "tp2_hit": False, "sl_hit": True, "time_stop_exit": False, "holding_days": 1, "mfe_pct": 0.01, "mae_pct": -0.03, "exit_date": "2026-01-03"},
        ]
    )

    metrics = calculate_backtest_metrics(trades, initial_capital=1000)

    assert metrics["win_rate"] == 0.5
    assert metrics["profit_factor"] == 2.5
    assert math.isclose(metrics["expectancy_pct"], 0.015)


def test_invalid_stage4_row_is_not_evaluated_as_trade() -> None:
    history = price_history(
        [
            ("2026-01-01", 99, 100, 98, 99),
            ("2026-01-02", 100, 102.5, 99, 102),
        ]
    )

    result = simulate_interday_signal(signal_row(is_plan_valid=False), history, InterdayBacktestConfig())

    assert result["backtest_status"] == "SKIPPED_INVALID_STAGE4"
    assert pd.isna(result["entry_date"])
