import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import pandas as pd

from interday_liquidity_screener.bandar_tracker import (
    BandarTrackerConfig,
    aggregate_bandar_accum,
    run_bandar_scan
)

def test_config_loading_and_defaults(tmp_path):
    config = BandarTrackerConfig.load_from_file(tmp_path / "missing.json")
    assert config.whitelist_brokers == ["AK", "ZP", "BK", "XL", "RX", "KZ", "YJ"]
    assert config.track_investor_type == "INVESTOR_TYPE_FOREIGN"

    cfg_file = tmp_path / "tracker_config.json"
    with open(cfg_file, "w", encoding="utf-8") as f:
        json.dump({
            "whitelist_brokers": ["ZP", "XL"],
            "track_investor_type": "INVESTOR_TYPE_ALL",
            "track_period": "RT_PERIOD_LAST_3_DAYS",
            "min_accumulation_value": 500000000.0
        }, f)
        
    config = BandarTrackerConfig.load_from_file(cfg_file)
    assert config.whitelist_brokers == ["ZP", "XL"]
    assert config.track_investor_type == "INVESTOR_TYPE_ALL"
    assert config.track_period == "RT_PERIOD_LAST_3_DAYS"
    assert config.min_accumulation_value == 500000000.0

def test_aggregate_bandar_accum():
    payload = {
        "data": {
            "broker_activity_transaction": {
                "brokers_buy": [
                    {
                        "stock_code": "MAPI",
                        "broker_code": "XL",
                        "value": 1500000000,
                        "lot": 10000,
                        "freq": 5,
                        "company_detail": {
                            "corpaction": {"active": True},
                            "notation": ["X"]
                        }
                    },
                    {
                        "stock_code": "MAPI",
                        "broker_code": "ZP",
                        "value": 2500000000,
                        "lot": 15000,
                        "freq": 10,
                        "company_detail": {
                            "corpaction": {"active": True},
                            "notation": ["X"]
                        }
                    },
                    {
                        "stock_code": "BBRI",
                        "broker_code": "AK",
                        "value": 5000000000,
                        "lot": 10000,
                        "freq": 15,
                        "company_detail": {
                            "corpaction": {"active": False},
                            "notation": []
                        }
                    }
                ],
                "brokers_sell": []
            }
        }
    }
    
    df = aggregate_bandar_accum(payload)
    assert len(df) == 2
    
    mapi_row = df[df["ticker"] == "MAPI.JK"].iloc[0]
    assert mapi_row["net_buy_value"] == 4000000000.0
    assert mapi_row["net_buy_lot"] == 25000.0
    assert mapi_row["frequency"] == 15
    assert mapi_row["corp_action_active"] == True
    assert mapi_row["avg_price"] == 1600.0

    bbri_row = df[df["ticker"] == "BBRI.JK"].iloc[0]
    assert bbri_row["net_buy_value"] == 5000000000.0
    assert bbri_row["avg_price"] == 5000.0

def test_run_bandar_scan_caching_and_filter(tmp_path, monkeypatch):
    config_file = tmp_path / "tracker_config.json"
    with open(config_file, "w", encoding="utf-8") as f:
        json.dump({
            "whitelist_brokers": ["XL"],
            "track_investor_type": "INVESTOR_TYPE_FOREIGN",
            "track_period": "RT_PERIOD_LAST_1_DAY",
            "min_accumulation_value": 2000000000.0
        }, f)
        
    payload = {
        "data": {
            "broker_activity_transaction": {
                "brokers_buy": [
                    {
                        "stock_code": "MAPI",
                        "broker_code": "XL",
                        "value": 3000000000,
                        "lot": 20000,
                        "freq": 8,
                        "company_detail": {"corpaction": {"active": False}, "notation": []}
                    },
                    {
                        "stock_code": "ARTO",
                        "broker_code": "XL",
                        "value": 1500000000,
                        "lot": 15000,
                        "freq": 3,
                        "company_detail": {"corpaction": {"active": False}, "notation": []}
                    }
                ]
            }
        }
    }
    
    mock_fetch = MagicMock(return_value=payload)
    monkeypatch.setattr("interday_liquidity_screener.bandar_tracker.fetch_broker_activity_multi", mock_fetch)
    
    output_file = tmp_path / "candidates.csv"
    
    df = run_bandar_scan(config_file, output_file, force_refresh=True)
    assert len(df) == 1
    assert df.iloc[0]["ticker"] == "MAPI.JK"
    assert mock_fetch.call_count == 1
    
    mock_fetch.reset_mock()
    df2 = run_bandar_scan(config_file, output_file, force_refresh=False)
    assert len(df2) == 1
    assert df2.iloc[0]["ticker"] == "MAPI.JK"
    assert mock_fetch.call_count == 0
