from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import sqlite3
from typing import Any

import pandas as pd

DEFAULT_MARKET_DATA_DB = Path("data/cache/market_data.sqlite")
OHLCV_COLUMNS = ["open", "high", "low", "close", "adjusted_close", "volume"]

# IDX market closes at 16:15 WIB (UTC+7). We add a 15-minute buffer to be safe.
_IDX_MARKET_CLOSE_HOUR_WIB = 16
_IDX_MARKET_CLOSE_MINUTE_WIB = 30  # 16:15 + 15 min buffer = 16:30
_WIB = timezone(timedelta(hours=7))


def normalize_ohlcv_frame(data: pd.DataFrame | None, ticker: str | None = None) -> pd.DataFrame:
    if data is None or data.empty:
        return pd.DataFrame(columns=OHLCV_COLUMNS)

    normalized = data.copy()
    if isinstance(normalized.columns, pd.MultiIndex):
        if ticker and ticker in normalized.columns.get_level_values(-1):
            normalized = normalized.xs(ticker, axis=1, level=-1)
        elif ticker and ticker in normalized.columns.get_level_values(0):
            normalized = normalized.xs(ticker, axis=1, level=0)
        else:
            normalized.columns = normalized.columns.get_level_values(0)

    if "Date" in normalized.columns:
        normalized["Date"] = pd.to_datetime(normalized["Date"], errors="coerce")
        normalized = normalized.set_index("Date")

    rename_map = {
        "Open": "open",
        "High": "high",
        "Low": "low",
        "Close": "close",
        "Adj Close": "adjusted_close",
        "Adj_Close": "adjusted_close",
        "Volume": "volume",
    }
    normalized = normalized.rename(columns=rename_map)
    normalized.columns = [str(column).strip().lower().replace(" ", "_") for column in normalized.columns]
    keep = [column for column in OHLCV_COLUMNS if column in normalized.columns]
    if not keep:
        return pd.DataFrame(columns=OHLCV_COLUMNS)

    normalized.index = pd.to_datetime(normalized.index, errors="coerce")
    normalized = normalized[~normalized.index.isna()]
    normalized.index = normalized.index.tz_localize(None).normalize()
    normalized = normalized.sort_index()
    normalized = normalized[keep].copy()
    for column in keep:
        normalized[column] = pd.to_numeric(normalized[column], errors="coerce")
    normalized = normalized.dropna(subset=["open", "high", "low", "close"], how="any")
    normalized.index.name = "date"
    return normalized


def period_start_date(period: str, today: date | None = None) -> date | None:
    text = str(period or "").strip().lower()
    if not text or text == "max":
        return None
    today = today or date.today()
    try:
        amount = int(text[:-2]) if text.endswith(("mo", "wk")) else int(text[:-1])
    except ValueError:
        return None
    if text.endswith("d"):
        return today - timedelta(days=amount)
    if text.endswith("wk"):
        return today - timedelta(weeks=amount)
    if text.endswith("mo"):
        return (pd.Timestamp(today) - pd.DateOffset(months=amount)).date()
    if text.endswith("y"):
        return (pd.Timestamp(today) - pd.DateOffset(years=amount)).date()
    return None


class MarketDataCache:
    def __init__(self, db_path: str | Path = DEFAULT_MARKET_DATA_DB) -> None:
        self.db_path = Path(db_path)

    def _connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.db_path)
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS ohlcv (
                ticker TEXT NOT NULL,
                interval TEXT NOT NULL,
                date TEXT NOT NULL,
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                adjusted_close REAL,
                volume REAL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (ticker, interval, date)
            )
            """
        )
        connection.execute("CREATE INDEX IF NOT EXISTS idx_ohlcv_ticker_interval_date ON ohlcv(ticker, interval, date)")
        return connection

    def load_ohlcv(
        self,
        ticker: str,
        interval: str = "1d",
        start_date: str | date | None = None,
    ) -> pd.DataFrame:
        params: list[Any] = [ticker, interval]
        where = "ticker = ? AND interval = ?"
        if start_date is not None:
            where += " AND date >= ?"
            params.append(pd.Timestamp(start_date).date().isoformat())
        query = f"""
            SELECT date, open, high, low, close, adjusted_close, volume
            FROM ohlcv
            WHERE {where}
            ORDER BY date
        """
        with self._connect() as connection:
            rows = pd.read_sql_query(query, connection, params=params)
        if rows.empty:
            return pd.DataFrame(columns=OHLCV_COLUMNS)
        rows["date"] = pd.to_datetime(rows["date"], errors="coerce")
        rows = rows.dropna(subset=["date"]).set_index("date")
        rows.index = rows.index.normalize()
        rows.index.name = "date"
        return rows[OHLCV_COLUMNS]

    def coverage(self, ticker: str, interval: str = "1d") -> tuple[date | None, date | None]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT MIN(date), MAX(date) FROM ohlcv WHERE ticker = ? AND interval = ?",
                (ticker, interval),
            ).fetchone()
        if not row or not row[0] or not row[1]:
            return None, None
        return date.fromisoformat(row[0]), date.fromisoformat(row[1])

    def last_bar_updated_at(self, ticker: str, bar_date: date, interval: str = "1d") -> datetime | None:
        """Return the updated_at timestamp (UTC) for a specific bar, or None."""
        with self._connect() as connection:
            row = connection.execute(
                "SELECT updated_at FROM ohlcv WHERE ticker = ? AND interval = ? AND date = ?",
                (ticker, interval, bar_date.isoformat()),
            ).fetchone()
        if not row or not row[0]:
            return None
        try:
            return datetime.fromisoformat(row[0])
        except (ValueError, TypeError):
            return None

    def save_ohlcv(self, ticker: str, data: pd.DataFrame, interval: str = "1d") -> int:
        normalized = normalize_ohlcv_frame(data, ticker)
        if normalized.empty:
            return 0
        rows = []
        for index, row in normalized.iterrows():
            rows.append(
                (
                    ticker,
                    interval,
                    pd.Timestamp(index).date().isoformat(),
                    _optional_float(row.get("open")),
                    _optional_float(row.get("high")),
                    _optional_float(row.get("low")),
                    _optional_float(row.get("close")),
                    _optional_float(row.get("adjusted_close")),
                    _optional_float(row.get("volume")),
                )
            )
        with self._connect() as connection:
            connection.executemany(
                """
                INSERT INTO ohlcv (ticker, interval, date, open, high, low, close, adjusted_close, volume)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(ticker, interval, date) DO UPDATE SET
                    open = excluded.open,
                    high = excluded.high,
                    low = excluded.low,
                    close = excluded.close,
                    adjusted_close = excluded.adjusted_close,
                    volume = excluded.volume,
                    updated_at = CURRENT_TIMESTAMP
                """,
                rows,
            )
        return len(rows)


def _optional_float(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value)


# ---------------------------------------------------------------------------
# Data source selection: Stockbit (preferred) → yfinance (fallback)
# ---------------------------------------------------------------------------

_DATA_SOURCE: str = "stockbit"  # "stockbit" or "yfinance"


def _download_stockbit_ohlcv(
    ticker: str,
    period: str | None = None,
    start: date | None = None,
    end: date | None = None,
) -> pd.DataFrame:
    """Fetch daily OHLCV from Stockbit Exodus API for a single ticker.

    Returns a DataFrame compatible with the cache (DatetimeIndex + OHLCV columns).
    """
    from .stockbit_market_data import (
        fetch_daily_ohlcv_stockbit,
        daily_bars_to_dataframe,
        StockbitFetchConfig,
    )
    # Convert .JK ticker to plain ticker for Stockbit
    clean_ticker = ticker.replace(".JK", "")

    # Determine days from period or date range
    if start is not None and end is not None:
        days = (end - start).days + 1
    elif period:
        days_map = {"1mo": 30, "3mo": 90, "6mo": 180, "1y": 365, "2y": 730, "max": 500}
        days = days_map.get(period, 365)
    else:
        days = 365

    config = StockbitFetchConfig(
        min_delay_sec=2.0,
        max_delay_sec=5.0,
        max_requests_per_session=200,
        simulate_session_open=False,  # Skip session open for batch efficiency
    )

    try:
        bars = fetch_daily_ohlcv_stockbit(clean_ticker, days=days, config=config)
        if not bars:
            return pd.DataFrame()
        df = daily_bars_to_dataframe(bars)
        # Filter by start/end if specified
        if start is not None and not df.empty:
            df = df[df.index >= pd.Timestamp(start)]
        if end is not None and not df.empty:
            df = df[df.index <= pd.Timestamp(end)]
        return df
    except Exception:
        return pd.DataFrame()


def _download_stockbit_ohlcv_batch(
    tickers: list[str],
    period: str | None = None,
    start: date | None = None,
    end: date | None = None,
) -> dict[str, pd.DataFrame]:
    """Fetch daily OHLCV from Stockbit for multiple tickers with pacing."""
    from .stockbit_market_data import (
        fetch_daily_ohlcv_batch_stockbit,
        daily_bars_to_dataframe,
        StockbitFetchConfig,
        reset_session,
    )

    if start is not None and end is not None:
        days = (end - start).days + 1
    elif period:
        days_map = {"1mo": 30, "3mo": 90, "6mo": 180, "1y": 365, "2y": 730, "max": 500}
        days = days_map.get(period, 365)
    else:
        days = 365

    clean_tickers = [t.replace(".JK", "") for t in tickers]
    config = StockbitFetchConfig(
        min_delay_sec=2.0,
        max_delay_sec=5.0,
        max_requests_per_session=len(clean_tickers) + 10,
        simulate_session_open=True,
    )

    reset_session()
    try:
        raw_results = fetch_daily_ohlcv_batch_stockbit(clean_tickers, days=days, config=config)
    except Exception:
        return {}

    results: dict[str, pd.DataFrame] = {}
    for clean_tkr, bars in raw_results.items():
        yahoo_tkr = f"{clean_tkr}.JK"
        if bars:
            df = daily_bars_to_dataframe(bars)
            if start is not None and not df.empty:
                df = df[df.index >= pd.Timestamp(start)]
            results[yahoo_tkr] = df
        else:
            results[yahoo_tkr] = pd.DataFrame()
    return results


def download_yfinance_ohlcv(
    tickers: str | list[str],
    period: str | None = None,
    interval: str = "1d",
    start: str | date | None = None,
    end: str | date | None = None,
    threads: bool = True,
) -> pd.DataFrame:
    import yfinance as yf

    kwargs: dict[str, Any] = {
        "tickers": tickers,
        "interval": interval,
        "auto_adjust": False,
        "progress": False,
        "threads": threads,
        "group_by": "ticker",
    }
    if start is not None:
        kwargs["start"] = pd.Timestamp(start).date().isoformat()
        if end is not None:
            kwargs["end"] = pd.Timestamp(end).date().isoformat()
    else:
        kwargs["period"] = period
    return yf.download(**kwargs)


def _fetch_single_ticker(
    ticker: str,
    period: str | None = None,
    interval: str = "1d",
    start: date | None = None,
    end: date | None = None,
) -> pd.DataFrame:
    """Fetch OHLCV for a single ticker using the configured data source.

    Tries Stockbit first (if configured and token available), falls back to yfinance.
    Logs a warning when falling back so downstream consumers know the data source.
    """
    if _DATA_SOURCE == "stockbit" and interval == "1d":
        try:
            from .stockbit_collector import get_stockbit_token
            token = get_stockbit_token()
            if token:
                df = _download_stockbit_ohlcv(ticker, period=period, start=start, end=end)
                if not df.empty:
                    return df
                import logging
                logging.getLogger(__name__).warning(
                    "DATA_SOURCE_FALLBACK: Stockbit returned empty for %s — falling back to yfinance. "
                    "Prices may differ from IDX real-time.",
                    ticker,
                )
            else:
                import logging
                logging.getLogger(__name__).warning(
                    "DATA_SOURCE_FALLBACK: Stockbit token unavailable — using yfinance for %s. "
                    "Check STOCKBIT_TOKEN in .env.",
                    ticker,
                )
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning(
                "DATA_SOURCE_FALLBACK: Stockbit error for %s (%s) — using yfinance.",
                ticker, exc,
            )
    return download_yfinance_ohlcv(
        ticker, period=period, interval=interval,
        start=start, end=end, threads=False,
    )


def _today_bar_is_stale(cache: MarketDataCache, ticker: str, today: date, interval: str = "1d") -> bool:
    """Return True if the cached bar for *today* was written before IDX market close.

    This detects the common case where yfinance returned a partial intraday bar
    early in the day (or even pre-market) and the cache still holds that stale
    snapshot when the pipeline runs in the evening.

    A bar is NOT considered stale if it was written very recently (within the
    last 60 seconds) because that means it was just fetched in this session.
    """
    updated = cache.last_bar_updated_at(ticker, today, interval)
    if updated is None:
        return False  # no bar yet — will be fetched fresh anyway
    # updated_at is stored via sqlite CURRENT_TIMESTAMP which is UTC.
    # Convert the comparison threshold to UTC as well.
    from datetime import timezone as tz
    now_utc = datetime.now(tz.utc).replace(tzinfo=None)
    naive_updated = updated.replace(tzinfo=None) if updated.tzinfo else updated
    # If bar was written in the last 60 seconds, it was just fetched — not stale.
    if (now_utc - naive_updated).total_seconds() < 60:
        return False
    # IDX market closes at 16:30 WIB = 09:30 UTC.
    close_threshold_utc = datetime(
        today.year, today.month, today.day,
        _IDX_MARKET_CLOSE_HOUR_WIB - 7, _IDX_MARKET_CLOSE_MINUTE_WIB,
    )
    return naive_updated < close_threshold_utc


def get_incremental_ohlcv(
    ticker: str,
    period: str,
    interval: str = "1d",
    db_path: str | Path = DEFAULT_MARKET_DATA_DB,
    refresh: bool = False,
) -> pd.DataFrame:
    cache = MarketDataCache(db_path)
    today = date.today()
    required_start = period_start_date(period, today)
    first_cached, last_cached = cache.coverage(ticker, interval)
    is_weekend = today.weekday() >= 5

    fetch_full_period = refresh or first_cached is None
    if required_start is not None and first_cached is not None and first_cached > required_start:
        fetch_full_period = True

    if fetch_full_period:
        fetched = _fetch_single_ticker(ticker, period=period, interval=interval)
        cache.save_ohlcv(ticker, fetched, interval)
    elif last_cached is not None:
        next_date = last_cached + timedelta(days=1)
        end_date = today + timedelta(days=1)
        # Skip fetch on weekends if we already have the last trading day
        skip_weekend = is_weekend and (today - last_cached <= timedelta(days=2))
        if next_date <= today and not skip_weekend:
            fetched = _fetch_single_ticker(ticker, interval=interval, start=next_date, end=end_date)
            cache.save_ohlcv(ticker, fetched, interval)
        elif last_cached == today and _today_bar_is_stale(cache, ticker, today, interval):
            fetched = _fetch_single_ticker(ticker, interval=interval, start=today, end=end_date)
            cache.save_ohlcv(ticker, fetched, interval)

    return cache.load_ohlcv(ticker, interval, start_date=required_start)


def get_incremental_ohlcv_batch(
    tickers: list[str],
    period: str,
    interval: str = "1d",
    batch_size: int = 50,
    db_path: str | Path = DEFAULT_MARKET_DATA_DB,
    refresh: bool = False,
) -> dict[str, pd.DataFrame]:
    results: dict[str, pd.DataFrame] = {}
    cache = MarketDataCache(db_path)
    today = date.today()
    required_start = period_start_date(period, today)
    stale_full: list[str] = []
    stale_incremental: dict[date, list[str]] = {}
    stale_today: list[str] = []

    # On weekends/holidays, the last trading day is already in cache.
    # Don't attempt incremental fetches that would hit the API for nothing.
    is_weekend = today.weekday() >= 5  # Saturday=5, Sunday=6

    for ticker in tickers:
        first_cached, last_cached = cache.coverage(ticker, interval)
        if refresh or first_cached is None or (required_start is not None and first_cached > required_start):
            stale_full.append(ticker)
        elif last_cached is not None and last_cached < today:
            # Skip incremental if it's a weekend and cache has Friday's data
            if is_weekend and last_cached.weekday() == 4:
                pass  # Cache already has Friday — no new data on weekend
            elif is_weekend and today - last_cached <= timedelta(days=2):
                pass  # Cache is within weekend gap — skip
            else:
                stale_incremental.setdefault(last_cached + timedelta(days=1), []).append(ticker)
        elif last_cached == today and _today_bar_is_stale(cache, ticker, today, interval):
            stale_today.append(ticker)

    _fetch_and_store_batches(cache, stale_full, period, interval, batch_size)
    for start_date, stale_tickers in stale_incremental.items():
        _fetch_and_store_batches(
            cache,
            stale_tickers,
            period,
            interval,
            batch_size,
            start=start_date,
            end=today + timedelta(days=1),
        )
    if stale_today:
        _fetch_and_store_batches(
            cache,
            stale_today,
            period,
            interval,
            batch_size,
            start=today,
            end=today + timedelta(days=1),
        )

    for ticker in tickers:
        results[ticker] = cache.load_ohlcv(ticker, interval, start_date=required_start)
    return results


def _fetch_and_store_batches(
    cache: MarketDataCache,
    tickers: list[str],
    period: str,
    interval: str,
    batch_size: int,
    start: date | None = None,
    end: date | None = None,
) -> None:
    if not tickers:
        return

    # Try Stockbit batch first for daily data
    if _DATA_SOURCE == "stockbit" and interval == "1d":
        try:
            from .stockbit_collector import get_stockbit_token
            token = get_stockbit_token()
        except Exception:
            token = ""
        if token:
            print(f"Fetching {len(tickers)} tickers from Stockbit (daily)...")
            stockbit_results = _download_stockbit_ohlcv_batch(tickers, period=period, start=start, end=end)
            fetched_from_stockbit: set[str] = set()
            for ticker, df in stockbit_results.items():
                if not df.empty:
                    cache.save_ohlcv(ticker, df, interval)
                    fetched_from_stockbit.add(ticker)
            remaining = [t for t in tickers if t not in fetched_from_stockbit]
            if not remaining:
                return
            import logging
            logging.getLogger(__name__).warning(
                "DATA_SOURCE_FALLBACK: Stockbit got %d/%d. Falling back to yfinance for %d tickers: %s",
                len(fetched_from_stockbit), len(tickers), len(remaining),
                remaining[:5],
            )
            tickers = remaining

    # Fallback: yfinance batch
    batches = [tickers[index : index + batch_size] for index in range(0, len(tickers), batch_size)]
    mode = "incremental" if start else "full"
    for batch_index, batch in enumerate(batches, start=1):
        print(f"Downloading {mode} OHLCV batch {batch_index}/{len(batches)}: {len(batch)} tickers (yfinance)")
        data = download_yfinance_ohlcv(batch, period=period, interval=interval, start=start, end=end, threads=True)
        if data is None or data.empty:
            continue
        if len(batch) == 1:
            cache.save_ohlcv(batch[0], data, interval)
            continue
        top_level = set(data.columns.get_level_values(0)) if isinstance(data.columns, pd.MultiIndex) else set()
        for ticker in batch:
            ticker_data = data[ticker] if ticker in top_level else pd.DataFrame()
            cache.save_ohlcv(ticker, ticker_data, interval)
