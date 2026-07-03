"""Unit tests for BacktestConfig and CostModelConfig dataclasses."""

import pytest

from interday_liquidity_screener.backtest.config import BacktestConfig, CostModelConfig


class TestCostModelConfig:
    """Tests for CostModelConfig frozen dataclass."""

    def test_default_values(self):
        cfg = CostModelConfig()
        assert cfg.fee_buy_pct == 0.0015
        assert cfg.fee_sell_pct == 0.0025
        assert cfg.slippage_pct == 0.001
        assert cfg.snap_to_tick is True

    def test_custom_values(self):
        cfg = CostModelConfig(fee_buy_pct=0.002, fee_sell_pct=0.003, slippage_pct=0.002, snap_to_tick=False)
        assert cfg.fee_buy_pct == 0.002
        assert cfg.fee_sell_pct == 0.003
        assert cfg.slippage_pct == 0.002
        assert cfg.snap_to_tick is False

    def test_frozen(self):
        cfg = CostModelConfig()
        with pytest.raises(Exception):
            cfg.fee_buy_pct = 0.01  # type: ignore[misc]


class TestBacktestConfig:
    """Tests for BacktestConfig frozen dataclass."""

    def test_valid_construction(self):
        cfg = BacktestConfig(
            start_date="2023-01-01",
            end_date="2023-12-31",
            universe_tickers=["BBRI", "BBCA"],
        )
        assert cfg.start_date == "2023-01-01"
        assert cfg.end_date == "2023-12-31"
        assert cfg.universe_tickers == ["BBRI", "BBCA"]
        assert cfg.time_stop_days == 10
        assert cfg.min_sample_size == 30
        assert cfg.warmup_days == 200
        assert cfg.output_dir == "data/output/backtest"
        assert isinstance(cfg.cost_model, CostModelConfig)

    def test_custom_time_stop_positive(self):
        """Requirement 1.8: positive time-stop value should be used."""
        cfg = BacktestConfig(
            start_date="2023-01-01",
            end_date="2023-06-30",
            universe_tickers=["BBRI"],
            time_stop_days=15,
        )
        assert cfg.time_stop_days == 15

    def test_time_stop_zero_fallback_to_default(self):
        """Requirement 1.9: zero time-stop treated as invalid, use default."""
        cfg = BacktestConfig(
            start_date="2023-01-01",
            end_date="2023-06-30",
            universe_tickers=["BBRI"],
            time_stop_days=0,
        )
        assert cfg.time_stop_days == 10

    def test_time_stop_negative_fallback_to_default(self):
        """Requirement 1.9: negative time-stop treated as invalid, use default."""
        cfg = BacktestConfig(
            start_date="2023-01-01",
            end_date="2023-06-30",
            universe_tickers=["BBRI"],
            time_stop_days=-5,
        )
        assert cfg.time_stop_days == 10

    def test_invalid_date_format(self):
        """Invalid date format should raise ValueError."""
        with pytest.raises(ValueError, match="start_date must be in YYYY-MM-DD format"):
            BacktestConfig(
                start_date="01-01-2023",
                end_date="2023-12-31",
                universe_tickers=["BBRI"],
            )

    def test_invalid_date_format_end(self):
        with pytest.raises(ValueError, match="end_date must be in YYYY-MM-DD format"):
            BacktestConfig(
                start_date="2023-01-01",
                end_date="2023/12/31",
                universe_tickers=["BBRI"],
            )

    def test_invalid_calendar_date(self):
        """Non-existent date (e.g. Feb 30) should raise ValueError."""
        with pytest.raises(ValueError, match="not a valid calendar date"):
            BacktestConfig(
                start_date="2023-02-30",
                end_date="2023-12-31",
                universe_tickers=["BBRI"],
            )

    def test_start_date_after_end_date(self):
        """start_date must be before end_date."""
        with pytest.raises(ValueError, match="start_date.*must be before end_date"):
            BacktestConfig(
                start_date="2023-12-31",
                end_date="2023-01-01",
                universe_tickers=["BBRI"],
            )

    def test_start_date_equals_end_date(self):
        """start_date equal to end_date should raise ValueError."""
        with pytest.raises(ValueError, match="start_date.*must be before end_date"):
            BacktestConfig(
                start_date="2023-06-15",
                end_date="2023-06-15",
                universe_tickers=["BBRI"],
            )

    def test_frozen(self):
        cfg = BacktestConfig(
            start_date="2023-01-01",
            end_date="2023-12-31",
            universe_tickers=["BBRI"],
        )
        with pytest.raises(Exception):
            cfg.time_stop_days = 20  # type: ignore[misc]

    def test_custom_cost_model(self):
        custom_cost = CostModelConfig(fee_buy_pct=0.002)
        cfg = BacktestConfig(
            start_date="2023-01-01",
            end_date="2023-12-31",
            universe_tickers=["BBRI"],
            cost_model=custom_cost,
        )
        assert cfg.cost_model.fee_buy_pct == 0.002
