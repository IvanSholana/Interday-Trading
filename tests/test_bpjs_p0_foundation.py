from __future__ import annotations

from dataclasses import replace

import pandas as pd
import interday_liquidity_screener.hybrid_screener as hybrid_module

from interday_liquidity_screener.adjusted_price import AdjustedPriceHandler
from interday_liquidity_screener.corporate_action_store import CorporateActionEvent, CorporateActionStore
from interday_liquidity_screener.hybrid_config import HybridScreenerConfig
from interday_liquidity_screener.hybrid_screener import (
    assess_data_quality,
    build_hybrid_watchlist,
    build_risk_plan,
    normalize_candidate_row,
)
from interday_liquidity_screener.point_in_time import assert_point_in_time
from interday_liquidity_screener.position_sizing import calculate_position_size
from interday_liquidity_screener.technical import calculate_technical_features


def _size(**overrides):
    params = dict(
        capital=1_000_000,
        available_cash=1_000_000,
        entry_price=1_000,
        stop_price=990,
        risk_per_trade_pct=0.01,
        max_risk_per_trade_pct=0.015,
        max_position_pct=1.0,
        avg_value_20d=5_000_000_000,
        liquidity_participation_limit_pct=0.10,
        liquidity_sizer_enabled=True,
        buy_fee_pct=0.0015,
        slippage_pct=0.001,
        lot_size=100,
    )
    params.update(overrides)
    return calculate_position_size(**params)


def test_bpjs_single_position_uses_available_capital():
    result = _size(liquidity_sizer_enabled=False)
    assert result.planned_lots == 9
    assert result.capital_utilization_pct == 0.9


def test_position_sizing_respects_risk_cap():
    result = _size(stop_price=950, liquidity_sizer_enabled=False)
    assert result.binding_constraint == "RISK"
    assert result.actual_risk_amount <= result.risk_budget_amount


def test_position_sizing_respects_liquidity_cap():
    result = _size(avg_value_20d=500_000, liquidity_participation_limit_pct=0.10)
    assert result.binding_constraint == "LIQUIDITY"
    assert result.planned_lots == 0


def test_one_lot_rejected_when_risk_exceeded():
    result = _size(capital=100_000, available_cash=100_000, entry_price=900, stop_price=800)
    assert result.rejection_reason == "ONE_LOT_RISK_EXCEEDS_MAX"


def test_zero_stop_distance_rejected():
    assert _size(stop_price=1_000).rejection_reason == "INVALID_STOP_DISTANCE"


def test_expected_net_return_after_fees():
    row = normalize_candidate_row({
        "symbol": "TEST", "close": 1_000, "best_offer": 1_000,
        "avg_value_20d": 5_000_000_000, "target_tp_pct": 0.02,
        "stop_loss_pct": 0.01, "spread_pct": 0.001,
    })
    config = replace(HybridScreenerConfig(), adaptive_tp=replace(HybridScreenerConfig().adaptive_tp, mode="fixed"))
    plan = build_risk_plan(row, config, "capital_1m", "bpjs_live")
    assert 0 < plan.expected_net_return_pct < 0.02
    assert plan.net_risk_reward_ratio == plan.risk_reward_ratio


def test_missing_optional_data_reduces_confidence():
    full = {"symbol": "A", "close": 100, "avg_value_20d": 1, "broker_activity_available": True,
            "sector_strength_score": 50, "orderbook_available": True}
    sparse = {"symbol": "A", "close": 100, "avg_value_20d": 1}
    assert assess_data_quality(sparse)[0] < assess_data_quality(full)[0]


def test_missing_optional_data_does_not_auto_reject():
    _, required, optional, _, _ = assess_data_quality({"symbol": "A", "close": 100, "avg_value_20d": 1})
    assert required == []
    assert optional


def test_missing_required_data_rejected_by_quality_contract():
    _, required, _, _, confidence = assess_data_quality({"symbol": "A"})
    assert set(required) == {"close", "avg_value_20d"}
    assert confidence == "LOW"


def test_future_rows_rejected():
    data = pd.DataFrame({"close": [1, 2]}, index=pd.to_datetime(["2026-01-01", "2026-01-03"]))
    try:
        assert_point_in_time(data, data_cutoff_timestamp=pd.Timestamp("2026-01-02"), decision_timestamp=pd.Timestamp("2026-01-02"))
    except ValueError as exc:
        assert "future rows" in str(exc)
    else:
        raise AssertionError("future row was accepted")


def test_shifted_rolling_reference():
    dates = pd.date_range("2026-01-01", periods=21, freq="D")
    data = pd.DataFrame({
        "open": [100.0] * 21, "high": [110.0] * 20 + [999.0],
        "low": [90.0] * 21, "close": [100.0] * 21,
        "volume": [10.0] * 20 + [1_000.0],
    }, index=dates)
    result = calculate_technical_features(data).iloc[-1]
    assert result["high_20d"] == 110.0
    assert result["avg_volume_20d"] == 10.0


def test_adjusted_price_split_and_raw_execution_price():
    data = pd.DataFrame({
        "open": [1_000, 500], "high": [1_010, 510], "low": [990, 490],
        "close": [1_000, 500], "volume": [100, 200], "adjusted_close": [500, 500],
    })
    adjusted = AdjustedPriceHandler.prepare_dual_price(data)
    assert adjusted["close"].pct_change().iloc[-1] == 0
    assert AdjustedPriceHandler.restore_raw_close(adjusted)["close"].tolist() == [1_000, 500]


def test_future_corporate_action_not_visible_and_as_of_timestamp():
    store = CorporateActionStore([
        CorporateActionEvent("TEST", "SPLIT", pd.Timestamp("2026-01-10"), ex_date=pd.Timestamp("2026-01-15")),
    ])
    assert store.as_of(pd.Timestamp("2026-01-09"), "TEST") == ()
    assert len(store.as_of(pd.Timestamp("2026-01-10"), "TEST")) == 1


def test_sideways_compression_is_not_execution_ready():
    row = {
        "symbol": "TEST", "close": 1_000, "avg_value_20d": 5_000_000_000,
        "avg_volume_20d": 5_000_000, "avg_frequency_20d": 1_000, "rvol": 1.5,
        "return_1d": 0.01, "return_3d": 0.02, "return_5d": 0.03,
        "ma20": 990, "ma50": 980, "rsi": 55, "clv": 0.7,
        "technical_context": "SIDEWAYS_COMPRESSION", "broker_activity_available": True,
        "accumulation_window_count": 4, "distribution_window_count": 0,
        "orderbook_available": True, "best_bid": 995, "best_offer": 1_000,
        "bid_depth_5": 200_000, "offer_depth_5": 100_000, "tradable": True,
    }
    result = build_hybrid_watchlist(pd.DataFrame([row]), mode="bpjs_live", capital_profile="capital_1m")
    assert result.iloc[0]["final_status"] in {"EARLY_WATCH", "READY_SOON"}
    assert result.iloc[0]["final_status"] != "EXECUTION_READY"


def test_liquidity_sizer_runtime_toggle(tmp_path, monkeypatch):
    captured = {}
    input_path = tmp_path / "input.csv"
    output_path = tmp_path / "output.csv"
    pd.DataFrame([{"symbol": "TEST"}]).to_csv(input_path, index=False)

    def fake_build(candidates, mode, capital_profile, config, date, max_candidates):
        captured["enabled"] = config.liquidity_sizer.enabled
        return pd.DataFrame([{"symbol": "TEST"}])

    monkeypatch.setattr(hybrid_module, "build_hybrid_watchlist", fake_build)
    hybrid_module.run_hybrid_screener(input_path, output_path, enable_liquidity_sizer=True)
    assert captured["enabled"] is True
