from __future__ import annotations

import pandas as pd

from interday_liquidity_screener.analytics import audit_feature_correlations
from interday_liquidity_screener.bandarmology import calculate_broker_features, normalize_broker_flow, score_single_window
from interday_liquidity_screener.constants import WatchlistStatus
from interday_liquidity_screener.scoring import rank_bpjs_candidate
from interday_liquidity_screener.strategies import evaluate_strategy


def test_breakout_strategy_requires_trigger_and_allowed_regime():
    row = {"entry_setup": "BREAKOUT_CANDIDATE", "close": 1_000, "resistance_level": 1_010,
           "avg_value_20d": 5_000_000_000, "market_regime": "RISK_ON"}
    pending = evaluate_strategy(row)
    assert pending.definition.name == "breakout"
    assert pending.eligible is True
    assert pending.trigger_touched is False
    assert pending.status_cap == WatchlistStatus.READY_SOON
    triggered = evaluate_strategy({**row, "close": 1_015})
    assert triggered.status_cap == WatchlistStatus.EXECUTION_READY
    risk_off = evaluate_strategy({**row, "market_regime": "RISK_OFF"})
    assert risk_off.eligible is False


def test_pullback_rebound_and_momentum_have_distinct_triggers():
    pullback = evaluate_strategy({"entry_setup": "PULLBACK_CANDIDATE", "close": 1_000, "ma20": 990,
                                  "ma50": 950, "return_1d": 0.01})
    rebound = evaluate_strategy({"entry_setup": "REBOUND_CANDIDATE", "close": 1_000,
                                 "support_level": 950, "return_1d": 0.01, "clv": 0.7})
    momentum = evaluate_strategy({"technical_context": "UPTREND_CONTINUATION", "close": 1_000,
                                  "ma20": 980, "ma50": 950, "return_1d": 0.01, "rvol": 1.2})
    assert (pullback.definition.name, pullback.trigger_touched) == ("pullback", True)
    assert (rebound.definition.name, rebound.trigger_touched) == ("rebound", True)
    assert (momentum.definition.name, momentum.trigger_touched) == ("momentum_continuation", True)


def test_smart_money_and_compression_are_capped_until_technical_trigger():
    smart = evaluate_strategy({"accumulation_window_count": 4})
    compression = evaluate_strategy({"technical_context": "SIDEWAYS_COMPRESSION", "close": 990,
                                     "resistance_level": 1_000, "support_level": 950, "rvol": 0.8})
    assert smart.definition.name == "smart_money_discovery"
    assert smart.status_cap == WatchlistStatus.READY_SOON
    assert compression.definition.name == "sideways_compression"
    assert compression.status_cap == WatchlistStatus.READY_SOON


def test_strategy_contract_contains_all_execution_rules():
    evaluation = evaluate_strategy({"entry_setup": "BREAKOUT_CANDIDATE", "close": 1_010,
                                    "resistance_level": 1_000, "avg_value_20d": 1})
    definition = evaluation.definition
    assert definition.eligibility_gate
    assert definition.invalidation_rule
    assert definition.stop_rule
    assert definition.target_rule
    assert definition.time_stop_sessions in {2, 3}
    assert definition.required_features


def test_risk_feasibility_is_not_counted_as_alpha_or_rank():
    common = dict(technical=80, smart_money=70, price_extension=75, market_context=60,
                  liquidity=90, orderbook=80, net_profit_feasibility=85, data_quality=90)
    low_risk = rank_bpjs_candidate(**common, risk_feasibility=20)
    high_risk = rank_bpjs_candidate(**common, risk_feasibility=100)
    assert low_risk.alpha_score == high_risk.alpha_score
    assert low_risk.ranking_score == high_risk.ranking_score
    assert low_risk.risk_feasibility_score < high_risk.risk_feasibility_score


def test_validated_tp_probability_can_improve_ranking_without_being_fabricated():
    common = dict(technical=70, smart_money=60, price_extension=70, market_context=50,
                  liquidity=80, orderbook=75, net_profit_feasibility=80,
                  risk_feasibility=90, data_quality=90)
    unavailable = rank_bpjs_candidate(**common)
    high_probability = rank_bpjs_candidate(**common, estimated_tp_probability=0.8)
    assert unavailable.estimated_tp_probability is None
    assert high_probability.estimated_tp_probability == 0.8
    assert high_probability.ranking_score > unavailable.ranking_score


def test_broker_flow_score_does_not_double_count_technical_context():
    base = {"broker_activity_available": True, "broker_accdist": "Acc", "avg_accdist": "Acc",
            "top3_accdist": None, "top5_accdist": None, "avg_percent": 10, "avg_amount": 1,
            "detector_average_price": 1_000, "close": 1_000}
    weak = score_single_window({**base, "technical_context": "INVALID_DATA", "momentum_score": 0, "close_location": 0.1})
    strong = score_single_window({**base, "technical_context": "BREAKOUT_NEAR", "momentum_score": 100, "close_location": 1.0})
    assert weak == strong


def test_broker_dominance_is_bounded_and_low_coverage_is_ignored():
    frame = pd.DataFrame([
        {"ticker": "A", "side": "BUY", "broker_code": "X", "net_value": 200, "avg_price": 100},
        {"ticker": "A", "side": "SELL", "broker_code": "Y", "net_value": -100, "avg_price": 100},
    ])
    features = calculate_broker_features(frame).iloc[0]
    assert 0 <= features["top3_buyer_dominance"] <= 1
    assert 0 <= features["top3_seller_dominance"] <= 1
    high_coverage = score_single_window({"broker_activity_available": True, "top3_buyer_value": 200,
                                         "top3_seller_value": 100, "broker_flow_coverage_pct": 100})
    low_coverage = score_single_window({"broker_activity_available": True, "top3_buyer_value": 200,
                                        "top3_seller_value": 100, "broker_flow_coverage_pct": 20})
    assert high_coverage > low_coverage


def test_broker_flow_normalization_uses_scale_and_historical_distribution():
    normalized = normalize_broker_flow(
        200,
        avg_daily_value=2_000,
        traded_value=1_000,
        historical_net_flows=[0, 10, 20, 30, 40],
        free_float_market_cap=10_000,
    )
    assert normalized["broker_flow_to_avg_value"] == 0.1
    assert normalized["broker_flow_to_traded_value"] == 0.2
    assert normalized["broker_flow_to_free_float"] == 0.02
    assert normalized["broker_flow_zscore"] > 2


def test_feature_correlation_audit_flags_duplicate_information_only_with_enough_data():
    values = list(range(40))
    frame = pd.DataFrame({
        "liquidity_score": values,
        "technical_score": values,
        "smart_money_score": list(reversed(values)),
    })
    audit = audit_feature_correlations(frame, features=("liquidity_score", "technical_score", "smart_money_score"))
    pairs = {(left, right) for left, right, _ in audit.high_correlation_pairs}
    assert ("liquidity_score", "technical_score") in pairs
    assert audit.sample_size == 40

    too_small = audit_feature_correlations(frame.head(5), features=("liquidity_score", "technical_score"))
    assert too_small.high_correlation_pairs == ()
