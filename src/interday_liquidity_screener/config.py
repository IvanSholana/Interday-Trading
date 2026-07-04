from __future__ import annotations

from dataclasses import dataclass

from .market_data_cache import DEFAULT_MARKET_DATA_DB


@dataclass(frozen=True)
class ScreenerConfig:
    period: str = "3mo"
    interval: str = "1d"
    min_value: float = 5_000_000_000
    min_avg_value_20d: float = 5_000_000_000
    min_median_value_20d: float = 3_000_000_000
    min_volume_ratio: float = 1.0
    min_active_days_20d: int = 15
    max_zero_volume_days_20d: int = 3
    max_return_5d: float = 0.10
    batch_size: int = 50
    sleep: float = 0.0
    market_data_db: str = str(DEFAULT_MARKET_DATA_DB)
    refresh_market_data: bool = False
