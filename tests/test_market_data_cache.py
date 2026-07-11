from __future__ import annotations

from datetime import date

import pandas as pd

from interday_liquidity_screener import market_data_cache
from interday_liquidity_screener.market_data_cache import MarketDataCache, get_incremental_ohlcv


def sample_ohlcv() -> pd.DataFrame:
    today = pd.Timestamp(date.today())
    return pd.DataFrame(
        {
            "Open": [100.0],
            "High": [105.0],
            "Low": [99.0],
            "Close": [102.0],
            "Adj Close": [102.0],
            "Volume": [1_000_000],
        },
        index=[today],
    )


def test_market_data_cache_saves_and_loads_ohlcv(tmp_path) -> None:
    db_path = tmp_path / "market.sqlite"
    cache = MarketDataCache(db_path)

    assert cache.save_ohlcv("BBRI.JK", sample_ohlcv()) == 1
    loaded = cache.load_ohlcv("BBRI.JK")

    assert list(loaded.columns) == ["open", "high", "low", "close", "adjusted_close", "volume"]
    assert loaded.iloc[0]["close"] == 102.0
    assert cache.coverage("BBRI.JK") == (date.today(), date.today())


def test_get_incremental_ohlcv_fetches_empty_cache_once(tmp_path, monkeypatch) -> None:
    calls = []

    def fake_download(*args, **kwargs):
        calls.append((args, kwargs))
        return sample_ohlcv()

    monkeypatch.setattr(market_data_cache, "download_yfinance_ohlcv", fake_download)
    # Force yfinance path so Stockbit doesn't bypass the mock
    monkeypatch.setattr(market_data_cache, "_DATA_SOURCE", "yfinance")

    first = get_incremental_ohlcv("BBCA.JK", "max", db_path=tmp_path / "market.sqlite")
    second = get_incremental_ohlcv("BBCA.JK", "max", db_path=tmp_path / "market.sqlite")

    assert len(calls) == 1
    assert first.iloc[0]["close"] == 102.0
    assert second.iloc[0]["close"] == 102.0
