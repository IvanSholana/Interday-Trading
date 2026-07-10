"""Single-position cash ledger with daily mark-to-market accounting."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class Position:
    ticker: str
    lots: int
    lot_size: int
    entry_price: float
    stop_price: float
    target_price: float
    opened_at: pd.Timestamp
    entry_cost: float = 0.0
    order_id: str = ""

    @property
    def shares(self) -> int:
        return self.lots * self.lot_size


@dataclass(frozen=True)
class LedgerSnapshot:
    timestamp: pd.Timestamp
    available_cash: float
    reserved_cash: float
    total_equity: float
    realized_pnl: float
    unrealized_pnl: float
    open_position: str | None
    pending_order: str | None
    gross_exposure: float
    current_drawdown: float
    peak_equity: float
    daily_loss: float
    open_trade_count: int


class PortfolioLedger:
    """Cash-safe BPJS ledger enforcing at most one open position."""

    def __init__(self, initial_capital: float, max_concurrent_positions: int = 1) -> None:
        if initial_capital <= 0:
            raise ValueError("initial_capital must be positive")
        if max_concurrent_positions != 1:
            raise ValueError("BPJS ledger supports exactly one concurrent position")
        self.initial_capital = float(initial_capital)
        self.available_cash = float(initial_capital)
        self.reserved_cash = 0.0
        self.realized_pnl = 0.0
        self.position: Position | None = None
        self.pending_order_id: str | None = None
        self._reserved_by_order: dict[str, float] = {}
        self.peak_equity = float(initial_capital)
        self._previous_equity = float(initial_capital)
        self.snapshots: list[LedgerSnapshot] = []
        self.closed_trades: list[dict[str, Any]] = []

    def reserve(self, order_id: str, cash_required: float) -> None:
        if self.position is not None or self.pending_order_id is not None:
            raise ValueError("SECOND_POSITION_NOT_ALLOWED")
        amount = float(cash_required)
        if amount <= 0 or amount > self.available_cash:
            raise ValueError("INSUFFICIENT_CASH")
        self.available_cash -= amount
        self.reserved_cash += amount
        self._reserved_by_order[order_id] = amount
        self.pending_order_id = order_id

    def cancel_reservation(self, order_id: str) -> None:
        amount = self._reserved_by_order.pop(order_id, 0.0)
        self.reserved_cash -= amount
        self.available_cash += amount
        if self.pending_order_id == order_id:
            self.pending_order_id = None

    def open_position(self, order_id: str, position: Position, actual_cash_required: float) -> None:
        if self.position is not None:
            raise ValueError("SECOND_POSITION_NOT_ALLOWED")
        reserved = self._reserved_by_order.get(order_id, 0.0)
        required = float(actual_cash_required)
        if required > reserved + self.available_cash:
            raise ValueError("INSUFFICIENT_CASH")
        self._reserved_by_order.pop(order_id, None)
        self.reserved_cash -= reserved
        delta = reserved - required
        self.available_cash += delta
        self.pending_order_id = None
        self.position = position

    def close_position(self, timestamp: pd.Timestamp, exit_price: float, exit_cost: float = 0.0, reason: str = "") -> float:
        if self.position is None:
            raise ValueError("NO_OPEN_POSITION")
        position = self.position
        proceeds = position.shares * float(exit_price) - float(exit_cost)
        invested = position.shares * position.entry_price + position.entry_cost
        pnl = proceeds - invested
        self.available_cash += proceeds
        self.realized_pnl += pnl
        self.closed_trades.append({
            "ticker": position.ticker,
            "opened_at": position.opened_at,
            "closed_at": pd.Timestamp(timestamp),
            "entry_price": position.entry_price,
            "exit_price": float(exit_price),
            "lots": position.lots,
            "realized_pnl": pnl,
            "reason": reason,
            "order_id": position.order_id,
        })
        self.position = None
        return pnl

    def mark_to_market(self, timestamp: pd.Timestamp, prices: dict[str, float]) -> LedgerSnapshot:
        market_value = 0.0
        unrealized = 0.0
        exposure = 0.0
        open_ticker = None
        if self.position is not None:
            open_ticker = self.position.ticker
            mark = float(prices.get(open_ticker, self.position.entry_price))
            market_value = self.position.shares * mark
            exposure = market_value
            unrealized = (mark - self.position.entry_price) * self.position.shares - self.position.entry_cost
        equity = self.available_cash + self.reserved_cash + market_value
        self.peak_equity = max(self.peak_equity, equity)
        drawdown = (equity / self.peak_equity - 1.0) if self.peak_equity > 0 else 0.0
        daily_loss = min(0.0, equity - self._previous_equity)
        snapshot = LedgerSnapshot(
            pd.Timestamp(timestamp), self.available_cash, self.reserved_cash, equity,
            self.realized_pnl, unrealized, open_ticker, self.pending_order_id,
            exposure, drawdown, self.peak_equity, daily_loss, int(self.position is not None),
        )
        self.snapshots.append(snapshot)
        self._previous_equity = equity
        return snapshot

    def snapshots_frame(self) -> pd.DataFrame:
        return pd.DataFrame([asdict(snapshot) for snapshot in self.snapshots])


__all__ = ["LedgerSnapshot", "PortfolioLedger", "Position"]
