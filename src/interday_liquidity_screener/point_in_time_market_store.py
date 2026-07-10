"""Cutoff-safe facade over cached OHLCV market data."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .market_data_cache import MarketDataCache
from .point_in_time import assert_point_in_time


class PointInTimeMarketStore:
    def __init__(self, db_path: str | Path) -> None:
        self.cache = MarketDataCache(db_path)

    def snapshot(self, ticker: str, data_cutoff_timestamp: pd.Timestamp,
                 decision_timestamp: pd.Timestamp, interval: str = "1d") -> pd.DataFrame:
        data = self.cache.load_ohlcv(ticker, interval)
        cutoff = pd.Timestamp(data_cutoff_timestamp)
        snapshot = data[data.index <= cutoff].copy()
        assert_point_in_time(snapshot, data_cutoff_timestamp=cutoff, decision_timestamp=decision_timestamp)
        return snapshot


__all__ = ["PointInTimeMarketStore"]
