from __future__ import annotations

import pandas as pd
import pytest

from interday_liquidity_screener.backtest.config import BacktestConfig, CostModelConfig
from interday_liquidity_screener.backtest.cost_model import CostModel
from interday_liquidity_screener.backtest.simulator import TradeSimulation, TradeSimulator
from interday_liquidity_screener.backtest.walk_forward import WalkForwardPipelineBacktester
from interday_liquidity_screener.execution import ExecutionFillModel, ExecutionOrder, FillModelConfig, OrderType
from interday_liquidity_screener.portfolio import PortfolioLedger, Position


def _bar(**overrides) -> pd.Series:
    values = {"open": 1_000.0, "high": 1_020.0, "low": 990.0, "close": 1_005.0,
              "volume": 100_000, "tradable": True, "suspended": False,
              "near_ara": False, "near_arb": False}
    values.update(overrides)
    return pd.Series(values)


def _order(**overrides) -> ExecutionOrder:
    values = dict(order_id="O1", ticker="TEST", decision_timestamp=pd.Timestamp("2026-01-01"),
                  order_type=OrderType.NEXT_OPEN, planned_entry=1_000.0, planned_stop=980.0,
                  planned_target=1_040.0, planned_lots=2, risk_budget_amount=4_000.0,
                  max_risk_amount=5_000.0)
    values.update(overrides)
    return ExecutionOrder(**values)


def test_insufficient_cash_rejected():
    ledger = PortfolioLedger(100_000)
    with pytest.raises(ValueError, match="INSUFFICIENT_CASH"):
        ledger.reserve("O1", 100_001)


def test_second_position_rejected_when_one_is_open():
    ledger = PortfolioLedger(1_000_000)
    ledger.reserve("O1", 100_000)
    ledger.open_position("O1", Position("A", 1, 100, 990, 950, 1_050, pd.Timestamp("2026-01-01")), 99_000)
    with pytest.raises(ValueError, match="SECOND_POSITION_NOT_ALLOWED"):
        ledger.reserve("O2", 100_000)


def test_equity_curve_uses_mark_to_market():
    ledger = PortfolioLedger(1_000_000)
    ledger.reserve("O1", 100_000)
    ledger.open_position("O1", Position("A", 1, 100, 1_000, 950, 1_050, pd.Timestamp("2026-01-01")), 100_000)
    snapshot = ledger.mark_to_market(pd.Timestamp("2026-01-02"), {"A": 900})
    assert snapshot.unrealized_pnl == -10_000
    assert snapshot.total_equity == 990_000
    assert snapshot.current_drawdown == pytest.approx(-0.01)


def test_gap_through_stop_fill():
    simulator = TradeSimulator(CostModel(CostModelConfig(slippage_pct=0, snap_to_tick=False)), time_stop_days=3)
    trade = TradeSimulation("TEST", pd.Timestamp("2026-01-01"), 1_000, 1_000, 950, 1_050, 1_080)
    result = simulator.simulate(trade, pd.DataFrame([{"open": 900, "high": 920, "low": 880, "close": 910}],
                                                    index=[pd.Timestamp("2026-01-02")]))
    assert result.exit_event == "SL_HIT"
    assert result.exit_price == 900


def test_same_bar_tp_sl_conservative():
    simulator = TradeSimulator(CostModel(CostModelConfig(slippage_pct=0, snap_to_tick=False)), time_stop_days=3)
    trade = TradeSimulation("TEST", pd.Timestamp("2026-01-01"), 1_000, 1_000, 950, 1_050, 1_080)
    result = simulator.simulate(trade, pd.DataFrame([{"open": 1_000, "high": 1_060, "low": 940, "close": 1_010}],
                                                    index=[pd.Timestamp("2026-01-02")]))
    assert result.exit_event == "SL_HIT"


def test_limit_entry_not_triggered():
    model = ExecutionFillModel(CostModel(CostModelConfig(slippage_pct=0, snap_to_tick=False)))
    fill = model.simulate_entry(_order(order_type=OrderType.LIMIT_BUY, planned_entry=980), _bar(low=990), pd.Timestamp("2026-01-02"))
    assert fill.actual_lots == 0
    assert fill.rejection_reason == "LIMIT_NOT_TRIGGERED"


def test_breakout_entry_triggered():
    model = ExecutionFillModel(CostModel(CostModelConfig(slippage_pct=0, snap_to_tick=False)))
    fill = model.simulate_entry(_order(order_type=OrderType.STOP_ENTRY, planned_entry=1_010, max_risk_amount=10_000), _bar(high=1_020), pd.Timestamp("2026-01-02"))
    assert fill.status == "FILLED"
    assert fill.actual_entry == 1_010


def test_actual_fill_recalculates_risk():
    model = ExecutionFillModel(CostModel(CostModelConfig(slippage_pct=0.02, snap_to_tick=False)))
    fill = model.simulate_entry(_order(max_risk_amount=3_000), _bar(), pd.Timestamp("2026-01-02"))
    assert fill.actual_lots == 0
    assert fill.rejection_reason == "ACTUAL_FILL_RISK_EXCEEDS_MAX"
    assert fill.actual_entry == 1_020
    assert fill.actual_risk_amount == 8_000


def test_ara_arb_non_fill():
    model = ExecutionFillModel(CostModel())
    fill = model.simulate_entry(_order(), _bar(near_ara=True), pd.Timestamp("2026-01-02"))
    assert fill.rejection_reason == "ARA_ARB_NON_FILL"


def test_partial_fill():
    model = ExecutionFillModel(CostModel(CostModelConfig(slippage_pct=0, snap_to_tick=False)),
                               FillModelConfig(max_volume_participation_pct=0.01, allow_partial_fill=True))
    fill = model.simulate_entry(_order(planned_lots=10, max_risk_amount=20_000), _bar(volume=50_000), pd.Timestamp("2026-01-02"))
    assert fill.status == "PARTIAL_FILL"
    assert fill.actual_lots == 5


def test_fee_tax_spread_and_slippage():
    model = CostModel(CostModelConfig(fee_buy_pct=0.0015, fee_sell_pct=0.0015, sell_tax_pct=0.001,
                                      estimated_spread_pct=0.002, slippage_pct=0.001, snap_to_tick=False))
    costs = model.calculate_cost_breakdown(1_000, 1_020, 100)
    assert costs == {"buy_fee": 150.0, "sell_fee": 153.0, "sell_tax": 102.0,
                     "estimated_spread_cost": 200.0, "estimated_slippage_cost": 202.0}


def _prices(extra_future: bool = False) -> dict[str, pd.DataFrame]:
    dates = pd.bdate_range("2026-01-01", periods=8 + int(extra_future))
    frame = pd.DataFrame({"open": [1_000.0] * len(dates), "high": [1_010.0] * len(dates),
                          "low": [990.0] * len(dates), "close": [1_000.0] * len(dates),
                          "volume": [100_000] * len(dates)}, index=dates)
    return {"TEST": frame}


def _evaluator(snapshots, decision_timestamp, universe):
    if "TEST" not in snapshots:
        return []
    return [_order(order_id=f"O-{decision_timestamp.date()}", decision_timestamp=decision_timestamp,
                   planned_lots=1, planned_stop=950, planned_target=1_100,
                   orderbook_snapshot_timestamp=decision_timestamp)]


def _walk(extra_future: bool = False):
    config = BacktestConfig("2026-01-01", "2026-01-09", ["TEST"], warmup_days=2, time_stop_days=2,
                            initial_capital=1_000_000,
                            cost_model=CostModelConfig(slippage_pct=0, snap_to_tick=False))
    return WalkForwardPipelineBacktester(config, _prices(extra_future), _evaluator,
                                         fill_config=FillModelConfig(max_volume_participation_pct=1)).run()


def test_walk_forward_deterministic():
    first = _walk()
    second = _walk()
    assert first.ledger.snapshots_frame().to_dict("records") == second.ledger.snapshots_frame().to_dict("records")
    assert first.manifest.config_hash == second.manifest.config_hash


def test_signal_unchanged_by_future_data():
    base = _walk(False)
    extended = _walk(True)
    assert [order.order_id for order in base.orders] == [order.order_id for order in extended.orders]


def test_orderbook_snapshot_timestamp():
    def future_snapshot(snapshots, decision_timestamp, universe):
        return [_order(decision_timestamp=decision_timestamp,
                       orderbook_snapshot_timestamp=decision_timestamp + pd.Timedelta(days=1))]
    config = BacktestConfig("2026-01-01", "2026-01-09", ["TEST"], warmup_days=1)
    with pytest.raises(ValueError, match="snapshot timestamp"):
        WalkForwardPipelineBacktester(config, _prices(), future_snapshot).run()
