"""Deterministic IDX order trigger, fill, and post-fill risk model."""

from __future__ import annotations

from dataclasses import dataclass
import math

import pandas as pd

from interday_liquidity_screener.backtest.cost_model import CostModel
from interday_liquidity_screener.execution.orders import ExecutionOrder, FillResult, OrderType


@dataclass(frozen=True)
class FillModelConfig:
    max_volume_participation_pct: float = 0.01
    allow_partial_fill: bool = True
    reject_near_ara_arb: bool = True


class ExecutionFillModel:
    def __init__(self, cost_model: CostModel, config: FillModelConfig | None = None) -> None:
        self.cost_model = cost_model
        self.config = config or FillModelConfig()

    def simulate_entry(self, order: ExecutionOrder, bar: pd.Series, timestamp: pd.Timestamp) -> FillResult:
        def rejected(reason: str) -> FillResult:
            return FillResult(order.order_id, order.ticker, "REJECTED", None, order.planned_entry, None,
                              order.planned_lots, 0, 0.0, 0.0, 0.0, 0.0, 0.0, reason)

        tradable = bar.get("tradable", True)
        if pd.isna(tradable):
            tradable = True
        if bool(bar.get("suspended", False)) or not bool(tradable):
            return rejected("SUSPENDED_OR_NOT_TRADABLE")
        if self.config.reject_near_ara_arb and (bool(bar.get("near_ara", False)) or bool(bar.get("near_arb", False))):
            return rejected("ARA_ARB_NON_FILL")

        bar_open = float(bar["open"])
        bar_high = float(bar["high"])
        bar_low = float(bar["low"])
        raw_fill: float | None = None
        if order.order_type == OrderType.NEXT_OPEN:
            raw_fill = bar_open
        elif order.order_type == OrderType.LIMIT_BUY:
            if bar_low > order.planned_entry:
                return rejected("LIMIT_NOT_TRIGGERED")
            raw_fill = min(bar_open, order.planned_entry)
        elif order.order_type == OrderType.STOP_ENTRY:
            if bar_high < order.planned_entry:
                return rejected("BREAKOUT_NOT_TRIGGERED")
            raw_fill = max(bar_open, order.planned_entry)

        actual_entry = self.cost_model.apply_entry_slippage(float(raw_fill))
        available_shares = math.floor(float(bar.get("volume", 0.0)) * self.config.max_volume_participation_pct)
        available_lots = available_shares // order.lot_size
        actual_lots = min(order.planned_lots, available_lots)
        if actual_lots < order.planned_lots and not self.config.allow_partial_fill:
            return rejected("INSUFFICIENT_LIQUIDITY_FOR_FULL_FILL")
        if actual_lots < 1:
            return rejected("NO_LIQUIDITY_CAPACITY")

        shares = actual_lots * order.lot_size
        actual_position_value = actual_entry * shares
        buy_fee = actual_position_value * self.cost_model.config.fee_buy_pct
        slippage_amount = max(0.0, actual_entry - float(raw_fill)) * shares
        actual_cash_required = actual_position_value + buy_fee
        actual_risk = max(0.0, actual_entry - order.planned_stop) * shares
        if actual_risk > order.max_risk_amount:
            return FillResult(order.order_id, order.ticker, "REJECTED", pd.Timestamp(timestamp),
                              order.planned_entry, actual_entry, order.planned_lots, 0,
                              actual_position_value, buy_fee, slippage_amount,
                              actual_cash_required, actual_risk, "ACTUAL_FILL_RISK_EXCEEDS_MAX")

        status = "FILLED" if actual_lots == order.planned_lots else "PARTIAL_FILL"
        return FillResult(order.order_id, order.ticker, status, pd.Timestamp(timestamp), order.planned_entry,
                          actual_entry, order.planned_lots, actual_lots, actual_position_value, buy_fee,
                          slippage_amount, actual_cash_required, actual_risk, None)


__all__ = ["ExecutionFillModel", "FillModelConfig"]
