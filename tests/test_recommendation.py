from __future__ import annotations

import pandas as pd

from interday_liquidity_screener.constants import WatchlistStatus
from interday_liquidity_screener.recommendation import (
    build_recommendation_pack,
    render_recommendation_markdown,
)


def test_recommendation_prefers_high_score_execution_draft_with_lot_sizing() -> None:
    watchlist = pd.DataFrame(
        [
            {
                "symbol": "PGEO",
                "name": "PGEO",
                "final_status": WatchlistStatus.EXECUTION_DRAFT.value,
                "final_score": 92.2,
                "rank": 1,
                "entry_price": 940,
                "tp1_price": 955,
                "stop_loss_price": 930,
                "position_value": 940_000,
                "estimated_buy_fee": 1_410,
                "estimated_sell_fee": 2_387.5,
                "estimated_slippage": 1_895,
                "net_profit_after_fee": 9_307.5,
                "explanation": "draft needs live orderbook",
            },
            {
                "symbol": "ASII",
                "name": "ASII",
                "final_status": WatchlistStatus.EXECUTION_DRAFT.value,
                "final_score": 84.8,
                "rank": 2,
                "entry_price": 4_890,
                "tp1_price": 4_980,
                "stop_loss_price": 4_840,
                "position_value": 978_000,
            },
        ]
    )

    pack = build_recommendation_pack(watchlist, run_id="20260708_205047", capital=1_000_000, max_tp_pct=0.05)

    assert pack.schema_version == "recommendation-pack-v2"
    assert pack.policy_version == "2026-07-professional-mvp-v1"
    assert pack.policy["min_risk_reward"] == 1.0
    assert pack.primary is not None
    assert pack.primary.symbol == "PGEO"
    assert pack.primary.readiness == "NEEDS_LIVE_CONFIRMATION"
    assert pack.primary.execution_decision == "WAIT_CONFIRMATION"
    assert pack.primary.lots == 10
    assert pack.primary.target_tp_pct == (955 - 940) / 940
    assert pack.primary.max_loss_amount == 10_000
    assert pack.primary.estimated_buy_fee == 1_410
    assert pack.primary.expected_net_profit == 9_307.5
    assert pack.primary.confidence_components["final_confidence"] == pack.primary.confidence_score
    assert pack.primary.confidence_components["audit_penalty"] > 0
    assert pack.primary.decision_grade == "B"
    assert "NEEDS_LIVE_CONFIRMATION" in pack.primary.audit_flags
    assert pack.draft_count == 2
    assert pack.excluded_by_tp_limit_count == 0
    assert pack.data_quality["total_rows"] == 2
    assert pack.data_quality["complete_price_plan_count"] == 2
    assert pack.data_quality["missing_price_plan_count"] == 0
    assert pack.total_selected_position_value == 940_000
    assert pack.total_selected_capital_usage_pct == 0.94
    assert pack.total_selected_expected_net_profit == 9_307.5
    assert pack.portfolio_target_profit_amount == 50_000
    assert pack.portfolio_target_progress_pct == 9_307.5 / 50_000
    assert pack.portfolio_profit_shortfall_amount == 40_692.5
    assert pack.portfolio_target_reached is False
    assert pack.total_selected_max_loss_amount == 10_000
    assert pack.total_selected_max_loss_pct == 0.01
    assert pack.portfolio_decision == "WITHIN_BUDGET_REVIEW"
    assert "PROFIT_TARGET_NOT_REACHED" in pack.portfolio_flags


def test_recommendation_does_not_treat_portfolio_target_as_candidate_tp_cap() -> None:
    watchlist = pd.DataFrame(
        [
            {
                "symbol": "FAST",
                "final_status": WatchlistStatus.EXECUTION_READY.value,
                "final_score": 90,
                "entry_price": 100,
                "tp1_price": 108,
                "stop_loss_price": 97,
                "position_value": 1_000_000,
            },
            {
                "symbol": "SLOW",
                "final_status": WatchlistStatus.READY_SOON.value,
                "final_score": 70,
                "entry_price": 200,
                "tp1_price": 206,
                "stop_loss_price": 196,
                "position_value": 1_000_000,
            },
        ]
    )

    pack = build_recommendation_pack(watchlist, run_id="run", capital=1_000_000, max_tp_pct=0.05)

    assert pack.primary is not None
    assert pack.primary.symbol == "FAST"
    assert pack.excluded_by_tp_limit_count == 0
    assert pack.ready_count == 1
    assert pack.watch_count == 1
    assert [item.symbol for item in pack.candidates] == ["FAST"]


def test_recommendation_caps_position_value_to_max_position_pct() -> None:
    watchlist = pd.DataFrame(
        [
            {
                "symbol": "PGEO",
                "final_status": WatchlistStatus.EXECUTION_READY.value,
                "final_score": 92,
                "entry_price": 940,
                "tp1_price": 955,
                "stop_loss_price": 930,
                "position_value": 940_000,
            }
        ]
    )

    pack = build_recommendation_pack(
        watchlist,
        run_id="run",
        capital=1_000_000,
        max_position_pct=0.20,
    )

    assert pack.max_position_pct == 0.20
    assert pack.primary is not None
    assert pack.primary.lots == 2
    assert pack.primary.position_value == 188_000
    assert pack.primary.capital_usage_pct == 0.188
    assert pack.primary.expected_gross_profit == 3_000
    assert pack.primary.expected_net_profit == 1_861.5
    assert pack.primary.estimated_buy_fee == 282
    assert pack.primary.estimated_sell_fee == 477.5
    assert pack.primary.estimated_slippage == 379
    assert "POSITION_REDUCED_TO_CAP" in pack.primary.audit_flags
    assert "LOW_NET_PROFIT_AFTER_COSTS" in pack.primary.audit_flags
    assert pack.primary.decision_grade == "D"
    assert pack.primary.execution_decision == "AVOID"
    assert pack.total_selected_position_value == 188_000
    assert pack.total_selected_expected_net_profit == 1_861.5
    assert pack.total_selected_max_loss_amount == 2_000
    assert pack.total_selected_max_loss_pct == 0.002
    assert pack.portfolio_decision == "WITHIN_BUDGET_REVIEW"
    assert pack.portfolio_flags == ["PROFIT_TARGET_NOT_REACHED"]


def test_recommendation_rejects_one_lot_above_position_cap() -> None:
    watchlist = pd.DataFrame(
        [
            {
                "symbol": "ASII",
                "final_status": WatchlistStatus.EXECUTION_READY.value,
                "final_score": 92,
                "entry_price": 4_790,
                "tp1_price": 4_880,
                "stop_loss_price": 4_740,
                "position_value": 958_000,
                "position_size_lots": 2,
            }
        ]
    )

    pack = build_recommendation_pack(
        watchlist,
        run_id="run",
        capital=1_000_000,
        max_position_pct=0.20,
    )

    assert pack.primary is None
    assert pack.selected_count == 0
    assert pack.data_quality["affordable_lot_count"] == 0


def test_recommendation_reads_stage4_style_column_aliases() -> None:
    watchlist = pd.DataFrame(
        [
            {
                "ticker": "BBCA.JK",
                "final_status": WatchlistStatus.EXECUTION_READY.value,
                "final_score": 88,
                "entry_price": 6_175,
                "take_profit_1": 6_275,
                "stop_loss": 6_100,
                "executable_position_value": 617_500,
                "risk_reward_tp1": 1.33,
            }
        ]
    )

    pack = build_recommendation_pack(watchlist, run_id="run", capital=1_000_000)

    assert pack.primary is not None
    assert pack.primary.symbol == "BBCA.JK"
    assert pack.primary.tp1_price == 6_275
    assert pack.primary.stop_loss_price == 6_100
    assert pack.primary.position_value == 617_500
    assert pack.primary.risk_reward_ratio == 1.33
    assert pack.primary.lots == 1


def test_recommendation_data_quality_counts_missing_plan_and_unknown_status() -> None:
    watchlist = pd.DataFrame(
        [
            {
                "symbol": "ODD",
                "final_status": "CUSTOM_STATUS",
                "final_score": 10,
                "entry_price": 100,
            },
            {
                "symbol": "READY",
                "final_status": WatchlistStatus.EXECUTION_READY.value,
                "final_score": 90,
                "entry_price": 100,
                "tp1_price": 103,
                "stop_loss_price": 98,
                "position_value": 100_000,
            },
        ]
    )

    pack = build_recommendation_pack(watchlist, run_id="run", capital=1_000_000)

    assert pack.data_quality["total_rows"] == 2
    assert pack.data_quality["complete_price_plan_count"] == 1
    assert pack.data_quality["missing_price_plan_count"] == 1
    assert pack.data_quality["unknown_status_count"] == 1
    assert pack.data_quality["affordable_lot_count"] == 2


def test_render_recommendation_markdown_includes_primary_and_caveat() -> None:
    watchlist = pd.DataFrame(
        [
            {
                "symbol": "BBCA",
                "final_status": WatchlistStatus.EXECUTION_READY.value,
                "final_score": 88,
                "entry_price": 6_175,
                "tp1_price": 6_275,
                "stop_loss_price": 6_100,
                "position_value": 617_500,
            }
        ]
    )

    pack = build_recommendation_pack(watchlist, run_id="run", capital=1_000_000)
    markdown = render_recommendation_markdown(pack)

    assert "# Professional Trade Recommendation Pack: run" in markdown
    assert "recommendation-pack-v2" in markdown
    assert "Policy" in markdown
    assert "**BBCA**" in markdown
    assert "REVIEW_BUY" in markdown
    assert "Confidence model" in markdown
    assert "Portfolio decision" in markdown
    assert "Data quality" in markdown
    assert "Audit flags" in markdown
    assert "not a guarantee of profit" in markdown


def test_empty_recommendation_pack_has_no_portfolio_action() -> None:
    pack = build_recommendation_pack(pd.DataFrame(), run_id="run", capital=1_000_000)

    assert pack.portfolio_decision == "NO_PORTFOLIO_ACTION"
    assert pack.portfolio_flags == ["NO_SELECTED_CANDIDATES"]
    assert pack.data_quality["total_rows"] == 0


def test_recommendation_accumulates_multiple_positions_until_portfolio_target() -> None:
    watchlist = pd.DataFrame(
        [
            {
                "symbol": symbol,
                "final_status": WatchlistStatus.EXECUTION_READY.value,
                "final_score": score,
                "entry_price": 100,
                "tp1_price": 125,
                "stop_loss_price": 95,
                "position_value": 200_000,
            }
            for symbol, score in [("AAA", 90), ("BBB", 80), ("CCC", 70), ("DDD", 60)]
        ]
    )

    pack = build_recommendation_pack(
        watchlist,
        run_id="run",
        capital=1_000_000,
        max_tp_pct=0.05,
        max_position_pct=0.20,
    )

    assert pack.portfolio_target_profit_amount == 50_000
    assert [item.symbol for item in pack.candidates] == ["AAA", "BBB"]
    assert pack.total_selected_expected_net_profit is not None
    assert pack.total_selected_expected_net_profit >= 50_000
    assert pack.portfolio_target_reached is True
    assert pack.portfolio_profit_shortfall_amount == 0
