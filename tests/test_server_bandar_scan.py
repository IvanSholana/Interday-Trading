from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock
import pandas as pd
from fastapi.testclient import TestClient

from interday_liquidity_screener import server

def test_bandar_scan_endpoints(tmp_path, monkeypatch) -> None:
    mock_df = pd.DataFrame([
        {
            "ticker": "MAPI.JK",
            "net_buy_value": 3000000000.0,
            "net_buy_lot": 20000.0,
            "frequency": 8,
            "corp_action_active": False,
            "special_notations": "",
            "avg_price": 1500.0
        }
    ])
    
    mock_run = MagicMock(return_value=mock_df)
    monkeypatch.setattr("interday_liquidity_screener.bandar_tracker.run_bandar_scan", mock_run)
    
    client = TestClient(server.app)
    
    output_csv = tmp_path / "bandar_results.csv"
    
    # Trigger scan when file doesn't exist
    response = client.get(f"/api/bandar-scan?output_path={output_csv}")
    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["ticker"] == "MAPI.JK"
    assert mock_run.call_count == 1

    # Trigger fresh scan via POST
    mock_run.reset_mock()
    post_payload = {
        "config_path": "config/bandar_tracker.json",
        "output_path": str(output_csv),
        "force_refresh": True,
        "investor_type": "INVESTOR_TYPE_FOREIGN",
        "period": "RT_PERIOD_LAST_7_DAYS"
    }
    response_post = client.post("/api/bandar-scan/run", json=post_payload)
    assert response_post.status_code == 200
    payload_post = response_post.json()
    assert len(payload_post) == 1
    assert payload_post[0]["ticker"] == "MAPI.JK"
    assert mock_run.call_count == 1
