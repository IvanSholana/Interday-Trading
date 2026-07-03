from __future__ import annotations

import time

import pandas as pd

from .config import ScreenerConfig
from .utils import split_batches


def download_ticker_data(tickers: list[str], config: ScreenerConfig) -> dict[str, pd.DataFrame]:
    import yfinance as yf

    all_data: dict[str, pd.DataFrame] = {}
    batches = split_batches(tickers, config.batch_size)

    for batch_index, batch in enumerate(batches, start=1):
        print(f"Downloading batch {batch_index}/{len(batches)}: {len(batch)} tickers")
        try:
            data = yf.download(
                tickers=batch,
                period=config.period,
                interval=config.interval,
                group_by="ticker",
                auto_adjust=False,
                progress=False,
                threads=True,
            )

            if len(batch) == 1:
                all_data[batch[0]] = data
            else:
                top_level_columns = set(data.columns.get_level_values(0))
                for ticker in batch:
                    all_data[ticker] = data[ticker] if ticker in top_level_columns else pd.DataFrame()
        except Exception as exc:
            print(f"Batch failed: {exc}")
            for ticker in batch:
                all_data[ticker] = pd.DataFrame()

        if config.sleep > 0:
            time.sleep(config.sleep)

    return all_data
