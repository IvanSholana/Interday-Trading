"""Complete, serializable signal-to-trade audit trail."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

import pandas as pd


@dataclass
class SignalTradeAuditRecord:
    order_id: str
    ticker: str
    decision_timestamp: pd.Timestamp
    data_cutoff_timestamp: pd.Timestamp
    feature_version: str
    strategy_version: str
    config_hash: str
    code_commit_hash: str
    universe_version: str
    raw_input_refs: tuple[str, ...]
    broker_snapshot_timestamp: pd.Timestamp | None
    orderbook_snapshot_timestamp: pd.Timestamp | None
    planned_entry: float
    actual_entry: float | None
    planned_stop: float
    actual_stop: float | None
    planned_target: float
    planned_lots: int
    actual_lots: int
    binding_constraint: str
    signal_reason: str
    rejection_reason: str | None = None
    exit_timestamp: pd.Timestamp | None = None
    actual_exit: float | None = None
    realized_pnl: float | None = None
    status_transition: list[dict[str, Any]] = field(default_factory=list)

    def transition(self, status: str, timestamp: pd.Timestamp, reason: str | None = None) -> None:
        self.status_transition.append({"status": status, "timestamp": pd.Timestamp(timestamp), "reason": reason})
        if status.endswith("REJECTED") or status.endswith("CANCELLED"):
            self.rejection_reason = reason

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


__all__ = ["SignalTradeAuditRecord"]
