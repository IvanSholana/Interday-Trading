from __future__ import annotations

import json
import os

from interday_liquidity_screener.llm_analyst import run_llm_report, write_evidence_pack


def evidence():
    return {
        "metadata": {"run_date": "2026-07-03", "strategy_mode": "interday"},
        "warnings": [],
        "candidate_groups": {
            "valid": [{"ticker": "INDF", "trade_status": "VALID_TRADE_PLAN", "is_plan_valid": True, "bandarmology_signal": "STRONG_ACCUMULATION", "risk_reward_tp1": 2.0, "orderbook_status": "ORDERBOOK_SUPPORTIVE"}],
            "watchlist": [{"ticker": "MTEL", "trade_status": "WATCH_BANDAR_ACCUMULATION_WAIT_TECHNICAL_TRIGGER", "is_plan_valid": False, "trade_reason": "watch"}],
            "near_valid": [],
            "rejected_important": [],
            "avoid": [],
        },
    }


def test_dry_run_creates_outputs_and_safety(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "SHOULD_NOT_BE_SAVED")
    evidence_path = tmp_path / "evidence.json"
    report = tmp_path / "report.md"
    ranking = tmp_path / "ranking.json"
    watchlist = tmp_path / "watchlist.csv"
    raw = tmp_path / "raw.json"
    write_evidence_pack(evidence(), evidence_path)

    run_llm_report(evidence_path, report, ranking, watchlist, raw, "interday", dry_run=True)

    assert report.exists()
    assert ranking.exists()
    assert watchlist.exists()
    assert raw.exists()
    assert "Safety Reminder" in report.read_text(encoding="utf-8")
    assert "SHOULD_NOT_BE_SAVED" not in raw.read_text(encoding="utf-8")
    assert json.loads(ranking.read_text(encoding="utf-8"))["validated"] is True

