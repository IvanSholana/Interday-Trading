from __future__ import annotations

import time

import pandas as pd

from .config import ScreenerConfig
from .market_data_cache import get_incremental_ohlcv_batch
from .utils import split_batches


def download_ticker_data(tickers: list[str], config: ScreenerConfig) -> dict[str, pd.DataFrame]:
    all_data: dict[str, pd.DataFrame] = {}
    batches = split_batches(tickers, config.batch_size)

    for batch_index, batch in enumerate(batches, start=1):
        print(f"Loading batch {batch_index}/{len(batches)} from local DB/API: {len(batch)} tickers")
        try:
            all_data.update(
                get_incremental_ohlcv_batch(
                    batch,
                    period=config.period,
                    interval=config.interval,
                    batch_size=config.batch_size,
                    db_path=config.market_data_db,
                    refresh=config.refresh_market_data,
                )
            )
        except Exception as exc:
            print(f"Batch failed: {exc}")
            for ticker in batch:
                all_data[ticker] = pd.DataFrame()

        if config.sleep > 0:
            time.sleep(config.sleep)

    return {ticker: _to_yfinance_columns(data) for ticker, data in all_data.items()}


def _to_yfinance_columns(data: pd.DataFrame) -> pd.DataFrame:
    if data is None or data.empty:
        return pd.DataFrame()
    rename_map = {
        "open": "Open",
        "high": "High",
        "low": "Low",
        "close": "Close",
        "adjusted_close": "Adj Close",
        "volume": "Volume",
    }
    return data.rename(columns=rename_map)
