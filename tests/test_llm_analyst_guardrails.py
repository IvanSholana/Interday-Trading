from __future__ import annotations

from interday_liquidity_screener.llm_analyst import validate_llm_output


def evidence_pack():
    return {
        "candidate_groups": {
            "valid": [{"ticker": "INDF", "trade_status": "VALID_TRADE_PLAN", "is_plan_valid": True, "stop_loss": 100, "take_profit_1": 110}],
            "watchlist": [{"ticker": "MTEL", "trade_status": "WATCH_BANDAR_ACCUMULATION_WAIT_TECHNICAL_TRIGGER", "is_plan_valid": False}],
            "near_valid": [{"ticker": "ASII", "trade_status": "REJECT_BAD_RISK_REWARD_TP1", "is_plan_valid": False}],
        }
    }


def test_unknown_ticker_is_flagged() -> None:
    output, violations = validate_llm_output({"candidate_ranking": [{"ticker": "NEW", "category": "VALID"}]}, evidence_pack())

    assert violations[0]["kind"] == "unknown_ticker"
    assert output["candidate_ranking"][0]["category"] == "REJECTED"


def test_changed_trade_status_is_flagged_and_restored() -> None:
    output, violations = validate_llm_output({"candidate_ranking": [{"ticker": "INDF", "original_trade_status": "REJECTED", "category": "VALID"}]}, evidence_pack())

    assert any(v["kind"] == "changed_trade_status" for v in violations)
    assert output["candidate_ranking"][0]["original_trade_status"] == "VALID_TRADE_PLAN"


def test_rejected_ticker_marked_valid_is_downgraded() -> None:
    output, violations = validate_llm_output({"candidate_ranking": [{"ticker": "ASII", "original_trade_status": "REJECT_BAD_RISK_REWARD_TP1", "category": "VALID"}]}, evidence_pack())

    assert any(v["kind"] == "rejected_or_watch_marked_valid" for v in violations)
    assert output["candidate_ranking"][0]["category"] == "REJECTED"


def test_auto_order_language_is_flagged() -> None:
    _, violations = validate_llm_output({"final_notes": "Use auto order immediately."}, evidence_pack())

    assert any(v["kind"] == "forbidden_execution_language" for v in violations)


def test_changed_stop_loss_is_flagged_and_removed() -> None:
    output, violations = validate_llm_output({"candidate_ranking": [{"ticker": "INDF", "original_trade_status": "VALID_TRADE_PLAN", "category": "VALID", "stop_loss": 90}]}, evidence_pack())

    assert any(v["kind"] == "changed_risk_parameter" for v in violations)
    assert "stop_loss" not in output["candidate_ranking"][0]


def test_conservative_output_preserved() -> None:
    output, violations = validate_llm_output({"candidate_ranking": [{"ticker": "INDF", "original_trade_status": "VALID_TRADE_PLAN", "category": "VALID"}]}, evidence_pack())

    assert violations == []
    assert output["candidate_ranking"][0]["guardrail_validated"] is True

