"""Typed execution-order contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import pandas as pd


class OrderType(str, Enum):
    NEXT_OPEN = "NEXT_OPEN"
    LIMIT_BUY = "LIMIT_BUY"
    STOP_ENTRY = "STOP_ENTRY"


@dataclass(frozen=True)
class ExecutionOrder:
    order_id: str
    ticker: str
    decision_timestamp: pd.Timestamp
    order_type: OrderType
    planned_entry: float
    planned_stop: float
    planned_target: float
    planned_lots: int
    risk_budget_amount: float
    max_risk_amount: float
    lot_size: int = 100
    expires_after_sessions: int = 1
    broker_snapshot_timestamp: pd.Timestamp | None = None
    orderbook_snapshot_timestamp: pd.Timestamp | None = None
    data_cutoff_timestamp: pd.Timestamp | None = None
    raw_input_refs: tuple[str, ...] = ()
    binding_constraint: str = "UNKNOWN"
    signal_reason: str = ""

    @property
    def planned_position_value(self) -> float:
        return self.planned_entry * self.planned_lots * self.lot_size


@dataclass(frozen=True)
class FillResult:
    order_id: str
    ticker: str
    status: str
    fill_timestamp: pd.Timestamp | None
    planned_entry: float
    actual_entry: float | None
    planned_lots: int
    actual_lots: int
    actual_position_value: float
    buy_fee: float
    slippage_amount: float
    actual_cash_required: float
    actual_risk_amount: float
    rejection_reason: str | None = None


__all__ = ["ExecutionOrder", "FillResult", "OrderType"]
