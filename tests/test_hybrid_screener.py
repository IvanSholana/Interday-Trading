from __future__ import annotations

import pandas as pd

from interday_liquidity_screener.backtest.config import CostModelConfig
from interday_liquidity_screener.backtest.cost_model import CostModel
from interday_liquidity_screener.backtest.simulator import TradeSimulation, TradeSimulator
from interday_liquidity_screener.hybrid_backtest import compare_hybrid_modes
from interday_liquidity_screener.hybrid_screener import (
    HybridScreenerConfig,
    build_hybrid_watchlist,
    build_risk_plan,
    normalize_candidate_row,
    score_liquidity,
    score_orderbook,
    score_price_extension,
    score_smart_money,
    score_technical,
)


def candidate(**overrides):
    row = {
        "symbol": "TEST",
        "name": "Test Emiten",
        "date": "2026-07-06",
        "close": 1000,
        "avg_value_20d": 5_000_000_000,
        "avg_volume_20d": 5_000_000,
        "avg_frequency_20d": 1000,
        "rvol": 1.6,
        "return_1d": 0.02,
        "return_3d": 0.04,
        "return_5d": 0.06,
        "return_20d": 0.08,
        "ma20": 950,
        "ma50": 900,
        "distance_ma20": 0.0526,
        "distance_ma50": 0.1111,
        "rsi": 60,
        "atr_pct": 0.025,
        "clv": 0.85,
        "support_level": 940,
        "resistance_level": 1040,
        "broker_activity_available": True,
        "broker_net_buy_1d": 150_000_000,
        "broker_net_buy_3d": 300_000_000,
        "broker_net_buy_5d": 500_000_000,
        "broker_net_buy_10d": 800_000_000,
        "broker_net_buy_20d": 1_000_000_000,
        "accumulation_window_count": 4,
        "distribution_window_count": 0,
        "top_buyer": "RX",
        "top_buyer_avg_price": 970,
        "top3_buyer_dominance": 0.72,
        "top_seller": "YP",
        "top_seller_avg_price": 990,
        "top3_seller_dominance": 0.25,
        "hhi_buyer": 0.30,
        "hhi_seller": 0.20,
        "close_vs_top_buyer_avg_pct": 0.03,
        "orderbook_available": True,
        "best_bid": 1000,
        "best_offer": 1005,
        "spread_pct": 0.00499,
        "bid_depth_5": 500_000,
        "offer_depth_5": 250_000,
        "bid_offer_ratio_5": 2.0,
        "offer_wall_ratio": 1.2,
        "frequency_live": 150,
        "value_live": 500_000_000,
        "tradable": True,
    }
    row.update(overrides)
    return row


def test_liquidity_score_high_and_low_cases():
    config = HybridScreenerConfig()
    assert score_liquidity(normalize_candidate_row(candidate()), config).score >= 85
    low = normalize_candidate_row(candidate(avg_value_20d=100_000_000, avg_volume_20d=50_000, avg_frequency_20d=20, rvol=0.2))
    assert score_liquidity(low, config).score < 40


def test_technical_score_tradeable_setup():
    result = score_technical(normalize_candidate_row(candidate()), HybridScreenerConfig())
    assert result.score >= 75


def test_smart_money_accumulation_and_distribution_cases():
    config = HybridScreenerConfig()
    acc = score_smart_money(normalize_candidate_row(candidate()), config)
    dist = score_smart_money(
        normalize_candidate_row(candidate(accumulation_window_count=0, distribution_window_count=4, broker_net_buy_1d=-1)),
        config,
    )
    assert acc.score > 70
    assert dist.score < 45
    assert "STRONG_DISTRIBUTION" in dist.flags


def test_smart_money_fake_accumulation_crossing_warning():
    result = score_smart_money(
        normalize_candidate_row(candidate(top_buyer="RX", top_seller="RX", top3_seller_dominance=0.65, hhi_buyer=0.5, hhi_seller=0.52)),
        HybridScreenerConfig(),
    )
    assert "FAKE_ACCUMULATION_RISK" in result.flags
    assert any("concentration" in warning for warning in result.warnings)


def test_price_extension_flags_danger_chasing():
    result = score_price_extension(
        normalize_candidate_row(candidate(return_3d=0.16, return_5d=0.20, distance_ma20=0.18)),
        HybridScreenerConfig(),
    )
    assert result.score < 50
    assert "DANGER_CHASING" in result.flags


def test_orderbook_supportive_and_weak_cases():
    config = HybridScreenerConfig()
    supportive = score_orderbook(normalize_candidate_row(candidate()), config, "bpjs_live")
    weak = score_orderbook(normalize_candidate_row(candidate(bid_offer_ratio_5=0.25, bid_depth_5=50_000, offer_depth_5=400_000)), config, "bpjs_live")
    assert supportive.score >= 70
    assert "ORDERBOOK_WEAK" in weak.flags


def test_risk_plan_positive_net_profit_after_fee():
    risk = build_risk_plan(normalize_candidate_row(candidate()), HybridScreenerConfig(), "capital_1m", "bpjs_live")
    assert risk.net_profit_after_fee > 0
    assert risk.net_profit_feasibility_score == 100


def test_risk_plan_negative_due_to_fee_slippage_and_tick_rounding():
    risk = build_risk_plan(
        normalize_candidate_row(candidate(target_tp_pct=0.004)),
        HybridScreenerConfig(),
        "capital_1m",
        "normal_execution",
    )
    assert risk.net_profit_after_fee <= 0
    assert "NET_PROFIT_NOT_WORTH_IT" in risk.skip_reasons


def test_bpjs_mode_cannot_be_execution_ready_without_orderbook():
    row = candidate(orderbook_available=False, best_bid=None, best_offer=None, spread_pct=None, bid_depth_5=None, offer_depth_5=None)
    result = build_hybrid_watchlist(pd.DataFrame([row]), mode="bpjs_live", capital_profile="capital_1m")
    assert result.iloc[0]["final_status"] == "NEED_ORDERBOOK"


def test_weekend_preparation_never_execution_ready():
    result = build_hybrid_watchlist(pd.DataFrame([candidate()]), mode="weekend_preparation", capital_profile="capital_1m")
    assert result.iloc[0]["final_status"] != "EXECUTION_READY"
    assert result.iloc[0]["final_status"] in {"EARLY_WATCH", "READY_SOON"}


def test_missing_broker_flow_and_sector_data_do_not_crash():
    row = candidate(broker_activity_available=False, accumulation_window_count=None, distribution_window_count=None)
    for key in ["broker_net_buy_1d", "broker_net_buy_3d", "broker_net_buy_5d", "broker_net_buy_10d", "broker_net_buy_20d"]:
        row[key] = None
    result = build_hybrid_watchlist(pd.DataFrame([row]), mode="normal_execution", capital_profile="capital_1m")
    assert not result.empty
    assert "broker_flow_missing_neutral_score" in result.iloc[0]["warnings"]
    assert "sector_strength_unavailable_neutral_score" in result.iloc[0]["warnings"]


def test_same_day_ambiguity_uses_worst_case_stop_loss():
    simulator = TradeSimulator(CostModel(CostModelConfig(slippage_pct=0, snap_to_tick=False)), time_stop_days=3)
    trade = TradeSimulation(
        ticker="TEST",
        entry_date=pd.Timestamp("2026-07-06"),
        entry_price=1000,
        raw_entry_price=1000,
        stop_loss=990,
        take_profit_1=1020,
        take_profit_2=1030,
    )
    bars = pd.DataFrame(
        [{"open": 1000, "high": 1030, "low": 980, "close": 1005, "volume": 1_000_000}],
        index=[pd.Timestamp("2026-07-07")],
    )
    result = simulator.simulate(trade, bars)
    assert result.exit_event == "SL_HIT"


def test_hybrid_backtest_compares_required_modes():
    candidates = pd.DataFrame([candidate()])
    bars = pd.DataFrame(
        [
            {"open": 1000, "high": 1010, "low": 995, "close": 1005, "volume": 1_000_000},
            {"open": 1005, "high": 1030, "low": 1000, "close": 1025, "volume": 1_000_000},
        ],
        index=[pd.Timestamp("2026-07-06"), pd.Timestamp("2026-07-07")],
    )
    result = compare_hybrid_modes(candidates, {"TEST": bars}, capital_profile="capital_1m")
    assert set(result["mode"]) == {"normal_execution", "smart_money_first", "hybrid_dual_flow"}
    assert "number_of_trades" in result.columns

