from __future__ import annotations

import pandas as pd
from fastapi.testclient import TestClient

from interday_liquidity_screener.constants import WatchlistStatus
from interday_liquidity_screener import server


def test_recommendation_endpoint_returns_structured_pack(tmp_path, monkeypatch) -> None:
    run_root = tmp_path / "runs"
    run_dir = run_root / "20260708_205047"
    run_dir.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "symbol": "PGEO",
                "name": "PGEO",
                "final_status": WatchlistStatus.EXECUTION_DRAFT.value,
                "final_score": 92.2,
                "entry_price": 940,
                "tp1_price": 955,
                "stop_loss_price": 930,
                "position_value": 940_000,
            }
        ]
    ).to_csv(run_dir / "hybrid_watchlist.csv", index=False)

    monkeypatch.setattr(server, "DEFAULT_RUN_ROOT", run_root)
    client = TestClient(server.app)

    response = client.get("/api/recommendation/20260708_205047?capital=1000000&max_tp_pct=0.05")

    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_version"] == "recommendation-pack-v1"
    assert payload["primary"]["symbol"] == "PGEO"
    assert payload["primary"]["decision_grade"] == "B"
    assert payload["primary"]["readiness"] == "NEEDS_LIVE_CONFIRMATION"


def test_run_audit_endpoint_returns_artifact_health(tmp_path, monkeypatch) -> None:
    run_root = tmp_path / "runs"
    run_dir = run_root / "20260708_205047"
    run_dir.mkdir(parents=True)
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

    monkeypatch.setattr(server, "DEFAULT_RUN_ROOT", run_root)
    client = TestClient(server.app)

    response = client.get("/api/run-audit/20260708_205047?capital=1000000&max_tp_pct=0.05")

    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_version"] == "run-audit-v1"
    assert payload["overall_status"] == "NEEDS_MORNING_CONFIRMATION"
    assert payload["recommendation"]["primary"]["symbol"] == "PGEO"


def test_bandar_scan_endpoint_returns_json_safe_records(tmp_path) -> None:
    output_path = tmp_path / "bandar_scan_results.csv"
    pd.DataFrame(
        [
            {
                "symbol": "BBCA",
                "score": float("nan"),
                "net_value": float("inf"),
                "broker": "YP",
            }
        ]
    ).to_csv(output_path, index=False)

    client = TestClient(server.app)

    response = client.get("/api/bandar-scan", params={"output_path": str(output_path)})

    assert response.status_code == 200
    assert response.json() == [
        {
            "symbol": "BBCA",
            "score": None,
            "net_value": None,
            "broker": "YP",
        }
    ]


def test_live_monitor_status_reports_configuration(monkeypatch) -> None:
    monkeypatch.setenv("TELEGRAM_TOKEN", "mock_token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "mock_chat_id")
    monkeypatch.setenv("STOCKBIT_TOKEN", "mock_stockbit")

    client = TestClient(server.app)

    response = client.get("/api/live-monitor/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["running"] is False
    assert payload["telegram_configured"] is True
    assert payload["stockbit_configured"] is True
    assert payload["interval_seconds"] >= 30
    assert isinstance(payload["last_results"], list)
