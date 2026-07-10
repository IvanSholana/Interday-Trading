import json
from pathlib import Path
import pandas as pd
import pytest
from unittest.mock import MagicMock

from interday_liquidity_screener.monitor import LiveTickerMonitor

def test_load_candidates_with_final_status(tmp_path) -> None:
    csv_file = tmp_path / "hybrid_watchlist.csv"
    df = pd.DataFrame([
        {
            "ticker": "BBCA.JK",
            "final_status": "EXECUTION_READY",
            "close": 10000.0,
            "entry_price": 9900.0,
            "stop_loss": 9800.0,
            "take_profit_1": 10100.0,
            "take_profit_2": 10200.0,
            "trade_reason": "Accumulation"
        },
        {
            "ticker": "ANTM.JK",
            "trade_status": "READY_SOON",  # trade_status instead of final_status
            "close": 1500.0,
            "entry_price": 1490.0,
            "stop_loss": 1450.0,
            "take_profit_1": 1550.0,
            "take_profit_2": 1600.0,
            "trade_reason": "Smart Money Watch"
        },
        {
            "ticker": "GOTO.JK",
            "final_status": "SKIP",  # Non-valid status
            "close": 50.0,
        }
    ])
    df.to_csv(csv_file, index=False)

    monitor = LiveTickerMonitor(watchlist_path=csv_file)
    candidates = monitor.load_candidates()

    assert len(candidates) == 2
    assert candidates[0]["ticker"] == "BBCA"
    assert candidates[0]["trade_status"] == "EXECUTION_READY"
    assert candidates[1]["ticker"] == "ANTM"
    assert candidates[1]["trade_status"] == "READY_SOON"


def test_telegram_alert_dispatch(tmp_path, monkeypatch) -> None:
    csv_file = tmp_path / "hybrid_watchlist.csv"
    pd.DataFrame([]).to_csv(csv_file, index=False)

    monitor = LiveTickerMonitor(watchlist_path=csv_file)
    
    # Configure mock environment
    monkeypatch.setenv("TELEGRAM_TOKEN", "mock_token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "mock_chat_id")

    mock_response = MagicMock()
    mock_response.status = 200
    mock_urlopen = MagicMock(return_value=mock_response)
    monkeypatch.setattr("urllib.request.urlopen", mock_urlopen)

    res = {
        "ticker": "ADRO",
        "live_price": 2500.0,
        "entry_price": 2520.0,
        "stop_loss": 2450.0,
        "take_profit_1": 2600.0,
        "orderbook_status": "ORDERBOOK_SUPPORTIVE"
    }

    # Trigger alert
    monitor.send_telegram_alert(res, "ENTRY_ZONE_SUPPORTIVE")
    
    # Verify urlopen was called once
    assert mock_urlopen.call_count == 1
    args, kwargs = mock_urlopen.call_args
    req = args[0]
    
    assert req.full_url == "https://api.telegram.org/botmock_token/sendMessage"
    assert req.get_header("Content-type") == "application/json"
    
    payload = json.loads(req.data.decode("utf-8"))
    assert payload["chat_id"] == "mock_chat_id"
    assert "ADRO" in payload["text"]
    assert "ENTRY BUY TRIGGER" in payload["text"]


def test_alert_spam_prevention(tmp_path, monkeypatch) -> None:
    csv_file = tmp_path / "hybrid_watchlist.csv"
    pd.DataFrame([]).to_csv(csv_file, index=False)

    monitor = LiveTickerMonitor(watchlist_path=csv_file)
    
    monkeypatch.setenv("TELEGRAM_TOKEN", "mock_token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "mock_chat_id")

    mock_response = MagicMock()
    mock_response.status = 200
    mock_urlopen = MagicMock(return_value=mock_response)
    monkeypatch.setattr("urllib.request.urlopen", mock_urlopen)

    # Mock process_ticker and load_candidates
    monitor.load_candidates = MagicMock(return_value=[{
        "ticker": "BBRI",
        "entry_price": 4500,
        "stop_loss": 4400,
        "take_profit_1": 4600,
        "take_profit_2": 4700,
    }])
    
    monitor.process_ticker = MagicMock(return_value={
        "ticker": "BBRI",
        "live_price": 4505,
        "entry_price": 4500,
        "stop_loss": 4400,
        "take_profit_1": 4600,
        "take_profit_2": 4700,
        "orderbook_status": "ORDERBOOK_SUPPORTIVE",
        "alerts": ["ENTRY_ZONE_SUPPORTIVE"]
    })

    monitor.is_market_open = MagicMock(return_value=True)

    # First monitoring pass: triggers alert and sends to telegram
    monitor.monitor_once(bypass_market_hours=True)
    assert mock_urlopen.call_count == 1
    assert "BBRI_ENTRY_ZONE_SUPPORTIVE" in monitor.sent_alerts

    # Second monitoring pass: should NOT send again because it is cached
    monitor.monitor_once(bypass_market_hours=True)
    assert mock_urlopen.call_count == 1  # Still 1
