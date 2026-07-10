from __future__ import annotations

import pandas as pd

from interday_liquidity_screener.constants import WatchlistStatus
from interday_liquidity_screener.pipeline import resolve_artifact_path, summarize_run
from interday_liquidity_screener.run_audit import build_run_audit_report, render_run_audit_markdown


def test_run_audit_marks_draft_run_as_needing_morning_confirmation(tmp_path) -> None:
    run_dir = tmp_path / "20260708_205047"
    run_dir.mkdir()
    pd.DataFrame([{"ticker": "PGEO", "liquidity_bucket": "HIGH_LIQUIDITY"}]).to_csv(run_dir / "stage1_liquidity.csv", index=False)
    pd.DataFrame([{"ticker": "PGEO", "bandar_watch_eligible": True}]).to_csv(run_dir / "stage2_technical_context.csv", index=False)
    pd.DataFrame(
        [
            {
                "symbol": "PGEO",
                "final_status": WatchlistStatus.EXECUTION_DRAFT.value,
                "final_score": 92.2,
                "entry_price": 940,
                "tp1_price": 955,
                "stop_loss_price": 930,
                "position_value": 940_000,
            }
        ]
    ).to_csv(run_dir / "hybrid_watchlist.csv", index=False)

    report = build_run_audit_report(run_dir, resolve_artifact_path, summarize_run, capital=1_000_000)

    assert report.schema_version == "run-audit-v1"
    assert report.overall_status == "NEEDS_MORNING_CONFIRMATION"
    assert report.recommendation is not None
    assert report.recommendation["primary"]["symbol"] == "PGEO"
    assert "stage3c" in report.missing_artifacts
    assert "Fase Pagi" in report.next_action


def test_run_audit_markdown_lists_artifact_health(tmp_path) -> None:
    run_dir = tmp_path / "missing_hybrid"
    run_dir.mkdir()
    pd.DataFrame([{"ticker": "BBCA", "liquidity_bucket": "GOOD_LIQUIDITY"}]).to_csv(run_dir / "stage1_liquidity.csv", index=False)

    report = build_run_audit_report(run_dir, resolve_artifact_path, summarize_run)
    markdown = render_run_audit_markdown(report)

    assert report.overall_status == "BLOCKED_MISSING_HYBRID_WATCHLIST"
    assert "run-audit-v1" in markdown
    assert "| hybrid_watchlist | MISSING |" in markdown
    assert "Run or resume through Stage Hybrid" in markdown
