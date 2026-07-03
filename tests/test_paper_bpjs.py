from __future__ import annotations

import pandas as pd

from interday_liquidity_screener.paper_bpjs import (
    BpjsPaperConfig,
    calculate_bpjs_summary,
    create_bpjs_paper_trades,
    update_bpjs_paper_trades,
)


def stage4_row(**overrides):
    row = {
        "ticker": "TEST",
        "strategy_mode": "bpjs",
        "trade_status": "VALID_TRADE_PLAN",
        "is_plan_valid": True,
        "entry_price": 100.0,
        "stop_loss": 98.0,
        "take_profit_1": 102.0,
        "take_profit_2": 103.0,
        "orderbook_status": "ORDERBOOK_SUPPORTIVE",
        "orderbook_score": 80,
        "executable_position_size_lots": 2,
    }
    row.update(overrides)
    return row


def orderbook_row(**overrides):
    row = {
        "ticker": "TEST",
        "lastprice": 100.0,
        "spread_pct": 0.002,
        "depth_imbalance_top5": 0.2,
        "offer_wall_ratio_top5": 1.5,
        "fnet": 1_000_000,
        "foreign_net_ratio": 0.05,
    }
    row.update(overrides)
    return row


def test_bpjs_valid_stage4_supportive_orderbook_opens_paper_trade() -> None:
    paper = create_bpjs_paper_trades(
        pd.DataFrame([stage4_row()]),
        pd.DataFrame([orderbook_row()]),
        BpjsPaperConfig(date="2026-07-03"),
    )

    assert len(paper) == 1
    assert paper.iloc[0]["status"] == "OPEN_PAPER_TRADE"
    assert paper.iloc[0]["paper_entry_price"] == 100.0


def test_non_bpjs_row_is_not_paper_trade() -> None:
    paper = create_bpjs_paper_trades(
        pd.DataFrame([stage4_row(strategy_mode="interday")]),
        pd.DataFrame([orderbook_row()]),
        BpjsPaperConfig(date="2026-07-03"),
    )

    assert paper.empty


def test_wait_orderbook_row_is_not_paper_trade() -> None:
    paper = create_bpjs_paper_trades(
        pd.DataFrame([stage4_row(orderbook_status="WAIT_SPREAD_TOO_WIDE")]),
        pd.DataFrame([orderbook_row()]),
        BpjsPaperConfig(date="2026-07-03"),
    )

    assert paper.empty


def test_update_actual_exit_closes_trade_and_calculates_return() -> None:
    paper = create_bpjs_paper_trades(
        pd.DataFrame([stage4_row()]),
        pd.DataFrame([orderbook_row()]),
        BpjsPaperConfig(date="2026-07-03"),
    )
    updated = update_bpjs_paper_trades(
        paper,
        pd.DataFrame([{"ticker": "TEST", "exit_price": 102.0, "exit_time": "15:45", "exit_reason": "MANUAL_TP"}]),
    )

    assert updated.iloc[0]["status"] == "CLOSED_PAPER_TRADE"
    assert updated.iloc[0]["return_pct"] == 0.02
    assert updated.iloc[0]["pnl_amount"] == 400.0


def test_summary_metrics() -> None:
    paper = pd.DataFrame(
        [
            {"status": "CLOSED_PAPER_TRADE", "return_pct": 0.02, "pnl_amount": 200, "orderbook_status": "ORDERBOOK_SUPPORTIVE"},
            {"status": "CLOSED_PAPER_TRADE", "return_pct": -0.01, "pnl_amount": -100, "orderbook_status": "ORDERBOOK_NEUTRAL"},
        ]
    )

    summary = calculate_bpjs_summary(paper)

    assert summary["win_rate"] == 0.5
    assert summary["average_return_pct"] == 0.005
    assert summary["total_pnl_amount"] == 100.0

