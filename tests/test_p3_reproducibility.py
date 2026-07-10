from __future__ import annotations

from dataclasses import replace
import json

import pandas as pd

from interday_liquidity_screener.backtest.config import BacktestConfig, CostModelConfig
from interday_liquidity_screener.backtest.walk_forward import WalkForwardPipelineBacktester
from interday_liquidity_screener.execution import ExecutionOrder, FillModelConfig, OrderType
from interday_liquidity_screener.hybrid_config import HybridScreenerConfig
from interday_liquidity_screener.hybrid_screener import build_output_row


REQUIRED_P3_FIELDS = {
    "decision_timestamp", "data_cutoff_timestamp", "feature_version", "strategy_version",
    "config_hash", "code_commit_hash", "universe_version", "raw_input_refs",
    "broker_snapshot_timestamp", "orderbook_snapshot_timestamp", "planned_entry",
    "actual_entry", "planned_stop", "actual_stop", "planned_target", "planned_lots",
    "actual_lots", "binding_constraint", "signal_reason", "rejection_reason", "status_transition",
}


def _hybrid_candidate() -> dict:
    return {
        "symbol": "TEST", "date": "2026-01-01", "close": 1_000,
        "avg_value_20d": 5_000_000_000, "avg_volume_20d": 5_000_000,
        "avg_frequency_20d": 1_000, "rvol": 1.5, "return_1d": 0.01,
        "return_3d": 0.02, "return_5d": 0.03, "return_20d": 0.05,
        "ma20": 980, "ma50": 950, "rsi": 60, "atr_pct": 0.02, "clv": 0.8,
        "entry_setup": "PULLBACK_CANDIDATE", "support_level": 950, "resistance_level": 1_020,
        "broker_activity_available": True, "accumulation_window_count": 4,
        "distribution_window_count": 0, "orderbook_available": True,
        "best_bid": 1_000, "best_offer": 1_000, "bid_depth_5": 500_000,
        "offer_depth_5": 200_000, "frequency_live": 500, "value_live": 1_000_000_000,
        "tradable": True, "broker_snapshot_timestamp": "2026-01-01T08:00:00",
        "orderbook_snapshot_timestamp": "2026-01-01T09:10:00",
        "raw_input_refs": "ohlcv:TEST:rows=200",
    }


def test_hybrid_signal_contains_complete_p3_metadata():
    config = HybridScreenerConfig()
    config = replace(config, adaptive_tp=replace(config.adaptive_tp, mode="fixed"))
    output = build_output_row(_hybrid_candidate(), "bpjs_live", "capital_1m", config)
    assert REQUIRED_P3_FIELDS.issubset(output)
    assert len(output["config_hash"]) == 64
    assert output["planned_entry"] == output["entry_price"]
    assert output["planned_lots"] > 0
    assert output["status_transition"].startswith("DISCOVERED->")


def _walk_result(reject: bool = False):
    dates = pd.bdate_range("2026-01-01", periods=5)
    data = pd.DataFrame({
        "open": [1_000] * 5, "high": [1_005, 1_005, 1_020, 1_005, 1_005],
        "low": [995] * 5, "close": [1_000] * 5, "volume": [100_000] * 5,
    }, index=dates)

    def evaluator(snapshots, decision_timestamp, universe):
        if decision_timestamp != dates[0]:
            return []
        return [ExecutionOrder(
            "O1", "TEST", decision_timestamp, OrderType.NEXT_OPEN, 1_000, 980, 1_010,
            1, 2_000, 1 if reject else 3_000, broker_snapshot_timestamp=decision_timestamp,
            orderbook_snapshot_timestamp=decision_timestamp, data_cutoff_timestamp=decision_timestamp,
            raw_input_refs=("ohlcv:TEST:rows=1",), binding_constraint="RISK",
            signal_reason="test_reproducible_signal",
        )]

    config = BacktestConfig(dates[0].date().isoformat(), dates[-1].date().isoformat(), ["TEST"],
                            warmup_days=1, time_stop_days=3, initial_capital=1_000_000,
                            feature_version="feature-v3", strategy_version="strategy-v3",
                            cost_model=CostModelConfig(slippage_pct=0, snap_to_tick=False))
    return WalkForwardPipelineBacktester(
        config, {"TEST": data}, evaluator, fill_config=FillModelConfig(max_volume_participation_pct=1),
        universe_version="IDX-TEST-v1", data_version="ohlcv-v1", code_commit_hash="abc123",
    ).run()


def test_walk_forward_audit_tracks_signal_to_closed_position():
    result = _walk_result()
    assert len(result.audit_records) == 1
    record = result.audit_records[0]
    assert REQUIRED_P3_FIELDS.issubset(record.to_dict())
    assert record.feature_version == "feature-v3"
    assert record.strategy_version == "strategy-v3"
    assert record.code_commit_hash == "abc123"
    assert record.universe_version == "IDX-TEST-v1"
    assert record.actual_entry == 1_000
    assert record.actual_lots == 1
    assert record.actual_exit == 1_010
    statuses = [transition["status"] for transition in record.status_transition]
    assert statuses == ["SIGNAL_CREATED", "ORDER_RESERVED", "FILLED", "POSITION_OPEN", "POSITION_CLOSED"]


def test_rejected_fill_preserves_actual_risk_evidence_and_transition():
    result = _walk_result(reject=True)
    record = result.audit_records[0]
    assert record.actual_entry == 1_000
    assert record.actual_lots == 0
    assert record.rejection_reason == "ACTUAL_FILL_RISK_EXCEEDS_MAX"
    assert record.status_transition[-1]["status"] == "FILL_REJECTED"


def test_manifest_contains_metrics_and_artifacts_are_stable(tmp_path):
    result = _walk_result()
    assert result.manifest.metrics["signal_count"] == 1
    assert result.manifest.metrics["closed_trade_count"] == 1
    paths = result.write_artifacts(str(tmp_path / "experiment"))
    assert set(paths) == {"manifest", "audit", "equity", "closed_trades"}
    for path in paths.values():
        assert path.exists()
    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    assert manifest["config_hash"] == result.manifest.config_hash
    assert manifest["artifact_path"] == str(tmp_path / "experiment")
    audit_line = paths["audit"].read_text(encoding="utf-8").strip()
    assert json.loads(audit_line)["order_id"] == "O1"


def test_config_hash_is_deterministic_across_runs():
    first = _walk_result()
    second = _walk_result()
    assert first.manifest.config_hash == second.manifest.config_hash
    assert first.audit_records[0].config_hash == second.audit_records[0].config_hash
