from __future__ import annotations

import json

import pandas as pd

from interday_liquidity_screener.llm_analyst import build_evidence_pack, sanitize_for_llm, write_evidence_pack


def write_csv(path, rows):
    pd.DataFrame(rows).to_csv(path, index=False)


def base_row(**overrides):
    row = {
        "ticker": "TEST",
        "strategy_mode": "interday",
        "trade_status": "VALID_TRADE_PLAN",
        "is_plan_valid": True,
        "liquidity_bucket": "HIGH_LIQUIDITY",
        "technical_context": "BREAKOUT_NEAR",
        "bandarmology_signal": "STRONG_ACCUMULATION",
        "bandarmology_score": 80,
        "risk_reward_tp1": 2.0,
        "orderbook_score": 70,
    }
    row.update(overrides)
    return row


def test_evidence_pack_excludes_raw_secrets() -> None:
    evidence = sanitize_for_llm({"DEEPSEEK_API_KEY": "abc", "Authorization": "Bearer secret", "safe": "ok"})
    text = json.dumps(evidence)

    assert "abc" not in text
    assert "Bearer secret" not in text
    assert "ok" in text


def test_valid_trade_plan_goes_to_valid(tmp_path) -> None:
    stage4 = tmp_path / "stage4.csv"
    write_csv(stage4, [base_row(ticker="INDF")])

    evidence = build_evidence_pack(None, None, None, stage4, None, None, "interday", "2026-07-03", 30)

    assert evidence["candidate_groups"]["valid"][0]["ticker"] == "INDF"


def test_watch_status_goes_to_watchlist(tmp_path) -> None:
    stage4 = tmp_path / "stage4.csv"
    write_csv(stage4, [base_row(ticker="MTEL", trade_status="WATCH_BANDAR_ACCUMULATION_WAIT_TECHNICAL_TRIGGER", is_plan_valid=False)])

    evidence = build_evidence_pack(None, None, None, stage4, None, None, "interday", "2026-07-03", 30)

    assert evidence["candidate_groups"]["watchlist"][0]["ticker"] == "MTEL"


def test_reject_bad_rr_with_strong_bandar_goes_near_valid(tmp_path) -> None:
    stage4 = tmp_path / "stage4.csv"
    write_csv(stage4, [base_row(ticker="INDF", trade_status="REJECT_BAD_RISK_REWARD_TP1", is_plan_valid=False)])

    evidence = build_evidence_pack(None, None, None, stage4, None, None, "interday", "2026-07-03", 30)

    assert evidence["candidate_groups"]["near_valid"][0]["ticker"] == "INDF"


def test_strong_distribution_goes_to_avoid(tmp_path) -> None:
    stage4 = tmp_path / "stage4.csv"
    write_csv(stage4, [base_row(ticker="BBRI", trade_status="SKIPPED_NO_BANDAR_CONFIRMATION", bandarmology_signal="STRONG_DISTRIBUTION", is_plan_valid=False)])

    evidence = build_evidence_pack(None, None, None, stage4, None, None, "interday", "2026-07-03", 30)

    assert evidence["candidate_groups"]["avoid"][0]["ticker"] == "BBRI"


def test_missing_optional_files_do_not_crash_and_warn(tmp_path) -> None:
    stage4 = tmp_path / "stage4.csv"
    write_csv(stage4, [base_row()])

    evidence = build_evidence_pack(tmp_path / "missing.csv", None, None, stage4, tmp_path / "missing.json", None, "interday", "2026-07-03", 30)

    assert evidence["warnings"]


def test_max_candidates_limit_works(tmp_path) -> None:
    stage4 = tmp_path / "stage4.csv"
    write_csv(stage4, [base_row(ticker=f"T{i}") for i in range(5)])

    evidence = build_evidence_pack(None, None, None, stage4, None, None, "interday", "2026-07-03", 3)

    assert len(evidence["candidate_groups"]["valid"]) == 3


def test_write_evidence_pack(tmp_path) -> None:
    path = tmp_path / "evidence.json"
    write_evidence_pack({"safe": True}, path)

    assert json.loads(path.read_text())["safe"] is True

