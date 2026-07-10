from __future__ import annotations

from dataclasses import replace

import numpy as np
import pandas as pd

from interday_liquidity_screener.backtest.bpjs_pipeline import BPJSPipelineEvaluator
from interday_liquidity_screener.backtest.config import BacktestConfig, CostModelConfig
from interday_liquidity_screener.backtest.walk_forward import WalkForwardPipelineBacktester
from interday_liquidity_screener.execution import FillModelConfig
from interday_liquidity_screener.corporate_action_store import CorporateActionEvent, CorporateActionStore
from interday_liquidity_screener.hybrid_config import HybridScreenerConfig
from interday_liquidity_screener.hybrid_screener import build_output_row
from interday_liquidity_screener.market_data_cache import MarketDataCache
from interday_liquidity_screener.point_in_time_market_store import PointInTimeMarketStore
from interday_liquidity_screener.universe_history_store import UniverseHistoryStore


def test_persistent_corporate_action_as_of(tmp_path):
    store = CorporateActionStore(db_path=tmp_path / "events.sqlite")
    store.add(CorporateActionEvent("TEST", "SPLIT", pd.Timestamp("2026-01-10"),
                                   ex_date=pd.Timestamp("2026-01-15"), source="IDX"))
    assert store.as_of(pd.Timestamp("2026-01-09"), "TEST") == ()
    visible = store.as_of(pd.Timestamp("2026-01-10"), "TEST")
    assert len(visible) == 1
    assert visible[0].source == "IDX"


def test_universe_history_as_of_boundaries(tmp_path):
    store = UniverseHistoryStore(tmp_path / "universe.sqlite")
    store.add_membership("IDX80", "AAA", pd.Timestamp("2026-01-01"), pd.Timestamp("2026-06-30"), "IDX")
    store.add_membership("IDX80", "BBB", pd.Timestamp("2026-07-01"), None, "IDX")
    assert store.members_as_of("IDX80", pd.Timestamp("2026-06-30")) == ["AAA"]
    assert store.members_as_of("IDX80", pd.Timestamp("2026-07-01")) == ["BBB"]


def test_point_in_time_market_store_cuts_future_rows(tmp_path):
    db = tmp_path / "market.sqlite"
    dates = pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-05"])
    data = pd.DataFrame({"open": [100, 101, 102], "high": [101, 102, 103],
                         "low": [99, 100, 101], "close": [100, 101, 102],
                         "volume": [1_000] * 3}, index=dates)
    MarketDataCache(db).save_ohlcv("TEST", data)
    snapshot = PointInTimeMarketStore(db).snapshot("TEST", pd.Timestamp("2026-01-02"), pd.Timestamp("2026-01-02"))
    assert snapshot.index.max() == pd.Timestamp("2026-01-02")
    assert len(snapshot) == 2


def _candidate() -> dict:
    return {
        "symbol": "TEST", "date": "2026-01-13", "close": 1_000,
        "avg_value_20d": 5_000_000_000, "avg_volume_20d": 5_000_000,
        "avg_frequency_20d": 1_000, "rvol": 1.5, "return_1d": 0.01,
        "return_3d": 0.03, "return_5d": 0.04, "return_20d": 0.08,
        "ma20": 970, "ma50": 930, "rsi": 60, "atr_pct": 0.02, "clv": 0.8,
        "low_20d": 900, "high_20d": 995, "broker_activity_available": True,
        "accumulation_window_count": 4, "distribution_window_count": 0,
        "top3_buyer_dominance": 0.7, "orderbook_available": True,
        "best_bid": 1_000, "best_offer": 1_005, "bid_depth_5": 500_000,
        "offer_depth_5": 250_000, "frequency_live": 500, "value_live": 1_000_000_000,
        "tradable": True,
    }


def test_hybrid_blackout_uses_only_announced_events(tmp_path):
    store = CorporateActionStore(db_path=tmp_path / "events.sqlite")
    store.add(CorporateActionEvent("TEST", "SPLIT", pd.Timestamp("2026-01-14"),
                                   ex_date=pd.Timestamp("2026-01-15"), source="IDX"))
    output = build_output_row(_candidate(), "bpjs_live", "capital_1m", HybridScreenerConfig(),
                              corporate_action_store=store)
    assert "SKIP_BLACKOUT_WINDOW" not in output["skip_reasons"]

    known_store = CorporateActionStore(db_path=tmp_path / "known.sqlite")
    known_store.add(CorporateActionEvent("TEST", "SPLIT", pd.Timestamp("2026-01-10"),
                                         ex_date=pd.Timestamp("2026-01-15"), source="IDX"))
    known = build_output_row(_candidate(), "bpjs_live", "capital_1m", HybridScreenerConfig(),
                             corporate_action_store=known_store)
    assert "SKIP_BLACKOUT_WINDOW" in known["skip_reasons"]


def _history() -> pd.DataFrame:
    dates = pd.bdate_range("2025-01-01", periods=140)
    close = np.linspace(800.0, 1_000.0, len(dates))
    return pd.DataFrame({"open": close - 2, "high": close + 8, "low": close - 8,
                         "close": close, "volume": [5_000_000] * len(dates)}, index=dates)


def test_bpjs_pipeline_evaluator_recomputes_order_from_asof_snapshot():
    decision = _history().index[-1]

    def broker(ticker, timestamp):
        return {"snapshot_timestamp": timestamp, "broker_activity_available": True,
                "accumulation_window_count": 4, "distribution_window_count": 0,
                "top3_buyer_dominance": 0.75}

    def orderbook(ticker, timestamp):
        close = float(_history().loc[timestamp, "close"])
        return {"snapshot_timestamp": timestamp, "orderbook_available": True,
                "best_bid": close, "best_offer": close, "bid_depth_5": 500_000,
                "offer_depth_5": 200_000, "frequency_live": 500,
                "value_live": 1_000_000_000, "tradable": True}

    config = HybridScreenerConfig()
    config = replace(config, adaptive_tp=replace(config.adaptive_tp, mode="fixed"))
    evaluator = BPJSPipelineEvaluator(hybrid_config=config, broker_provider=broker, orderbook_provider=orderbook)
    orders = evaluator({"TEST": _history()}, decision, ["TEST"])
    assert len(orders) == 1
    assert orders[0].ticker == "TEST"
    assert orders[0].decision_timestamp == decision
    assert orders[0].orderbook_snapshot_timestamp == decision


def test_bpjs_pipeline_evaluator_rejects_future_provider_snapshot():
    decision = _history().index[-1]

    def future_broker(ticker, timestamp):
        return {"snapshot_timestamp": timestamp + pd.Timedelta(days=1)}

    evaluator = BPJSPipelineEvaluator(broker_provider=future_broker)
    try:
        evaluator({"TEST": _history()}, decision, ["TEST"])
    except ValueError as exc:
        assert "future data" in str(exc)
    else:
        raise AssertionError("future provider snapshot was accepted")


def test_walk_forward_runs_concrete_bpjs_pipeline_end_to_end():
    history = _history()
    start, end = history.index[-2], history.index[-1]

    def broker(ticker, timestamp):
        return {"snapshot_timestamp": timestamp, "broker_activity_available": True,
                "accumulation_window_count": 4, "distribution_window_count": 0,
                "top3_buyer_dominance": 0.75}

    def orderbook(ticker, timestamp):
        close = float(history.loc[timestamp, "close"])
        return {"snapshot_timestamp": timestamp, "orderbook_available": True,
                "best_bid": close, "best_offer": close, "bid_depth_5": 500_000,
                "offer_depth_5": 200_000, "frequency_live": 500,
                "value_live": 1_000_000_000, "tradable": True}

    hybrid = HybridScreenerConfig()
    hybrid = replace(hybrid, adaptive_tp=replace(hybrid.adaptive_tp, mode="fixed"))
    evaluator = BPJSPipelineEvaluator(hybrid_config=hybrid, broker_provider=broker, orderbook_provider=orderbook)
    config = BacktestConfig(start.date().isoformat(), end.date().isoformat(), ["TEST"], warmup_days=120,
                            initial_capital=1_000_000,
                            cost_model=CostModelConfig(slippage_pct=0, snap_to_tick=False))
    result = WalkForwardPipelineBacktester(config, {"TEST": history}, evaluator,
                                            fill_config=FillModelConfig(max_volume_participation_pct=1)).run()
    assert len(result.orders) == 1
    assert len(result.fills) == 1
    assert result.fills[0].actual_lots > 0
    assert result.ledger.position is not None
