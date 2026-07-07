from __future__ import annotations

import pandas as pd

from interday_liquidity_screener.trade_plan import (
    TradePlanConfig,
    build_trade_plan_row,
    can_afford_minimum_lot,
    calculate_theoretical_position_size,
    get_idx_tick_size,
    load_stage_2_candidates,
    round_price_to_tick,
    run_stage_4_trade_plan,
)


def stage2_row(**overrides) -> dict:
    row = {
        "ticker": "TEST",
        "yahoo_ticker": "TEST.JK",
        "last_date": "2026-07-02",
        "close": 1000.0,
        "entry_setup": "BREAKOUT_CANDIDATE",
        "technical_context": "BREAKOUT_NEAR",
        "bandar_watch_eligible": True,
        "liquidity_bucket": "HIGH_LIQUIDITY",
        "relative_activity_bucket": "ACTIVE",
        "trend_score": 80,
        "momentum_score": 80,
        "volatility_score": 80,
        "rsi14": 60,
        "atr14": 20,
        "atr_pct": 0.03,
        "volume_ratio": 1.2,
        "value_ratio": 1.2,
        "return_1d": 0.01,
        "return_3d": 0.02,
        "return_5d": 0.03,
        "return_10d": 0.04,
        "return_20d": 0.05,
        "high_20d": 1010,
        "low_20d": 930,
        "ma20": 970,
        "ma50": 950,
        "ma100": 900,
        "ma200": 850,
        "distance_to_20d_high": 0.01,
        "distance_from_20d_low": 0.07,
        "distance_to_ma20": 0.02,
        "distance_to_ma50": 0.05,
        "close_location": 0.7,
        "data_points": 244,
        "is_data_valid": True,
    }
    row.update(overrides)
    return row


def test_theoretical_position_size_respects_risk_and_lot_size() -> None:
    result = calculate_theoretical_position_size(1000, 950, TradePlanConfig(capital=100_000_000))

    assert result["theoretical_position_size_lots"] > 0
    assert result["theoretical_position_value"] <= 20_000_000


def test_non_trade_candidate_is_skipped_with_nan_plan_fields() -> None:
    result = build_trade_plan_row(stage2_row(entry_setup="LIQUID_BUT_WEAK_TREND"), TradePlanConfig())

    assert result["trade_status"] == "SKIPPED_NOT_TRADE_CANDIDATE"
    assert result["is_plan_valid"] is False
    assert pd.isna(result["entry_price"])
    assert pd.isna(result["risk_reward_tp1"])
    assert result["executable_position_size_lots"] == 0


def test_invalid_data_status() -> None:
    result = build_trade_plan_row(stage2_row(is_data_valid=False), TradePlanConfig())

    assert result["trade_status"] == "INVALID_DATA"
    assert result["is_plan_valid"] is False


def test_invalid_stop_is_rejected() -> None:
    result = build_trade_plan_row(stage2_row(entry_price=1000, stop_loss=1000), TradePlanConfig())

    assert result["trade_status"] == "REJECT_INVALID_STOP"


def test_stop_too_wide_is_rejected() -> None:
    result = build_trade_plan_row(
        stage2_row(entry_price=1000, stop_loss=930),
        TradePlanConfig(max_stop_loss_pct=0.06),
    )

    assert round(result["risk_pct"], 2) == 0.07
    assert result["trade_status"] == "REJECT_STOP_TOO_WIDE"
    assert result["executable_position_size_lots"] == 0


def test_bad_rr_tp1_is_rejected_when_stop_is_inside_limit() -> None:
    result = build_trade_plan_row(
        stage2_row(entry_price=1000, stop_loss=940),
        TradePlanConfig(max_stop_loss_pct=0.07, min_rr_tp1=1.2),
    )

    assert round(result["risk_reward_tp1"], 2) == 0.83
    assert result["trade_status"] == "REJECT_BAD_RISK_REWARD_TP1"


def test_bad_rr_tp2_for_rebound_is_rejected_after_tp1_passes() -> None:
    result = build_trade_plan_row(
        stage2_row(
            entry_setup="REBOUND_CANDIDATE",
            entry_price=1000,
            stop_loss=960,
            relative_activity_bucket="NORMAL",
            value_ratio=0.85,
            volume_ratio=0.85,
        ),
        TradePlanConfig(max_stop_loss_pct=0.05, rebound_min_rr_tp1=1.2, rebound_min_rr_tp2=2.1),
    )

    assert result["risk_reward_tp1"] >= 1.2
    assert result["risk_reward_tp2"] < 2.1
    assert result["trade_status"] == "REJECT_BAD_RISK_REWARD_TP2"


def test_quiet_rebound_waits_for_confirmation_or_activity() -> None:
    result = build_trade_plan_row(
        stage2_row(entry_setup="REBOUND_CANDIDATE", relative_activity_bucket="QUIET", value_ratio=0.4, volume_ratio=0.4),
        TradePlanConfig(max_stop_loss_pct=0.10),
    )

    assert result["trade_status"] in {"WAIT_FOR_ACTIVITY", "WAIT_FOR_REBOUND_CONFIRMATION"}
    assert result["is_plan_valid"] is False


def test_position_too_small_is_rejected() -> None:
    result = build_trade_plan_row(
        stage2_row(entry_price=1000, stop_loss=990),
        TradePlanConfig(capital=10_000, risk_per_trade_pct=0.001, max_stop_loss_pct=0.02, min_rr_tp1=1.0, min_rr_tp2=1.0),
    )

    assert result["theoretical_position_size_lots"] == 0
    assert result["executable_position_size_lots"] == 0
    assert result["trade_status"] == "REJECT_POSITION_TOO_SMALL"


def test_minimum_lot_affordability_uses_position_limit() -> None:
    assert can_afford_minimum_lot(stage2_row(close=2000), TradePlanConfig(capital=500_000, max_position_pct=0.40))
    assert not can_afford_minimum_lot(stage2_row(close=2400), TradePlanConfig(capital=500_000, max_position_pct=0.40))


def test_expensive_accumulation_does_not_enter_watchlist_when_one_lot_is_too_expensive() -> None:
    result = build_trade_plan_row(
        bandar_row(
            close=2400,
            entry_price=2400,
            stop_loss=2320,
            technical_context="TECHNICALLY_WEAK_BUT_LIQUID",
            bandarmology_signal="MILD_ACCUMULATION",
            bandarmology_score=70,
            broker_activity_available=True,
        ),
        TradePlanConfig(capital=500_000, max_position_pct=0.40),
    )

    assert result["trade_status"] == "REJECT_POSITION_TOO_SMALL"
    assert result["is_plan_valid"] is False
    assert result["position_size_lots"] == 0


def test_invalid_plan_does_not_expose_executable_lot() -> None:
    result = build_trade_plan_row(
        stage2_row(entry_price=1000, stop_loss=940),
        TradePlanConfig(capital=100_000_000, max_stop_loss_pct=0.07),
    )

    assert result["theoretical_position_size_lots"] > 0
    assert result["trade_status"] != "VALID_TRADE_PLAN"
    assert result["executable_position_size_lots"] == 0
    assert result["is_plan_valid"] is False


def test_valid_trade_plan_has_executable_lot() -> None:
    result = build_trade_plan_row(
        stage2_row(entry_setup="BREAKOUT_CANDIDATE", entry_price=1000, stop_loss=970),
        TradePlanConfig(capital=100_000_000, max_stop_loss_pct=0.04, min_rr_tp1=1.2, min_rr_tp2=1.8),
    )

    assert result["trade_status"] == "VALID_TRADE_PLAN"
    assert result["is_plan_valid"] is True
    assert result["executable_position_size_lots"] > 0


def test_load_stage2_candidates_keeps_invalid_rows_for_status_output(tmp_path) -> None:
    path = tmp_path / "stage2.csv"
    df = pd.DataFrame(
        [
            stage2_row(ticker="VALID", is_data_valid=True),
            stage2_row(ticker="INVALID", is_data_valid=False),
        ]
    )
    df.to_csv(path, index=False)

    loaded = load_stage_2_candidates(path)

    assert loaded["ticker"].tolist() == ["VALID", "INVALID"]


def bandar_row(**overrides) -> dict:
    row = stage2_row(
        entry_setup="BREAKOUT_CANDIDATE",
        entry_price=1000,
        stop_loss=970,
        bandarmology_signal="STRONG_ACCUMULATION",
        bandarmology_score=80,
        broker_activity_available=True,
    )
    row.update(overrides)
    return row


def test_stage4_no_broker_data_is_skipped_by_default() -> None:
    result = build_trade_plan_row(
        bandar_row(bandarmology_signal="NO_BROKER_DATA", bandarmology_score=0, broker_activity_available=False),
        TradePlanConfig(),
    )

    assert result["trade_status"] == "SKIPPED_NO_BROKER_DATA"


def test_stage4_low_bandarmology_score_is_skipped() -> None:
    result = build_trade_plan_row(
        bandar_row(bandarmology_signal="NEUTRAL_FLOW", bandarmology_score=50, broker_activity_available=True),
        TradePlanConfig(bandarmology_min_score=60),
    )

    assert result["trade_status"] == "SKIPPED_LOW_BANDARMOLOGY_SCORE"


def test_stage4_strong_accumulation_and_valid_risk_can_be_valid_plan() -> None:
    result = build_trade_plan_row(
        bandar_row(),
        TradePlanConfig(capital=100_000_000, max_stop_loss_pct=0.04, min_rr_tp1=1.2, min_rr_tp2=1.8),
    )

    assert result["trade_status"] == "VALID_TRADE_PLAN"
    assert result["is_plan_valid"] is True
    assert result["executable_position_size_lots"] > 0


def test_stage4_without_orderbook_file_creates_draft_pending_orderbook(tmp_path) -> None:
    stage2_path = tmp_path / "stage2.csv"
    bandarmology_path = tmp_path / "stage3b.csv"
    output_path = tmp_path / "stage4.csv"
    missing_orderbook_path = tmp_path / "missing_stage3c.csv"

    pd.DataFrame([stage2_row()]).to_csv(stage2_path, index=False)
    pd.DataFrame(
        [
            {
                "ticker": "TEST",
                "bandarmology_score": 80,
                "bandarmology_signal": "STRONG_ACCUMULATION",
                "bandarmology_reason": "test",
                "bandarmology_summary": "test",
                "broker_activity_available": True,
            }
        ]
    ).to_csv(bandarmology_path, index=False)

    output = run_stage_4_trade_plan(
        stage2_path,
        bandarmology_path,
        output_path,
        TradePlanConfig(capital=100_000_000, max_stop_loss_pct=0.04, min_rr_tp1=1.2, min_rr_tp2=1.8),
        orderbook_path=missing_orderbook_path,
    )

    row = output.iloc[0]
    assert output_path.exists()
    assert row["orderbook_status"] == "NOT_CHECKED"
    assert bool(row["orderbook_confirmation_required"]) is True
    assert row["trade_status"] == "DRAFT_PLAN_PENDING_ORDERBOOK"
    assert bool(row["is_plan_valid"]) is False
    assert row["executable_position_size_lots"] == 0
    assert row["theoretical_position_size_lots"] > 0


def test_stage4_existing_orderbook_file_uses_orderbook_status_normally(tmp_path) -> None:
    stage2_path = tmp_path / "stage2.csv"
    bandarmology_path = tmp_path / "stage3b.csv"
    orderbook_path = tmp_path / "stage3c.csv"
    output_path = tmp_path / "stage4.csv"

    pd.DataFrame([stage2_row()]).to_csv(stage2_path, index=False)
    pd.DataFrame(
        [
            {
                "ticker": "TEST",
                "bandarmology_score": 80,
                "bandarmology_signal": "STRONG_ACCUMULATION",
                "bandarmology_reason": "test",
                "bandarmology_summary": "test",
                "broker_activity_available": True,
            }
        ]
    ).to_csv(bandarmology_path, index=False)
    pd.DataFrame(
        [
            {
                "ticker": "TEST",
                "orderbook_status": "WAIT_SPREAD_TOO_WIDE",
                "orderbook_score": 40,
                "spread_pct": 0.03,
            }
        ]
    ).to_csv(orderbook_path, index=False)

    output = run_stage_4_trade_plan(
        stage2_path,
        bandarmology_path,
        output_path,
        TradePlanConfig(
            capital=100_000_000,
            max_stop_loss_pct=0.04,
            min_rr_tp1=1.2,
            min_rr_tp2=1.8,
            require_orderbook_confirmation=True,
        ),
        orderbook_path=orderbook_path,
    )

    row = output.iloc[0]
    assert row["orderbook_status"] == "WAIT_SPREAD_TOO_WIDE"
    assert row["trade_status"] == "WAIT_ORDERBOOK_SPREAD_TOO_WIDE"
    assert bool(row["is_plan_valid"]) is False
    assert row["executable_position_size_lots"] == 0


def test_stage4_uses_new_gate_not_legacy_entry_setup_for_indf_like_row() -> None:
    result = build_trade_plan_row(
        bandar_row(
            ticker="INDF",
            entry_setup="LIQUID_BUT_WEAK_TREND",
            technical_context="BREAKOUT_NEAR",
            bandar_watch_eligible=True,
            broker_activity_available=True,
            bandarmology_signal="STRONG_ACCUMULATION",
            bandarmology_score=80,
        ),
        TradePlanConfig(capital=100_000_000, max_stop_loss_pct=0.04, min_rr_tp1=1.2, min_rr_tp2=1.8),
    )

    assert result["trade_status"] != "SKIPPED_NOT_TRADE_CANDIDATE"
    assert result["entry_style"] == "BREAKOUT_TRIGGER"
    assert pd.notna(result["raw_entry_price"])
    assert pd.notna(result["risk_reward_tp1"])


def test_stage4_distribution_is_skipped_before_trade_plan_for_bbri_like_row() -> None:
    result = build_trade_plan_row(
        bandar_row(
            ticker="BBRI",
            bandarmology_signal="STRONG_DISTRIBUTION",
            bandarmology_score=80,
            broker_activity_available=True,
        ),
        TradePlanConfig(bandarmology_min_score=60),
    )

    assert result["trade_status"] == "SKIPPED_NO_BANDAR_CONFIRMATION"
    assert pd.isna(result["raw_entry_price"])
    assert pd.isna(result["risk_reward_tp1"])


def test_stage4_technically_weak_but_liquid_accumulation_is_watch_not_trade() -> None:
    result = build_trade_plan_row(
        bandar_row(
            entry_setup="LIQUID_BUT_WEAK_TREND",
            technical_context="TECHNICALLY_WEAK_BUT_LIQUID",
            bandarmology_signal="MILD_ACCUMULATION",
            bandarmology_score=70,
            broker_activity_available=True,
        ),
        TradePlanConfig(capital=100_000_000, max_stop_loss_pct=0.10, min_rr_tp1=1.0, min_rr_tp2=1.0),
    )

    assert result["trade_status"] == "WATCH_BANDAR_ACCUMULATION_WAIT_TECHNICAL_TRIGGER"
    assert result["is_plan_valid"] is False
    assert result["executable_position_size_lots"] == 0
    assert result["position_size_lots"] == 0
    assert pd.isna(result["entry_price"])


def test_stage4_short_term_accumulation_against_distribution_is_watch() -> None:
    result = build_trade_plan_row(
        bandar_row(
            bandarmology_signal="SHORT_TERM_ACCUMULATION_AGAINST_MEDIUM_DISTRIBUTION",
            bandarmology_score=62,
            broker_activity_available=True,
        ),
        TradePlanConfig(),
    )

    assert result["trade_status"] == "WATCH_SHORT_TERM_ACCUMULATION_AGAINST_DISTRIBUTION"
    assert result["executable_position_size_lots"] == 0


def test_stage4_pullback_with_medium_accumulation_is_watch_by_default() -> None:
    result = build_trade_plan_row(
        bandar_row(
            bandarmology_signal="PULLBACK_WITH_MEDIUM_ACCUMULATION",
            bandarmology_score=64,
            broker_activity_available=True,
        ),
        TradePlanConfig(),
    )

    assert result["trade_status"] == "WATCH_PULLBACK_WITH_MEDIUM_ACCUMULATION"
    assert result["executable_position_size_lots"] == 0


def test_stage4_orderbook_wait_spread_too_wide_blocks_executable_when_required() -> None:
    result = build_trade_plan_row(
        bandar_row(orderbook_status="WAIT_SPREAD_TOO_WIDE", orderbook_score=40),
        TradePlanConfig(require_orderbook_confirmation=True),
    )

    assert result["trade_status"] == "WAIT_ORDERBOOK_SPREAD_TOO_WIDE"
    assert result["is_plan_valid"] is False
    assert result["executable_position_size_lots"] == 0


def test_strategy_mode_defaults_remain_interday() -> None:
    config = TradePlanConfig()

    assert config.strategy_mode == "interday"
    assert config.tp1_pct == 0.05
    assert config.tp2_pct == 0.08
    assert config.time_stop_days == 10
    assert config.require_orderbook_confirmation is False
    assert config.force_exit_same_day is False


def test_bpjs_strategy_defaults_are_intraday_execution_strict() -> None:
    config = TradePlanConfig(strategy_mode="bpjs")

    assert config.tp1_pct == 0.02
    assert config.tp2_pct == 0.03
    assert config.max_stop_loss_pct == 0.015
    assert config.force_exit_same_day is True
    assert config.time_stop_days == 0
    assert config.require_orderbook_confirmation is True


def test_interday_orderbook_risk_is_note_not_gate_when_not_required() -> None:
    result = build_trade_plan_row(
        bandar_row(orderbook_status="WAIT_SPREAD_TOO_WIDE", orderbook_score=40),
        TradePlanConfig(capital=100_000_000, max_stop_loss_pct=0.04, min_rr_tp1=1.2, min_rr_tp2=1.8),
    )

    assert result["trade_status"] == "VALID_TRADE_PLAN"
    assert "WAIT_SPREAD_TOO_WIDE" in result["execution_quality_note"]


def test_interday_corporate_action_active_is_watch_by_default() -> None:
    result = build_trade_plan_row(
        bandar_row(corp_action_active=True, orderbook_status="REJECT_CORPORATE_ACTION_RISK"),
        TradePlanConfig(),
    )

    assert result["trade_status"] == "WATCH_CORPORATE_ACTION_RISK"
    assert result["executable_position_size_lots"] == 0


def test_interday_corporate_action_active_can_be_strict_reject() -> None:
    result = build_trade_plan_row(
        bandar_row(corp_action_active=True, orderbook_status="REJECT_CORPORATE_ACTION_RISK"),
        TradePlanConfig(strict_corporate_action_filter=True),
    )

    assert result["trade_status"] == "REJECT_CORPORATE_ACTION_RISK"
    assert result["executable_position_size_lots"] == 0


def test_bpjs_requires_supportive_or_neutral_orderbook() -> None:
    result = build_trade_plan_row(
        bandar_row(orderbook_status="WAIT_SPREAD_TOO_WIDE", orderbook_score=40),
        TradePlanConfig(strategy_mode="bpjs"),
    )

    assert result["trade_status"] == "WAIT_ORDERBOOK_SPREAD_TOO_WIDE"
    assert result["is_plan_valid"] is False
    assert result["executable_position_size_lots"] == 0


def test_bpjs_corporate_action_active_hard_rejects() -> None:
    result = build_trade_plan_row(
        bandar_row(corp_action_active=True, orderbook_status="ORDERBOOK_SUPPORTIVE", orderbook_score=90),
        TradePlanConfig(strategy_mode="bpjs"),
    )

    assert result["trade_status"] == "REJECT_CORPORATE_ACTION_RISK"
    assert result["executable_position_size_lots"] == 0


def test_stage4_invalid_plan_keeps_executable_lot_zero() -> None:
    result = build_trade_plan_row(
        bandar_row(entry_price=1000, stop_loss=940),
        TradePlanConfig(capital=100_000_000, max_stop_loss_pct=0.07),
    )

    assert result["trade_status"] != "VALID_TRADE_PLAN"
    assert result["executable_position_size_lots"] == 0


def test_stage4_keeps_idx_tick_rounding() -> None:
    result = build_trade_plan_row(
        bandar_row(entry_price=1195, stop_loss=1154.244),
        TradePlanConfig(capital=100_000_000, max_stop_loss_pct=0.10, min_rr_tp1=1.0, min_rr_tp2=1.0),
    )

    assert result["stop_loss"] == 1150
    assert result["prices_are_tick_valid"] is True


def test_idx_tick_size_mapping() -> None:
    assert get_idx_tick_size(100) == 1
    assert get_idx_tick_size(250) == 2
    assert get_idx_tick_size(1195) == 5
    assert get_idx_tick_size(2700) == 10
    assert get_idx_tick_size(5800) == 25


def test_rounding_floor_to_idx_tick() -> None:
    assert round_price_to_tick(1154.244, "floor") == 1150
    assert round_price_to_tick(1254.75, "floor") == 1250


def test_rounding_ceil_to_idx_tick() -> None:
    assert round_price_to_tick(1154.244, "ceil") == 1155
    assert round_price_to_tick(1254.75, "ceil") == 1255


def test_rounding_nearest_to_idx_tick() -> None:
    assert round_price_to_tick(1194, "nearest") == 1195
    assert round_price_to_tick(1192, "nearest") == 1190


def test_stop_loss_and_take_profit_use_conservative_rounding() -> None:
    result = build_trade_plan_row(
        stage2_row(
            entry_price=1195,
            stop_loss=1154.244,
            high_20d=1220,
            ma20=1160,
            low_20d=1140,
        ),
        TradePlanConfig(capital=100_000_000, max_stop_loss_pct=0.10, min_rr_tp1=1.0, min_rr_tp2=1.0),
    )

    assert result["raw_stop_loss"] == 1154.244
    assert result["stop_loss"] == 1150
    assert result["raw_take_profit_1"] == 1254.75
    assert result["take_profit_1"] == 1250


def test_tugu_like_plan_recalculates_risk_reward_after_rounding() -> None:
    result = build_trade_plan_row(
        stage2_row(
            ticker="TUGU",
            entry_price=1195,
            stop_loss=1154.244,
            high_20d=1220,
            ma20=1160,
            low_20d=1140,
        ),
        TradePlanConfig(capital=100_000_000, max_stop_loss_pct=0.10, min_rr_tp1=1.0, min_rr_tp2=1.0),
    )

    assert result["entry_price"] == 1195
    assert result["stop_loss"] == 1150
    assert result["take_profit_1"] == 1250
    assert result["take_profit_2"] == 1290
    assert result["risk_per_share"] == 45
    assert round(result["risk_reward_tp1"], 2) == 1.22
    assert result["prices_are_tick_valid"] is True


def test_invalid_plan_after_rounding_has_no_executable_lot() -> None:
    result = build_trade_plan_row(
        stage2_row(entry_price=1195, stop_loss=1154.244),
        TradePlanConfig(capital=100_000_000, max_stop_loss_pct=0.04, min_rr_tp1=2.0),
    )

    assert result["is_plan_valid"] is False
    assert result["executable_position_size_lots"] == 0
