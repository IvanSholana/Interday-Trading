"""Deterministic BPJS position sizing with post-lot risk reconciliation."""

from __future__ import annotations

from dataclasses import dataclass
import math


@dataclass(frozen=True)
class PositionSizingResult:
    risk_budget_amount: float
    risk_based_limit: float
    capital_based_limit: float
    liquidity_based_limit: float
    available_cash_limit: float
    binding_constraint: str
    planned_lots: int
    actual_position_value: float
    actual_cash_required: float
    actual_risk_amount: float
    actual_risk_pct: float
    capital_utilization_pct: float
    liquidity_participation_pct: float
    estimated_transaction_cost: float
    rejection_reason: str | None = None


def calculate_position_size(
    *,
    capital: float,
    available_cash: float,
    entry_price: float,
    stop_price: float,
    risk_per_trade_pct: float,
    max_risk_per_trade_pct: float,
    max_position_pct: float,
    avg_value_20d: float | None,
    liquidity_participation_limit_pct: float,
    liquidity_sizer_enabled: bool,
    buy_fee_pct: float,
    slippage_pct: float,
    lot_size: int = 100,
) -> PositionSizingResult:
    """Size from cash, capital, stop risk and optional liquidity constraints."""

    capital = max(float(capital), 0.0)
    available_cash = max(float(available_cash), 0.0)
    entry_price = float(entry_price)
    stop_price = float(stop_price)
    lot_size = int(lot_size)
    risk_budget = capital * max(float(risk_per_trade_pct), 0.0)
    capital_limit = capital * min(max(float(max_position_pct), 0.0), 1.0)
    cash_limit = available_cash / (1 + max(float(buy_fee_pct), 0.0) + max(float(slippage_pct), 0.0))

    stop_distance = entry_price - stop_price
    if entry_price <= 0 or lot_size <= 0 or stop_distance <= 0:
        return PositionSizingResult(
            risk_budget, 0.0, capital_limit, 0.0, cash_limit, "INVALID_STOP", 0,
            0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, "INVALID_STOP_DISTANCE",
        )

    risk_based_limit = risk_budget * entry_price / stop_distance
    if liquidity_sizer_enabled:
        liquidity_limit = max(float(avg_value_20d or 0.0), 0.0) * max(float(liquidity_participation_limit_pct), 0.0)
    else:
        liquidity_limit = math.inf

    limits = {
        "AVAILABLE_CASH": cash_limit,
        "CAPITAL": capital_limit,
        "RISK": risk_based_limit,
        "LIQUIDITY": liquidity_limit,
    }
    binding_constraint, final_limit = min(limits.items(), key=lambda item: item[1])
    lot_value = entry_price * lot_size
    lots = max(int(final_limit // lot_value), 0)
    position_value = lots * lot_value
    transaction_cost = position_value * (max(float(buy_fee_pct), 0.0) + max(float(slippage_pct), 0.0))
    cash_required = position_value + transaction_cost
    actual_risk = lots * stop_distance * lot_size
    actual_risk_pct = actual_risk / capital if capital > 0 else 0.0
    utilization = position_value / capital if capital > 0 else 0.0
    participation = position_value / float(avg_value_20d) if avg_value_20d and avg_value_20d > 0 else 0.0

    one_lot_risk = stop_distance * lot_size
    max_risk_amount = capital * max(float(max_risk_per_trade_pct), 0.0)
    rejection_reason = None
    if lot_value * (1 + buy_fee_pct + slippage_pct) > available_cash:
        rejection_reason = "INSUFFICIENT_CASH_FOR_ONE_LOT"
    elif one_lot_risk > max_risk_amount:
        rejection_reason = "ONE_LOT_RISK_EXCEEDS_MAX"
    elif lots < 1:
        rejection_reason = "POSITION_BELOW_ONE_LOT"
    if rejection_reason:
        lots = 0
        position_value = cash_required = actual_risk = actual_risk_pct = utilization = participation = transaction_cost = 0.0

    return PositionSizingResult(
        risk_budget, risk_based_limit, capital_limit, liquidity_limit, cash_limit,
        binding_constraint, lots, position_value, cash_required, actual_risk,
        actual_risk_pct, utilization, participation, transaction_cost, rejection_reason,
    )


__all__ = ["PositionSizingResult", "calculate_position_size"]
