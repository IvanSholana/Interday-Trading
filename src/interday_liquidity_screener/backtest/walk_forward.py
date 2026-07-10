"""End-to-end orchestration boundary for point-in-time pipeline backtests."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Callable

import pandas as pd

from interday_liquidity_screener.backtest.config import BacktestConfig
from interday_liquidity_screener.backtest.cost_model import CostModel
from interday_liquidity_screener.execution import ExecutionFillModel, ExecutionOrder, FillModelConfig
from interday_liquidity_screener.experiments import (
    ExperimentArtifactWriter,
    ExperimentManifest,
    SignalTradeAuditRecord,
)
from interday_liquidity_screener.point_in_time import assert_point_in_time
from interday_liquidity_screener.portfolio import PortfolioLedger, Position


PipelineEvaluator = Callable[[dict[str, pd.DataFrame], pd.Timestamp, list[str]], list[ExecutionOrder]]
UniverseProvider = Callable[[pd.Timestamp], list[str]]


@dataclass
class WalkForwardResult:
    ledger: PortfolioLedger
    orders: list[ExecutionOrder] = field(default_factory=list)
    fills: list[object] = field(default_factory=list)
    rejected: list[dict[str, object]] = field(default_factory=list)
    manifest: ExperimentManifest | None = None
    audit_records: list[SignalTradeAuditRecord] = field(default_factory=list)

    def audit_frame(self) -> pd.DataFrame:
        return pd.DataFrame([record.to_dict() for record in self.audit_records])

    def write_artifacts(self, output_dir: str | None = None) -> dict[str, Path]:
        if self.manifest is None:
            raise ValueError("walk-forward result has no experiment manifest")
        resolved_output = output_dir or self.manifest.artifact_path
        if str(resolved_output) != self.manifest.artifact_path:
            self.manifest = replace(self.manifest, artifact_path=str(resolved_output))
        writer = ExperimentArtifactWriter(resolved_output)
        return writer.write(manifest=self.manifest, audit_records=self.audit_records,
                            equity_curve=self.ledger.snapshots_frame(), closed_trades=self.ledger.closed_trades)


class WalkForwardPipelineBacktester:
    """Recompute strategy decisions on cutoff-safe snapshots and account cash."""

    def __init__(
        self,
        config: BacktestConfig,
        price_data: dict[str, pd.DataFrame],
        pipeline_evaluator: PipelineEvaluator | None = None,
        universe_provider: UniverseProvider | None = None,
        fill_config: FillModelConfig | None = None,
        *,
        universe_version: str = "STATIC_UNIVERSE_SURVIVORSHIP_RISK",
        data_version: str = "UNKNOWN",
        code_commit_hash: str = "UNKNOWN",
    ) -> None:
        self.config = config
        self.price_data = {ticker: data.sort_index().copy() for ticker, data in price_data.items()}
        if pipeline_evaluator is None:
            from interday_liquidity_screener.backtest.bpjs_pipeline import BPJSPipelineEvaluator
            pipeline_evaluator = BPJSPipelineEvaluator(capital=config.initial_capital)
        self.pipeline_evaluator = pipeline_evaluator
        self.universe_provider = universe_provider
        self.cost_model = CostModel(config.cost_model)
        self.fill_model = ExecutionFillModel(self.cost_model, fill_config)
        self.universe_version = universe_version
        self.data_version = data_version
        self.code_commit_hash = code_commit_hash

    def _trading_days(self) -> pd.DatetimeIndex:
        dates: set[pd.Timestamp] = set()
        for data in self.price_data.values():
            dates.update(pd.Timestamp(value) for value in data.index)
        index = pd.DatetimeIndex(sorted(dates))
        return index[(index >= pd.Timestamp(self.config.start_date)) & (index <= pd.Timestamp(self.config.end_date))]

    def _bar(self, ticker: str, timestamp: pd.Timestamp) -> pd.Series | None:
        data = self.price_data.get(ticker)
        if data is None or timestamp not in data.index:
            return None
        row = data.loc[timestamp]
        return row.iloc[-1] if isinstance(row, pd.DataFrame) else row

    def _next_bar(self, ticker: str, timestamp: pd.Timestamp) -> tuple[pd.Timestamp, pd.Series] | None:
        data = self.price_data.get(ticker)
        if data is None:
            return None
        future = data[data.index > timestamp]
        if future.empty:
            return None
        return pd.Timestamp(future.index[0]), future.iloc[0]

    def run(self) -> WalkForwardResult:
        ledger = PortfolioLedger(self.config.initial_capital)
        result = WalkForwardResult(ledger=ledger)
        trading_days = self._trading_days()
        configuration = asdict(self.config)
        seed_manifest = ExperimentManifest.create(
            start_date=self.config.start_date, end_date=self.config.end_date,
            initial_capital=self.config.initial_capital, universe_version=self.universe_version,
            configuration=configuration, code_commit_hash=self.code_commit_hash,
            data_version=self.data_version, random_seed=self.config.random_seed,
            feature_version=self.config.feature_version, strategy_version=self.config.strategy_version,
            artifact_path=self.config.output_dir,
        )
        audit_by_order: dict[str, SignalTradeAuditRecord] = {}

        for decision_timestamp in trading_days:
            # Existing position exits before a new decision is considered.
            if ledger.position is not None:
                bar = self._bar(ledger.position.ticker, decision_timestamp)
                if bar is not None and decision_timestamp > ledger.position.opened_at:
                    stop_hit = float(bar["low"]) <= ledger.position.stop_price
                    target_hit = float(bar["high"]) >= ledger.position.target_price
                    holding_sessions = int(((trading_days > ledger.position.opened_at) & (trading_days <= decision_timestamp)).sum())
                    time_stop = holding_sessions >= self.config.time_stop_days
                    if stop_hit or target_hit or time_stop:
                        if stop_hit:  # conservative if both hit
                            raw_exit = min(float(bar["open"]), ledger.position.stop_price)
                            reason = "SL_HIT"
                        elif target_hit:
                            raw_exit = ledger.position.target_price
                            reason = "TP_HIT"
                        else:
                            raw_exit = float(bar["close"])
                            reason = "TIME_STOP"
                        actual_exit = self.cost_model.apply_exit_slippage(raw_exit)
                        exit_cost = actual_exit * ledger.position.shares * (
                            self.cost_model.config.fee_sell_pct + self.cost_model.config.sell_tax_pct
                        )
                        closing_order_id = ledger.position.order_id
                        pnl = ledger.close_position(decision_timestamp, actual_exit, exit_cost, reason)
                        audit = audit_by_order.get(closing_order_id)
                        if audit is not None:
                            audit.exit_timestamp = decision_timestamp
                            audit.actual_exit = actual_exit
                            audit.realized_pnl = pnl
                            audit.transition("POSITION_CLOSED", decision_timestamp, reason)

            marks = {}
            if ledger.position is not None:
                bar = self._bar(ledger.position.ticker, decision_timestamp)
                if bar is not None:
                    marks[ledger.position.ticker] = float(bar["close"])
            ledger.mark_to_market(decision_timestamp, marks)
            if ledger.position is not None or ledger.pending_order_id is not None:
                continue

            universe = self.universe_provider(decision_timestamp) if self.universe_provider else list(self.config.universe_tickers)
            snapshots: dict[str, pd.DataFrame] = {}
            for ticker in universe:
                data = self.price_data.get(ticker)
                if data is None:
                    continue
                snapshot = data[data.index <= decision_timestamp].copy()
                assert_point_in_time(snapshot, data_cutoff_timestamp=decision_timestamp, decision_timestamp=decision_timestamp)
                if len(snapshot) >= self.config.warmup_days:
                    snapshots[ticker] = snapshot

            orders = self.pipeline_evaluator(snapshots, decision_timestamp, universe)
            for order in orders[:1]:  # BPJS: one primary candidate only
                if pd.Timestamp(order.decision_timestamp) != decision_timestamp:
                    raise ValueError("order decision timestamp does not match backtest decision timestamp")
                for snapshot_timestamp in (order.broker_snapshot_timestamp, order.orderbook_snapshot_timestamp):
                    if snapshot_timestamp is not None and pd.Timestamp(snapshot_timestamp) > decision_timestamp:
                        raise ValueError("execution snapshot timestamp exceeds decision timestamp")
                result.orders.append(order)
                cutoff = pd.Timestamp(order.data_cutoff_timestamp or decision_timestamp)
                if cutoff > decision_timestamp:
                    raise ValueError("order data cutoff exceeds decision timestamp")
                raw_refs = order.raw_input_refs
                if not raw_refs and order.ticker in snapshots:
                    snapshot = snapshots[order.ticker]
                    raw_refs = (f"ohlcv:{order.ticker}:rows={len(snapshot)}:cutoff={cutoff.isoformat()}",)
                audit = SignalTradeAuditRecord(
                    order_id=order.order_id, ticker=order.ticker,
                    decision_timestamp=decision_timestamp, data_cutoff_timestamp=cutoff,
                    feature_version=self.config.feature_version, strategy_version=self.config.strategy_version,
                    config_hash=seed_manifest.config_hash, code_commit_hash=self.code_commit_hash,
                    universe_version=self.universe_version, raw_input_refs=raw_refs,
                    broker_snapshot_timestamp=order.broker_snapshot_timestamp,
                    orderbook_snapshot_timestamp=order.orderbook_snapshot_timestamp,
                    planned_entry=order.planned_entry, actual_entry=None,
                    planned_stop=order.planned_stop, actual_stop=None,
                    planned_target=order.planned_target, planned_lots=order.planned_lots,
                    actual_lots=0, binding_constraint=order.binding_constraint,
                    signal_reason=order.signal_reason or "pipeline_evaluator_selected_primary",
                )
                audit.transition("SIGNAL_CREATED", decision_timestamp)
                result.audit_records.append(audit)
                audit_by_order[order.order_id] = audit
                planned_cash = order.planned_position_value * (1 + self.cost_model.config.fee_buy_pct + self.cost_model.config.slippage_pct)
                try:
                    ledger.reserve(order.order_id, planned_cash)
                except ValueError as exc:
                    result.rejected.append({"order_id": order.order_id, "reason": str(exc)})
                    audit.transition("ORDER_REJECTED", decision_timestamp, str(exc))
                    continue
                audit.transition("ORDER_RESERVED", decision_timestamp)
                next_bar = self._next_bar(order.ticker, decision_timestamp)
                if next_bar is None:
                    ledger.cancel_reservation(order.order_id)
                    result.rejected.append({"order_id": order.order_id, "reason": "NO_FUTURE_BAR"})
                    audit.transition("ORDER_CANCELLED", decision_timestamp, "NO_FUTURE_BAR")
                    continue
                fill_timestamp, bar = next_bar
                fill = self.fill_model.simulate_entry(order, bar, fill_timestamp)
                result.fills.append(fill)
                audit.actual_entry = fill.actual_entry
                audit.actual_lots = fill.actual_lots
                audit.actual_stop = order.planned_stop if fill.actual_entry is not None else None
                if fill.actual_lots < 1 or fill.actual_entry is None:
                    ledger.cancel_reservation(order.order_id)
                    result.rejected.append({"order_id": order.order_id, "reason": fill.rejection_reason})
                    audit.transition("FILL_REJECTED", fill.fill_timestamp or decision_timestamp, fill.rejection_reason)
                    continue
                audit.transition(fill.status, fill.fill_timestamp or decision_timestamp)
                position = Position(order.ticker, fill.actual_lots, order.lot_size, fill.actual_entry,
                                    order.planned_stop, order.planned_target, fill_timestamp, fill.buy_fee, order.order_id)
                try:
                    ledger.open_position(order.order_id, position, fill.actual_cash_required)
                    audit.transition("POSITION_OPEN", fill_timestamp)
                except ValueError as exc:
                    ledger.cancel_reservation(order.order_id)
                    result.rejected.append({"order_id": order.order_id, "reason": str(exc)})
                    audit.transition("POSITION_REJECTED", fill_timestamp, str(exc))

        equity = ledger.snapshots_frame()
        final_equity = float(equity.iloc[-1]["total_equity"]) if not equity.empty else self.config.initial_capital
        max_drawdown = float(equity["current_drawdown"].min()) if not equity.empty else 0.0
        metrics = {
            "trading_day_count": len(trading_days),
            "signal_count": len(result.orders),
            "fill_count": sum(getattr(fill, "actual_lots", 0) > 0 for fill in result.fills),
            "closed_trade_count": len(ledger.closed_trades),
            "rejection_count": len(result.rejected),
            "final_equity": final_equity,
            "realized_pnl": ledger.realized_pnl,
            "maximum_drawdown": max_drawdown,
        }
        result.manifest = ExperimentManifest.create(
            start_date=self.config.start_date, end_date=self.config.end_date,
            initial_capital=self.config.initial_capital, universe_version=self.universe_version,
            configuration=configuration, code_commit_hash=self.code_commit_hash,
            data_version=self.data_version, random_seed=self.config.random_seed,
            feature_version=self.config.feature_version, strategy_version=self.config.strategy_version,
            artifact_path=self.config.output_dir, metrics=metrics,
        )
        return result


__all__ = ["PipelineEvaluator", "WalkForwardPipelineBacktester", "WalkForwardResult"]
