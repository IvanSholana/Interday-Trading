"""Unit tests for CostModel class."""

import math

import pytest

from interday_liquidity_screener.backtest.config import CostModelConfig
from interday_liquidity_screener.backtest.cost_model import CostModel
from interday_liquidity_screener.trade_plan import get_idx_tick_size, round_price_to_tick


class TestCostModelInit:
    """Tests for CostModel initialization."""

    def test_default_config(self):
        model = CostModel()
        assert model.config.fee_buy_pct == 0.0015
        assert model.config.fee_sell_pct == 0.0025
        assert model.config.slippage_pct == 0.001
        assert model.config.snap_to_tick is True

    def test_custom_config(self):
        cfg = CostModelConfig(fee_buy_pct=0.002, fee_sell_pct=0.003, slippage_pct=0.005)
        model = CostModel(cfg)
        assert model.config.fee_buy_pct == 0.002
        assert model.config.fee_sell_pct == 0.003
        assert model.config.slippage_pct == 0.005


class TestApplyEntrySlippage:
    """Tests for apply_entry_slippage — Requirement 2.2 and 2.4."""

    def test_entry_slippage_adverse_direction(self):
        """Requirement 2.2: Entry slippage must make price MORE expensive."""
        model = CostModel()
        signal_price = 1000.0
        entry_price = model.apply_entry_slippage(signal_price)
        assert entry_price >= signal_price

    def test_entry_slippage_tick_valid(self):
        """Requirement 2.4: Result must be valid IDX tick-size multiple."""
        model = CostModel()
        signal_price = 1000.0
        entry_price = model.apply_entry_slippage(signal_price)
        tick = get_idx_tick_size(entry_price)
        assert math.isclose(entry_price % tick, 0.0, abs_tol=1e-9)

    def test_entry_slippage_ceil_rounding(self):
        """Entry slippage uses ceil rounding (worst case for buyer)."""
        # Price 1000 with 0.1% slippage = 1001.0
        # Tick for 500-2000 range is 5, ceil(1001/5)*5 = 1005
        cfg = CostModelConfig(slippage_pct=0.001)
        model = CostModel(cfg)
        result = model.apply_entry_slippage(1000.0)
        assert result == 1005.0

    def test_entry_slippage_exact_tick_no_change(self):
        """If slipped price is already on tick, ceil should not change it."""
        # Price 500 with slippage 0.01 = 505.0, tick for 500-2000 is 5
        # 505 / 5 = 101.0, ceil(101)*5 = 505
        cfg = CostModelConfig(slippage_pct=0.01)
        model = CostModel(cfg)
        result = model.apply_entry_slippage(500.0)
        assert result == 505.0

    def test_entry_slippage_low_price_range(self):
        """Test with price in 0-200 range (tick=1)."""
        cfg = CostModelConfig(slippage_pct=0.005)
        model = CostModel(cfg)
        # Price 100 * 1.005 = 100.5, tick=1, ceil(100.5)=101
        result = model.apply_entry_slippage(100.0)
        assert result == 101.0

    def test_entry_slippage_high_price_range(self):
        """Test with price in 5000+ range (tick=25)."""
        cfg = CostModelConfig(slippage_pct=0.001)
        model = CostModel(cfg)
        # Price 10000 * 1.001 = 10010, tick=25, ceil(10010/25)*25 = ceil(400.4)*25 = 401*25 = 10025
        result = model.apply_entry_slippage(10000.0)
        assert result == 10025.0

    def test_entry_slippage_no_snap(self):
        """When snap_to_tick=False, return raw slipped price."""
        cfg = CostModelConfig(slippage_pct=0.001, snap_to_tick=False)
        model = CostModel(cfg)
        result = model.apply_entry_slippage(1000.0)
        assert math.isclose(result, 1001.0, rel_tol=1e-9)


class TestApplyExitSlippage:
    """Tests for apply_exit_slippage — Requirement 2.2 and 2.4."""

    def test_exit_slippage_adverse_direction(self):
        """Requirement 2.2: Exit slippage must make price CHEAPER."""
        model = CostModel()
        signal_price = 1000.0
        exit_price = model.apply_exit_slippage(signal_price)
        assert exit_price <= signal_price

    def test_exit_slippage_tick_valid(self):
        """Requirement 2.4: Result must be valid IDX tick-size multiple."""
        model = CostModel()
        signal_price = 1000.0
        exit_price = model.apply_exit_slippage(signal_price)
        tick = get_idx_tick_size(exit_price)
        assert math.isclose(exit_price % tick, 0.0, abs_tol=1e-9)

    def test_exit_slippage_floor_rounding(self):
        """Exit slippage uses floor rounding (worst case for seller)."""
        # Price 1000 with 0.1% slippage = 999.0
        # Tick for 500-2000 range is 5, floor(999/5)*5 = floor(199.8)*5 = 199*5 = 995
        cfg = CostModelConfig(slippage_pct=0.001)
        model = CostModel(cfg)
        result = model.apply_exit_slippage(1000.0)
        assert result == 995.0

    def test_exit_slippage_exact_tick_no_change(self):
        """If slipped price is already on tick, floor should not change it."""
        # Price 1000 with slippage 0.01 = 990.0, tick for 500-2000 is 5
        # 990 / 5 = 198.0, floor(198)*5 = 990
        cfg = CostModelConfig(slippage_pct=0.01)
        model = CostModel(cfg)
        result = model.apply_exit_slippage(1000.0)
        assert result == 990.0

    def test_exit_slippage_low_price_range(self):
        """Test with price in 0-200 range (tick=1)."""
        cfg = CostModelConfig(slippage_pct=0.005)
        model = CostModel(cfg)
        # Price 100 * 0.995 = 99.5, tick=1, floor(99.5)=99
        result = model.apply_exit_slippage(100.0)
        assert result == 99.0

    def test_exit_slippage_high_price_range(self):
        """Test with price in 5000+ range (tick=25)."""
        cfg = CostModelConfig(slippage_pct=0.001)
        model = CostModel(cfg)
        # Price 10000 * 0.999 = 9990, tick=25, floor(9990/25)*25 = floor(399.6)*25 = 399*25 = 9975
        result = model.apply_exit_slippage(10000.0)
        assert result == 9975.0

    def test_exit_slippage_no_snap(self):
        """When snap_to_tick=False, return raw slipped price."""
        cfg = CostModelConfig(slippage_pct=0.001, snap_to_tick=False)
        model = CostModel(cfg)
        result = model.apply_exit_slippage(1000.0)
        assert math.isclose(result, 999.0, rel_tol=1e-9)


class TestCalculateNetReturn:
    """Tests for calculate_net_return — Requirement 2.1."""

    def test_net_return_formula(self):
        """Requirement 2.1: return_net = (exit/entry - 1) - fee_buy - fee_sell."""
        cfg = CostModelConfig(fee_buy_pct=0.0015, fee_sell_pct=0.0025)
        model = CostModel(cfg)
        # entry=1000, exit=1050 -> gross = 0.05
        # net = 0.05 - 0.0015 - 0.0025 = 0.046
        result = model.calculate_net_return(1000.0, 1050.0)
        assert math.isclose(result, 0.046, rel_tol=1e-9)

    def test_net_return_losing_trade(self):
        """Net return for a losing trade."""
        cfg = CostModelConfig(fee_buy_pct=0.0015, fee_sell_pct=0.0025)
        model = CostModel(cfg)
        # entry=1000, exit=950 -> gross = -0.05
        # net = -0.05 - 0.0015 - 0.0025 = -0.054
        result = model.calculate_net_return(1000.0, 950.0)
        assert math.isclose(result, -0.054, rel_tol=1e-9)

    def test_net_return_breakeven_gross(self):
        """When gross return is zero, net return equals negative fees."""
        cfg = CostModelConfig(fee_buy_pct=0.0015, fee_sell_pct=0.0025)
        model = CostModel(cfg)
        result = model.calculate_net_return(1000.0, 1000.0)
        assert math.isclose(result, -0.004, rel_tol=1e-9)

    def test_net_return_zero_entry_price(self):
        """Edge case: entry_price=0 returns 0.0."""
        model = CostModel()
        result = model.calculate_net_return(0.0, 1000.0)
        assert result == 0.0

    def test_net_return_custom_fees(self):
        """Test with custom fee configuration."""
        cfg = CostModelConfig(fee_buy_pct=0.003, fee_sell_pct=0.004)
        model = CostModel(cfg)
        # entry=500, exit=525 -> gross = 0.05
        # net = 0.05 - 0.003 - 0.004 = 0.043
        result = model.calculate_net_return(500.0, 525.0)
        assert math.isclose(result, 0.043, rel_tol=1e-9)


class TestSnapPriceToTick:
    """Tests for snap_price_to_tick — wraps round_price_to_tick."""

    def test_snap_nearest(self):
        model = CostModel()
        # 1003 in 500-2000 range, tick=5 -> nearest: round(1003/5)=round(200.6)=201 -> 1005
        assert model.snap_price_to_tick(1003.0, "nearest") == 1005.0

    def test_snap_ceil(self):
        model = CostModel()
        # 1001 in 500-2000 range, tick=5 -> ceil(1001/5)=ceil(200.2)=201 -> 1005
        assert model.snap_price_to_tick(1001.0, "ceil") == 1005.0

    def test_snap_floor(self):
        model = CostModel()
        # 1004 in 500-2000 range, tick=5 -> floor(1004/5)=floor(200.8)=200 -> 1000
        assert model.snap_price_to_tick(1004.0, "floor") == 1000.0

    def test_snap_already_on_tick(self):
        model = CostModel()
        assert model.snap_price_to_tick(1000.0, "nearest") == 1000.0
        assert model.snap_price_to_tick(1000.0, "ceil") == 1000.0
        assert model.snap_price_to_tick(1000.0, "floor") == 1000.0

    def test_snap_invalid_mode(self):
        model = CostModel()
        with pytest.raises(ValueError, match="Unsupported rounding mode"):
            model.snap_price_to_tick(1000.0, "invalid")
