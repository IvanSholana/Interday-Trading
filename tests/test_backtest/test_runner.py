"""Tests for WalkForwardRunner and TradeLedger."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from interday_liquidity_screener.backtest.config import BacktestConfig, CostModelConfig
from interday_liquidity_screener.backtest.runner import (
    TradeLedger,
    WalkForwardRunner,
    _noop_signal_generator,
)
from interday_liquidity_screener.backtest.simulator import TradeSimulation


# --- Helpers ---


def _make_price_df(
    start: str = "2023-01-01",
    periods: int = 250,
    base_price: float = 1000.0,
) -> pd.DataFrame:
    """Create a synthetic OHLCV DataFrame for testing."""
    dates = pd.bdate_range(start=start, periods=periods)
    rng = np.random.default_rng(42)
    close = base_price + np.cumsum(rng.normal(0, 5, periods))
    close = np.maximum(close, 50)  # Ensure positive prices

    df = pd.DataFrame(
        {
            "open": close * (1 + rng.uniform(-0.01, 0.01, periods)),
            "high": close * (1 + rng.uniform(0.005, 0.03, periods)),
            "low": close * (1 - rng.uniform(0.005, 0.03, periods)),
            "close": close,
            "volume": rng.integers(1_000_000, 10_000_000, periods),
        },
        index=dates,
    )
    return df


def _simple_signal_generator(
    df: pd.DataFrame, ticker: str, date: pd.Timestamp
) -> list[TradeSimulation]:
    """Generate a single dummy trade signal on every call."""
    last_close = float(df["close"].iloc[-1])
    return [
        TradeSimulation(
            ticker=ticker,
            entry_date=date,
            entry_price=last_close * 1.001,  # pretend slippage applied
            raw_entry_price=last_close,
            stop_loss=last_close * 0.95,
            take_profit_1=last_close * 1.05,
            take_profit_2=last_close * 1.08,
            entry_setup="TEST_SETUP",
        )
    ]


# --- TradeLedger Tests ---


class TestTradeLedger:
    def test_empty_ledger_to_dataframe(self):
        """to_dataframe() on empty ledger returns DataFrame with correct columns."""
        ledger = TradeLedger()
        df = ledger.to_dataframe()
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 0
        assert "ticker" in df.columns
        assert "entry_date" in df.columns
        assert "exit_event" in df.columns

    def test_to_dataframe_with_trades(self):
        """to_dataframe() converts trades to rows correctly."""
        trade = TradeSimulation(
            ticker="BBRI",
            entry_date=pd.Timestamp("2023-06-01"),
            entry_price=4500.0,
            raw_entry_price=4495.0,
            stop_loss=4200.0,
            take_profit_1=4700.0,
            take_profit_2=4900.0,
            exit_date=pd.Timestamp("2023-06-05"),
            exit_price=4700.0,
            exit_event="TP1_HIT",
        )
        ledger = TradeLedger(trades=[trade])
        df = ledger.to_dataframe()
        assert len(df) == 1
        assert df.iloc[0]["ticker"] == "BBRI"
        assert df.iloc[0]["exit_event"] == "TP1_HIT"

    def test_filter_by_segment(self):
        """filter_by_segment returns matching trades."""
        trade_a = TradeSimulation(
            ticker="BBRI",
            entry_date=pd.Timestamp("2023-06-01"),
            entry_price=4500.0,
            raw_entry_price=4495.0,
            stop_loss=4200.0,
            take_profit_1=4700.0,
            take_profit_2=4900.0,
            entry_setup="BREAKOUT",
        )
        trade_b = TradeSimulation(
            ticker="BBCA",
            entry_date=pd.Timestamp("2023-06-01"),
            entry_price=9000.0,
            raw_entry_price=8990.0,
            stop_loss=8500.0,
            take_profit_1=9500.0,
            take_profit_2=9800.0,
            entry_setup="REBOUND",
        )
        ledger = TradeLedger(trades=[trade_a, trade_b])

        breakout_trades = ledger.filter_by_segment("entry_setup", "BREAKOUT")
        assert len(breakout_trades) == 1
        assert breakout_trades[0].ticker == "BBRI"

        rebound_trades = ledger.filter_by_segment("entry_setup", "REBOUND")
        assert len(rebound_trades) == 1
        assert rebound_trades[0].ticker == "BBCA"

    def test_filter_by_segment_no_match(self):
        """filter_by_segment returns empty list when no trades match."""
        trade = TradeSimulation(
            ticker="BBRI",
            entry_date=pd.Timestamp("2023-06-01"),
            entry_price=4500.0,
            raw_entry_price=4495.0,
            stop_loss=4200.0,
            take_profit_1=4700.0,
            take_profit_2=4900.0,
            entry_setup="BREAKOUT",
        )
        ledger = TradeLedger(trades=[trade])
        result = ledger.filter_by_segment("entry_setup", "NONEXISTENT")
        assert result == []


# --- WalkForwardRunner Tests ---


class TestWalkForwardRunner:
    def _make_config(self, **overrides) -> BacktestConfig:
        """Create a BacktestConfig with sensible test defaults."""
        defaults = {
            "start_date": "2023-10-01",
            "end_date": "2023-10-31",
            "universe_tickers": ["BBRI"],
            "time_stop_days": 10,
            "warmup_days": 200,
            "cost_model": CostModelConfig(
                fee_buy_pct=0.0015,
                fee_sell_pct=0.0025,
                slippage_pct=0.001,
                snap_to_tick=False,  # disable tick-snap for test simplicity
            ),
        }
        defaults.update(overrides)
        return BacktestConfig(**defaults)

    def test_noop_signal_generator_produces_no_trades(self):
        """With no-op generator, runner returns empty ledger."""
        # Use 300 periods from Jan to ensure >200 data points by October
        price_data = {"BBRI": _make_price_df(start="2022-06-01", periods=400)}
        config = self._make_config()
        runner = WalkForwardRunner(config, price_data)
        ledger = runner.run()

        assert len(ledger.trades) == 0
        # All dates should have sufficient data (400 points from mid-2022)
        assert len(ledger.skipped) == 0

    def test_insufficient_data_is_recorded_in_skipped(self):
        """Tickers with insufficient data are skipped and recorded (Req 1.7)."""
        # Only 50 data points, warmup_days=200 → insufficient
        price_data = {"BBRI": _make_price_df(start="2023-09-01", periods=50)}
        config = self._make_config(warmup_days=200)
        runner = WalkForwardRunner(config, price_data)
        ledger = runner.run()

        assert len(ledger.trades) == 0
        assert len(ledger.skipped) > 0
        # All skips should be for BBRI with reason "insufficient_data"
        for skip in ledger.skipped:
            assert skip["ticker"] == "BBRI"
            assert skip["reason"] == "insufficient_data"

    def test_walk_forward_constraint_no_future_data(self):
        """Signal generator only sees data up to decision date T (Req 1.2)."""
        seen_dates_and_maxes: list[tuple[pd.Timestamp, pd.Timestamp]] = []

        def tracking_generator(
            df: pd.DataFrame, ticker: str, date: pd.Timestamp
        ) -> list[TradeSimulation]:
            seen_dates_and_maxes.append((date, df.index.max()))
            return []

        # Plenty of data to avoid warmup skipping
        price_data = {"BBRI": _make_price_df(start="2022-06-01", periods=400)}
        config = self._make_config()
        runner = WalkForwardRunner(config, price_data, signal_generator=tracking_generator)
        runner.run()

        # Every max date seen by the generator must be <= its decision_date
        assert len(seen_dates_and_maxes) > 0
        for decision_date, max_date in seen_dates_and_maxes:
            assert max_date <= decision_date, (
                f"Future data leak: generator saw data up to {max_date} "
                f"but decision_date is {decision_date}"
            )

    def test_signal_generator_produces_trades(self):
        """Runner creates TradeSimulation for each Entry_Signal (Req 1.1)."""
        price_data = {"BBRI": _make_price_df(start="2022-06-01", periods=400)}
        config = self._make_config()
        runner = WalkForwardRunner(
            config, price_data, signal_generator=_simple_signal_generator
        )
        ledger = runner.run()

        # Should have trades (one per trading day with sufficient data)
        assert len(ledger.trades) > 0
        # All trades should have exit info filled by simulator
        for trade in ledger.trades:
            assert trade.exit_event is not None
            assert trade.exit_date is not None
            assert trade.exit_price is not None

    def test_missing_ticker_data_is_skipped(self):
        """Ticker with no data in price_data is skipped."""
        price_data = {"BBRI": _make_price_df(start="2022-06-01", periods=400)}
        config = self._make_config(universe_tickers=["BBRI", "MISSING"])
        runner = WalkForwardRunner(config, price_data)
        ledger = runner.run()

        no_data_skips = [s for s in ledger.skipped if s["reason"] == "no_data"]
        assert len(no_data_skips) > 0
        assert all(s["ticker"] == "MISSING" for s in no_data_skips)

    def test_empty_price_data_returns_empty_ledger(self):
        """No price data → no trading days → empty ledger."""
        config = self._make_config()
        runner = WalkForwardRunner(config, {})
        ledger = runner.run()

        assert len(ledger.trades) == 0
        assert len(ledger.skipped) == 0

    def test_slice_up_to(self):
        """_slice_up_to returns data only up to and including the given date."""
        price_data = {"BBRI": _make_price_df(start="2023-01-01", periods=250)}
        config = self._make_config()
        runner = WalkForwardRunner(config, price_data)

        df = price_data["BBRI"]
        mid_date = df.index[100]
        sliced = runner._slice_up_to(df, mid_date)

        assert sliced.index.max() <= mid_date
        assert len(sliced) == 101  # 0-indexed, inclusive

    def test_has_sufficient_data(self):
        """_has_sufficient_data checks length against min_points."""
        price_data = {"BBRI": _make_price_df(start="2023-01-01", periods=250)}
        config = self._make_config()
        runner = WalkForwardRunner(config, price_data)

        df = price_data["BBRI"]
        assert runner._has_sufficient_data(df, min_points=200) is True
        assert runner._has_sufficient_data(df, min_points=300) is False
        assert runner._has_sufficient_data(df.iloc[:50], min_points=50) is True
        assert runner._has_sufficient_data(df.iloc[:49], min_points=50) is False
