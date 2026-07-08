from __future__ import annotations

from datetime import datetime
import os

from interday_liquidity_screener.pipeline import (
    apply_runtime_api_keys,
    build_run_paths,
    create_run_id,
    load_csv,
    parse_ticker_text,
    resolve_artifact_path,
    token_available,
)


def test_create_run_id_uses_expected_timestamp_format() -> None:
    assert create_run_id(datetime(2026, 7, 4, 9, 8, 7)) == "20260704_090807"


def test_build_run_paths_uses_structured_output_folder() -> None:
    paths = build_run_paths("data/output/ui_runs", "20260704_090807")

    assert str(paths.run_dir).endswith("data\\output\\ui_runs\\20260704_090807") or str(paths.run_dir).endswith("data/output/ui_runs/20260704_090807")
    assert paths.stage1.name == "stage1_liquidity.csv"
    assert paths.stage3a_detector.parent.name == "stockbit"
    assert paths.hybrid_watchlist.name == "hybrid_watchlist.csv"
    assert paths.stage6_report.name == "stage6_llm_daily_report.md"


def test_parse_ticker_text_normalizes_and_deduplicates() -> None:
    assert parse_ticker_text("bbca\nTLKM.JK,bbca") == ["BBCA.JK", "TLKM.JK"]


def test_token_available_reads_dotenv_without_exporting_secret(tmp_path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("STOCKBIT_TOKEN='secret-token'\nEMPTY_TOKEN=\n", encoding="utf-8")

    assert token_available("STOCKBIT_TOKEN", env_path)
    assert not token_available("EMPTY_TOKEN", env_path)
    assert not token_available("MISSING_TOKEN", env_path)


def test_apply_runtime_api_keys_sets_session_values(monkeypatch) -> None:
    monkeypatch.delenv("STOCKBIT_TOKEN", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("_UI_STOCKBIT_TOKEN_APPLIED", raising=False)
    monkeypatch.delenv("_UI_DEEPSEEK_API_KEY_APPLIED", raising=False)

    apply_runtime_api_keys("Bearer stockbit-session-token", "deepseek-session-key")

    assert os.environ["STOCKBIT_TOKEN"] == "stockbit-session-token"
    assert os.environ["DEEPSEEK_API_KEY"] == "deepseek-session-key"
    assert token_available("STOCKBIT_TOKEN")
    assert token_available("DEEPSEEK_API_KEY")


def test_resolve_artifact_path_supports_legacy_stage4_names(tmp_path) -> None:
    legacy = tmp_path / "stage4_trade_plan_interday.csv"
    legacy.write_text("ticker\nBBRI\n", encoding="utf-8")

    assert resolve_artifact_path(tmp_path, "stage4") == legacy


def test_resolve_artifact_path_supports_hybrid_watchlist(tmp_path) -> None:
    hybrid = tmp_path / "stage_hybrid_watchlist.csv"
    hybrid.write_text("symbol\nBBRI\n", encoding="utf-8")

    assert resolve_artifact_path(tmp_path, "hybrid_watchlist") == hybrid


def test_load_csv_returns_empty_dataframe_for_empty_file(tmp_path) -> None:
    empty_csv = tmp_path / "empty.csv"
    empty_csv.write_text("", encoding="utf-8")

    assert load_csv(empty_csv).empty
