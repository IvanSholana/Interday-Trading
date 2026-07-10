from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import pandas as pd
import pytest

from interday_liquidity_screener.constants import WatchlistStatus
from interday_liquidity_screener.commodity_gate import evaluate_commodity_sentiment, fetch_live_commodities
from interday_liquidity_screener.hybrid_screener import score_sector_strength, determine_status, ScoreResult
from interday_liquidity_screener.hybrid_config import HybridScreenerConfig, config_from_dict
from interday_liquidity_screener.trade_plan import TradePlanConfig, _status_reason_summary

def test_commodity_sentiment_evaluation(tmp_path, monkeypatch) -> None:
    # 1. Mock fetch_live_commodities to return a mock response
    mock_data = {
        "COAL-NEWCASTLE": {
            "symbol": "COAL-NEWCASTLE",
            "name": "Newcastle Coal",
            "last": 130.5,
            "percent": -2.5
        },
        "XAU": {
            "symbol": "XAU",
            "name": "Gold",
            "last": 2300.0,
            "percent": 0.5
        }
    }
    
    monkeypatch.setattr("interday_liquidity_screener.commodity_gate.fetch_live_commodities", lambda **kw: mock_data)
    
    # ADRO is coal,Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal Newcastle Coal is down -2.5% (below threshold of -1.5) -> should be headwind
    is_headwind, change, name = evaluate_commodity_sentiment("ADRO.JK")
    assert is_headwind is True
    assert change == -2.5
    assert name == "Newcastle Coal"
    
    # ANTM is gold, Gold is up 0.5% -> should not be headwind
    is_headwind_antm, change_antm, name_antm = evaluate_commodity_sentiment("ANTM.JK")
    assert is_headwind_antm is False
    assert change_antm == 0.5
    assert name_antm == "Gold"

    # Non-commodity stock -> should return False
    is_headwind_bbca, _, _ = evaluate_commodity_sentiment("BBCA.JK")
    assert is_headwind_bbca is False

def test_score_sector_strength_commodity_penalty(monkeypatch) -> None:
    # 1. Mock a headwind
    mock_data = {
        "COAL-NEWCASTLE": {
            "symbol": "COAL-NEWCASTLE",
            "name": "Newcastle Coal",
            "last": 130.5,
            "percent": -2.5
        }
    }
    monkeypatch.setattr("interday_liquidity_screener.commodity_gate.fetch_live_commodities", lambda **kw: mock_data)
    
    row = {"symbol": "ADRO", "sector_strength_score": 80.0, "sector_regime": "UPTREND"}
    res = score_sector_strength(row)
    
    # 80 - 20 (penalty) = 60
    assert res.score == 60.0
    assert "COMMODITY_HEADWIND" in res.flags

def test_determine_status_commodity_headwind() -> None:
    row = {"symbol": "ADRO"}
    scores = {
        "liquidity": ScoreResult(80, ()),
        "technical": ScoreResult(80, ()),
        "smart_money": ScoreResult(80, ()),
        "price_extension": ScoreResult(80, ()),
        "market_regime": ScoreResult(80, ()),
        "sector_strength": ScoreResult(60, flags=("COMMODITY_HEADWIND",)),
        "orderbook": ScoreResult(80, ()),
    }
    risk = MagicMock()
    risk.skip_reasons = []
    
    status = determine_status(row, scores, risk, [], "both", "normal_execution")
    assert status == WatchlistStatus.COMMODITY_HEADWIND

def test_status_reason_summary_metadata() -> None:
    reason, summary = _status_reason_summary("COMMODITY_HEADWIND")
    assert "commodity_headwind" in reason
    assert "global commodity" in summary.lower()


def test_smart_money_watch_path() -> None:
    # High smart money, weak technical
    row = {"symbol": "ANTM"}
    scores = {
        "liquidity": ScoreResult(80, ()),
        "technical": ScoreResult(40, ()),  # weak technical
        "smart_money": ScoreResult(75, ()), # strong smart money
        "price_extension": ScoreResult(80, ()),
        "market_regime": ScoreResult(80, ()),
        "sector_strength": ScoreResult(80, ()),
        "orderbook": ScoreResult(80, ()),
    }
    risk = MagicMock()
    risk.skip_reasons = []
    
    status = determine_status(row, scores, risk, [], "both", "normal_execution")
    assert status == WatchlistStatus.EARLY_WATCH

    # High smart money, borderline technical
    scores["technical"] = ScoreResult(50, ())
    status_borderline = determine_status(row, scores, risk, [], "both", "normal_execution")
    assert status_borderline == WatchlistStatus.READY_SOON


def test_market_regime_decoupling() -> None:
    from interday_liquidity_screener.hybrid_config import HybridScreenerConfig
    from dataclasses import replace
    
    config = HybridScreenerConfig()
    assert config.market_regime.enabled is True
    assert config.safety.hard_market_regime_risk_off is False
    
    config = replace(
        config,
        market_regime=replace(config.market_regime, enabled=False),
    )
    
    assert config.market_regime.enabled is False
    assert config.safety.hard_market_regime_risk_off is False


