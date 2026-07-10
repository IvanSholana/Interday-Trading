"""Concrete BPJS pipeline evaluator for cutoff-safe walk-forward runs."""

from __future__ import annotations

from dataclasses import replace
from typing import Callable, Any

import pandas as pd

from interday_liquidity_screener.constants import WatchlistStatus
from interday_liquidity_screener.execution import ExecutionOrder, OrderType
from interday_liquidity_screener.hybrid_config import HybridScreenerConfig
from interday_liquidity_screener.hybrid_screener import build_output_row
from interday_liquidity_screener.technical import build_latest_technical_row


SnapshotProvider = Callable[[str, pd.Timestamp], dict[str, Any] | None]


class BPJSPipelineEvaluator:
    """Recompute technical, optional snapshot overlay, ranking and trade plan."""

    def __init__(
        self,
        *,
        capital: float = 1_000_000,
        capital_profile: str = "capital_1m",
        hybrid_config: HybridScreenerConfig | None = None,
        broker_provider: SnapshotProvider | None = None,
        orderbook_provider: SnapshotProvider | None = None,
    ) -> None:
        config = hybrid_config or HybridScreenerConfig()
        profile = replace(config.capital_profiles[capital_profile], capital=float(capital), max_position_pct=1.0)
        profiles = dict(config.capital_profiles)
        profiles[capital_profile] = profile
        self.config = replace(config, capital_profiles=profiles)
        self.capital_profile = capital_profile
        self.broker_provider = broker_provider
        self.orderbook_provider = orderbook_provider

    @staticmethod
    def _overlay(provider: SnapshotProvider | None, ticker: str, decision_timestamp: pd.Timestamp) -> tuple[dict[str, Any], pd.Timestamp | None]:
        if provider is None:
            return {}, None
        payload = dict(provider(ticker, decision_timestamp) or {})
        raw_timestamp = payload.pop("snapshot_timestamp", None)
        snapshot_timestamp = pd.Timestamp(raw_timestamp) if raw_timestamp is not None else None
        if snapshot_timestamp is not None and snapshot_timestamp > decision_timestamp:
            raise ValueError("snapshot provider returned future data")
        return payload, snapshot_timestamp

    def __call__(self, snapshots: dict[str, pd.DataFrame], decision_timestamp: pd.Timestamp,
                 universe: list[str]) -> list[ExecutionOrder]:
        candidates: list[tuple[float, dict[str, Any], pd.Timestamp | None, pd.Timestamp | None]] = []
        for ticker in sorted(universe):
            history = snapshots.get(ticker)
            if history is None or history.empty:
                continue
            technical = build_latest_technical_row(
                {"ticker": ticker, "yahoo_ticker": f"{ticker}.JK", "liquidity_bucket": "HIGH_LIQUIDITY"},
                history,
            )
            if not technical.get("is_data_valid"):
                continue
            technical["symbol"] = ticker
            technical["date"] = decision_timestamp.date().isoformat()
            technical["market_regime"] = "UNKNOWN"
            technical["market_regime_score"] = 50.0
            technical["ihsg_trend_regime"] = "UNKNOWN"
            technical["market_regime_source"] = "NOT_PROVIDED"
            broker, broker_timestamp = self._overlay(self.broker_provider, ticker, decision_timestamp)
            orderbook, orderbook_timestamp = self._overlay(self.orderbook_provider, ticker, decision_timestamp)
            technical.update(broker)
            technical.update(orderbook)
            technical["decision_timestamp"] = decision_timestamp
            technical["data_cutoff_timestamp"] = decision_timestamp
            technical["broker_snapshot_timestamp"] = broker_timestamp
            technical["orderbook_snapshot_timestamp"] = orderbook_timestamp
            technical["raw_input_refs"] = f"ohlcv:{ticker}:rows={len(history)}:cutoff={decision_timestamp.isoformat()}"
            output = build_output_row(technical, "bpjs_live", self.capital_profile, self.config,
                                      ticker_history=None, blackout_events=None)
            output["entry_setup"] = technical.get("entry_setup")
            if output["final_status"] == WatchlistStatus.EXECUTION_READY and int(output.get("planned_lots") or 0) > 0:
                candidates.append((float(output["final_score"]), output, broker_timestamp, orderbook_timestamp))

        if not candidates:
            return []
        _, primary, broker_timestamp, orderbook_timestamp = max(candidates, key=lambda item: (item[0], item[1]["symbol"]))
        entry_setup = str(primary.get("entry_setup", "")).upper()
        order_type = OrderType.STOP_ENTRY if "BREAKOUT" in entry_setup else OrderType.LIMIT_BUY
        return [ExecutionOrder(
            order_id=f"BPJS-{decision_timestamp.strftime('%Y%m%d')}-{primary['symbol']}",
            ticker=str(primary["symbol"]), decision_timestamp=decision_timestamp,
            order_type=order_type, planned_entry=float(primary["entry_price"]),
            planned_stop=float(primary["stop_loss_price"]), planned_target=float(primary["tp1_price"]),
            planned_lots=int(primary["planned_lots"]), risk_budget_amount=float(primary["risk_budget_amount"]),
            max_risk_amount=float(self.config.capital_profiles[self.capital_profile].capital * self.config.risk.max_risk_per_trade_pct),
            lot_size=int(self.config.risk.lot_size), broker_snapshot_timestamp=broker_timestamp,
            orderbook_snapshot_timestamp=orderbook_timestamp,
            data_cutoff_timestamp=decision_timestamp,
            raw_input_refs=(
                f"ohlcv:{primary['symbol']}:rows={len(snapshots[str(primary['symbol'])])}:cutoff={decision_timestamp.isoformat()}",
            ),
            binding_constraint=str(primary.get("binding_constraint") or "UNKNOWN"),
            signal_reason=str(primary.get("explanation") or primary.get("strategy_reasons") or "bpjs_primary_rank"),
        )]


__all__ = ["BPJSPipelineEvaluator", "SnapshotProvider"]
