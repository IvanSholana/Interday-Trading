import json
from pathlib import Path
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone, timedelta

import pytest
import pandas as pd

from interday_liquidity_screener.monitor import LiveTickerMonitor

def test_load_candidates(tmp_path):
    watchlist_file = tmp_path / "watchlist.csv"
    df = pd.DataFrame([
        {"ticker": "BBRI.JK", "trade_status": "VALID_TRADE_PLAN", "close": 5000.0, "entry_price": 4900.0, "stop_loss": 4800.0, "take_profit_1": 5150.0},
        {"ticker": "ISAT.JK", "trade_status": "SKIPPED_NOT_TRADE_CANDIDATE", "close": 1890.0},
        {"ticker": "BBCA.JK", "trade_status": "WATCH_SHORT_TERM_ACCUMULATION_AGAINST_DISTRIBUTION", "close": 6150.0, "entry_price": 6000.0}
    ])
    df.to_csv(watchlist_file, index=False)

    mon = LiveTickerMonitor(watchlist_file)
    candidates = mon.load_candidates()
    
    assert len(candidates) == 2
    assert candidates[0]["ticker"] == "BBRI"
    assert candidates[0]["trade_status"] == "VALID_TRADE_PLAN"
    assert candidates[1]["ticker"] == "BBCA"
    assert candidates[1]["trade_status"] == "WATCH_SHORT_TERM_ACCUMULATION_AGAINST_DISTRIBUTION"

def test_is_market_open():
    mon = LiveTickerMonitor("dummy.csv")
    
    # Thursday at 10:00 AM JKT
    with patch("interday_liquidity_screener.monitor.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(2026, 7, 9, 10, 0, 0, tzinfo=timezone(timedelta(hours=7)))
        assert mon.is_market_open() is True

    # Sunday at 10:00 AM JKT
    with patch("interday_liquidity_screener.monitor.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(2026, 7, 12, 10, 0, 0, tzinfo=timezone(timedelta(hours=7)))
        assert mon.is_market_open() is False

    # Thursday at 9:00 PM JKT
    with patch("interday_liquidity_screener.monitor.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(2026, 7, 9, 21, 0, 0, tzinfo=timezone(timedelta(hours=7)))
        assert mon.is_market_open() is False

def test_process_ticker_triggers(monkeypatch):
    mon = LiveTickerMonitor("dummy.csv")
    
    candidate = {
        "ticker": "BBRI",
        "close": 5000.0,
        "entry_price": 4900.0,
        "stop_loss": 4800.0,
        "take_profit_1": 5150.0,
        "take_profit_2": 5300.0
    }
    
    monkeypatch.setattr("interday_liquidity_screener.monitor.fetch_orderbook", lambda *args, **kwargs: {})
    monkeypatch.setattr("interday_liquidity_screener.monitor.normalize_orderbook_payload", lambda *args, **kwargs: {"lastprice": 4750.0})
    monkeypatch.setattr("interday_liquidity_screener.monitor.classify_orderbook", lambda *args, **kwargs: "ORDERBOOK_NEUTRAL")
    
    res = mon.process_ticker(candidate)
    assert "STOP_LOSS_TRIGGERED" in res["alerts"]
    assert res["live_price"] == 4750.0
    assert res["orderbook_status"] == "ORDERBOOK_NEUTRAL"

    monkeypatch.setattr("interday_liquidity_screener.monitor.normalize_orderbook_payload", lambda *args, **kwargs: {"lastprice": 5200.0})
    res = mon.process_ticker(candidate)
    assert "TP1_TRIGGERED" in res["alerts"]
    
    monkeypatch.setattr("interday_liquidity_screener.monitor.normalize_orderbook_payload", lambda *args, **kwargs: {"lastprice": 4850.0})
    monkeypatch.setattr("interday_liquidity_screener.monitor.classify_orderbook", lambda *args, **kwargs: "ORDERBOOK_SUPPORTIVE")
    res = mon.process_ticker(candidate)
    assert "ENTRY_ZONE_SUPPORTIVE" in res["alerts"]

def test_monitor_once_generates_json_file(tmp_path, monkeypatch):
    watchlist_file = tmp_path / "watchlist.csv"
    df = pd.DataFrame([
        {"ticker": "BBRI.JK", "trade_status": "VALID_TRADE_PLAN", "close": 5000.0, "entry_price": 4900.0, "stop_loss": 4800.0}
    ])
    df.to_csv(watchlist_file, index=False)

    status_file = tmp_path / "status.json"
    mon = LiveTickerMonitor(watchlist_file, status_file)
    
    monkeypatch.setattr("interday_liquidity_screener.monitor.fetch_orderbook", lambda *args, **kwargs: {})
    monkeypatch.setattr("interday_liquidity_screener.monitor.normalize_orderbook_payload", lambda *args, **kwargs: {"lastprice": 4950.0})
    monkeypatch.setattr("interday_liquidity_screener.monitor.classify_orderbook", lambda *args, **kwargs: "ORDERBOOK_SUPPORTIVE")
    
    mon.is_market_open = MagicMock(return_value=True)
    
    results = mon.monitor_once(bypass_market_hours=True)
    assert len(results) == 1
    assert status_file.exists()
    
    with open(status_file, "r") as f:
        data = json.load(f)
    assert len(data) == 1
    assert data[0]["ticker"] == "BBRI"
    assert data[0]["live_price"] == 4950.0

