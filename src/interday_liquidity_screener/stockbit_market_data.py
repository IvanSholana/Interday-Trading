"""
stockbit_market_data.py – Stockbit Exodus API data fetcher with anti-detection.

Fetches daily OHLCV+foreign flow and intraday 1-min candles from Stockbit's
internal Exodus API. Implements human-like request pacing, aggressive caching,
and session simulation to minimize detection risk.

Usage:
    from interday_liquidity_screener.stockbit_market_data import (
        fetch_daily_ohlcv_stockbit,
        fetch_daily_ohlcv_batch_stockbit,
        fetch_intraday_candles,
        compute_vwap,
        compute_opening_gap,
        compute_foreign_flow_summary,
    )
"""
from __future__ import annotations

import json
import logging
import random
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pandas as pd

from .stockbit_collector import get_stockbit_token, _headers

logger = logging.getLogger(__name__)

_WIB = timezone(timedelta(hours=7))

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class StockbitFetchConfig:
    """Anti-detection and fetch behavior configuration."""
    # Delay between requests (random uniform within range)
    min_delay_sec: float = 3.0
    max_delay_sec: float = 8.0
    # Maximum requests per session (safety breaker)
    max_requests_per_session: int = 80
    # Request timeout
    timeout_sec: int = 15
    # Retry on transient errors
    max_retries: int = 2
    retry_backoff_sec: float = 5.0
    # Whether to simulate session open (fetch /user-setting first)
    simulate_session_open: bool = True


DEFAULT_FETCH_CONFIG = StockbitFetchConfig()


# ---------------------------------------------------------------------------
# Rate limiter / session state
# ---------------------------------------------------------------------------

class _SessionState:
    """Tracks request count and timing for the current fetch session."""
    def __init__(self) -> None:
        self.request_count: int = 0
        self.session_opened: bool = False
        self.last_request_time: float = 0.0
        self.max_requests: int = 200  # Dynamic limit, can be overridden per session

    def reset(self) -> None:
        self.request_count = 0
        self.session_opened = False
        self.last_request_time = 0.0
        self.max_requests = 200


_state = _SessionState()


def _human_delay(config: StockbitFetchConfig) -> None:
    """Sleep a random human-like duration between requests."""
    elapsed = time.time() - _state.last_request_time
    min_wait = max(0, config.min_delay_sec - elapsed)
    max_wait = max(min_wait, config.max_delay_sec - elapsed)
    if max_wait > 0:
        delay = random.uniform(min_wait, max_wait)
        time.sleep(delay)


def _ensure_session(config: StockbitFetchConfig, token: str) -> None:
    """Simulate user opening app by fetching config endpoint first."""
    if _state.session_opened or not config.simulate_session_open:
        return
    try:
        _raw_get("https://exodus.stockbit.com/user-setting/configurations", token, config)
    except Exception:
        pass  # Non-critical — session open is best-effort
    _state.session_opened = True
    time.sleep(random.uniform(1.5, 3.0))


def _raw_get(url: str, token: str, config: StockbitFetchConfig) -> dict[str, Any]:
    """Perform a single GET request with retry and rate limiting."""
    if _state.request_count >= config.max_requests_per_session:
        # Auto-reset session instead of hard-failing — allows long pipelines to continue
        logger.info("Session auto-reset at %d requests (limit %d)", _state.request_count, config.max_requests_per_session)
        _state.request_count = 0
        _state.session_opened = False

    headers = _headers(token)
    last_error: Exception | None = None

    for attempt in range(config.max_retries + 1):
        if attempt > 0:
            time.sleep(config.retry_backoff_sec * attempt)

        _human_delay(config)
        try:
            req = Request(url, headers=headers, method="GET")
            resp = urlopen(req, timeout=config.timeout_sec)
            _state.request_count += 1
            _state.last_request_time = time.time()
            raw = resp.read().decode("utf-8")
            return json.loads(raw)
        except HTTPError as exc:
            _state.last_request_time = time.time()
            if exc.code == 429:
                # Rate limited — back off harder
                logger.warning("Rate limited (429) on %s, backing off", url)
                time.sleep(config.retry_backoff_sec * (attempt + 2))
                last_error = exc
                continue
            if exc.code in {401, 403}:
                raise RuntimeError(
                    f"Auth error ({exc.code}) calling Stockbit API. Token may be expired."
                ) from exc
            last_error = exc
        except Exception as exc:
            _state.last_request_time = time.time()
            last_error = exc

    raise RuntimeError(f"Failed after {config.max_retries + 1} attempts: {last_error}") from last_error


# ---------------------------------------------------------------------------
# Daily OHLCV + Foreign Flow
# ---------------------------------------------------------------------------

@dataclass
class DailyBar:
    """Single daily OHLCV bar with extended Stockbit fields."""
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: int
    foreign_buy: float = 0.0
    foreign_sell: float = 0.0
    frequency: int = 0
    value: float = 0.0

    @property
    def foreign_net(self) -> float:
        return self.foreign_buy - self.foreign_sell


def _parse_daily_bar(raw: dict[str, Any]) -> DailyBar:
    return DailyBar(
        date=raw.get("date", ""),
        open=float(raw.get("open", 0)),
        high=float(raw.get("high", 0)),
        low=float(raw.get("low", 0)),
        close=float(raw.get("close", 0)),
        volume=int(raw.get("volume", 0)),
        foreign_buy=float(raw.get("foreignbuy", 0)),
        foreign_sell=float(raw.get("foreignsell", 0)),
        frequency=int(raw.get("frequency", 0)),
        value=float(raw.get("value", 0)),
    )


def fetch_daily_ohlcv_stockbit(
    ticker: str,
    days: int = 365,
    config: StockbitFetchConfig | None = None,
    token: str | None = None,
) -> list[DailyBar]:
    """Fetch daily OHLCV + foreign flow for a single ticker.

    Args:
        ticker: IDX ticker without .JK suffix (e.g. 'BBRI').
        days: How many calendar days of history to fetch.
        config: Fetch configuration (rate limit, delay).
        token: Stockbit token override.

    Returns:
        List of DailyBar sorted oldest-first.
    """
    config = config or DEFAULT_FETCH_CONFIG
    token = token or get_stockbit_token()
    _ensure_session(config, token)

    # Stockbit daily API: from=newest_date, to=oldest_date (reversed)
    today = date.today()
    from_date = today.isoformat()
    to_date = (today - timedelta(days=days)).isoformat()

    url = (
        f"https://exodus.stockbit.com/chartbit/{ticker}/price/daily"
        f"?from={from_date}&to={to_date}&limit=0"
    )

    data = _raw_get(url, token, config)
    chartbit = data.get("data", {}).get("chartbit", [])

    bars = [_parse_daily_bar(b) for b in chartbit if b.get("date")]
    # API returns newest-first; reverse to oldest-first
    bars.reverse()
    return bars


def fetch_daily_ohlcv_batch_stockbit(
    tickers: list[str],
    days: int = 365,
    config: StockbitFetchConfig | None = None,
    token: str | None = None,
) -> dict[str, list[DailyBar]]:
    """Fetch daily OHLCV for multiple tickers with human-like pacing.

    Args:
        tickers: List of IDX tickers without .JK suffix.
        days: Calendar days of history.
        config: Fetch configuration.
        token: Stockbit token override.

    Returns:
        Dict mapping ticker -> list of DailyBar (oldest-first).
    """
    config = config or DEFAULT_FETCH_CONFIG
    token = token or get_stockbit_token()
    _ensure_session(config, token)

    results: dict[str, list[DailyBar]] = {}
    for i, ticker in enumerate(tickers):
        try:
            bars = fetch_daily_ohlcv_stockbit(ticker, days=days, config=config, token=token)
            results[ticker] = bars
            if (i + 1) % 10 == 0:
                logger.info("Fetched %d/%d tickers", i + 1, len(tickers))
        except RuntimeError as exc:
            if "request limit" in str(exc).lower():
                logger.warning("Session limit reached at ticker %d/%d", i + 1, len(tickers))
                break
            logger.warning("Failed to fetch %s: %s", ticker, exc)
            results[ticker] = []

    return results


def daily_bars_to_dataframe(bars: list[DailyBar]) -> pd.DataFrame:
    """Convert DailyBar list to a pandas DataFrame compatible with pipeline."""
    if not bars:
        return pd.DataFrame(columns=["open", "high", "low", "close", "adjusted_close", "volume"])

    records = [
        {
            "date": b.date,
            "open": b.open,
            "high": b.high,
            "low": b.low,
            "close": b.close,
            "adjusted_close": b.close,  # Stockbit doesn't provide adjusted; use close
            "volume": b.volume,
            "foreign_buy": b.foreign_buy,
            "foreign_sell": b.foreign_sell,
            "foreign_net": b.foreign_net,
            "frequency": b.frequency,
        }
        for b in bars
    ]
    df = pd.DataFrame(records)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"]).set_index("date")
    df.index = df.index.normalize()
    df.index.name = "date"
    return df


# ---------------------------------------------------------------------------
# Intraday Candles (1-minute)
# ---------------------------------------------------------------------------

@dataclass
class IntradayBar:
    """Single 1-minute intraday candle."""
    datetime: str
    unix_timestamp: int
    open: float
    high: float
    low: float
    close: float
    volume: int
    value: float
    frequency: int
    foreign_buy: float = 0.0
    foreign_sell: float = 0.0


def _parse_intraday_bar(raw: dict[str, Any]) -> IntradayBar:
    return IntradayBar(
        datetime=raw.get("datetime", ""),
        unix_timestamp=int(raw.get("unix_timestamp", 0)),
        open=float(raw.get("open", 0)),
        high=float(raw.get("high", 0)),
        low=float(raw.get("low", 0)),
        close=float(raw.get("close", 0)),
        volume=int(raw.get("volume", 0)),
        value=float(raw.get("value", 0)),
        frequency=int(raw.get("frequency", 0)),
        foreign_buy=float(raw.get("foreign_buy", 0)),
        foreign_sell=float(raw.get("foreign_sell", 0)),
    )


def fetch_intraday_candles(
    ticker: str,
    target_date: date | None = None,
    lookback_days: int = 1,
    config: StockbitFetchConfig | None = None,
    token: str | None = None,
) -> list[IntradayBar]:
    """Fetch 1-minute intraday candles for a ticker.

    Args:
        ticker: IDX ticker without .JK (e.g. 'BBRI').
        target_date: The date to fetch intraday for. Defaults to today/last trading day.
        lookback_days: Number of trading days to fetch (max ~7 available).
        config: Fetch configuration.
        token: Stockbit token override.

    Returns:
        List of IntradayBar sorted oldest-first.
    """
    config = config or DEFAULT_FETCH_CONFIG
    token = token or get_stockbit_token()
    _ensure_session(config, token)

    # Calculate epoch range (from=newest, to=oldest for reversed Stockbit API)
    if target_date is None:
        target_date = date.today()

    # from = target_date market close (16:30 WIB)
    end_dt = datetime(target_date.year, target_date.month, target_date.day, 16, 30, tzinfo=_WIB)
    # to = lookback_days earlier at market open (08:45 WIB)
    start_dt = end_dt - timedelta(days=lookback_days)
    start_dt = start_dt.replace(hour=8, minute=45)

    from_ts = int(end_dt.timestamp())
    to_ts = int(start_dt.timestamp())

    url = (
        f"https://exodus.stockbit.com/chartbit/{ticker}/price/intraday"
        f"?from={from_ts}&to={to_ts}&limit=0"
    )

    data = _raw_get(url, token, config)
    chartbit = data.get("data", {}).get("chartbit", [])

    bars = [_parse_intraday_bar(b) for b in chartbit if b.get("datetime")]
    # API returns newest-first; reverse to oldest-first
    bars.reverse()
    return bars


# ---------------------------------------------------------------------------
# Analysis helpers
# ---------------------------------------------------------------------------

def compute_vwap(bars: list[IntradayBar], target_date: date | None = None) -> dict[str, Any]:
    """Compute VWAP (Volume Weighted Average Price) from intraday candles.

    Args:
        bars: Intraday 1-min candles (oldest-first).
        target_date: Filter bars to this date only. None = use all.

    Returns:
        Dict with vwap, total_volume, total_value, bar_count, date.
    """
    if target_date:
        date_str = target_date.isoformat()
        filtered = [b for b in bars if b.datetime.startswith(date_str)]
    else:
        filtered = bars

    if not filtered:
        return {"vwap": None, "total_volume": 0, "total_value": 0, "bar_count": 0, "date": str(target_date)}

    total_value = sum(b.value for b in filtered)
    total_volume = sum(b.volume for b in filtered)
    vwap = total_value / total_volume if total_volume > 0 else 0.0

    return {
        "vwap": round(vwap, 2),
        "total_volume": total_volume,
        "total_value": total_value,
        "bar_count": len(filtered),
        "date": filtered[0].datetime[:10],
        "open": filtered[0].open,
        "close": filtered[-1].close,
        "high": max(b.high for b in filtered),
        "low": min(b.low for b in filtered),
    }


def compute_opening_gap(
    intraday_bars: list[IntradayBar],
    previous_close: float,
) -> dict[str, Any]:
    """Compute opening gap from intraday first bar vs previous daily close.

    Args:
        intraday_bars: Intraday candles for today (oldest-first).
        previous_close: Yesterday's closing price.

    Returns:
        Dict with gap_pct, gap_amount, open_price, previous_close.
    """
    if not intraday_bars or previous_close <= 0:
        return {"gap_pct": None, "gap_amount": None, "open_price": None, "previous_close": previous_close}

    open_price = intraday_bars[0].open
    gap_amount = open_price - previous_close
    gap_pct = gap_amount / previous_close

    return {
        "gap_pct": round(gap_pct, 6),
        "gap_amount": gap_amount,
        "open_price": open_price,
        "previous_close": previous_close,
        "direction": "GAP_UP" if gap_pct > 0.005 else ("GAP_DOWN" if gap_pct < -0.005 else "FLAT_OPEN"),
    }


def compute_volume_profile(bars: list[IntradayBar], target_date: date | None = None) -> dict[str, Any]:
    """Compute hourly volume distribution (volume profile) from intraday data.

    Returns volume concentration per hour to identify accumulation/distribution timing.
    """
    if target_date:
        date_str = target_date.isoformat()
        filtered = [b for b in bars if b.datetime.startswith(date_str)]
    else:
        filtered = bars

    if not filtered:
        return {"hours": {}, "peak_hour": None, "total_volume": 0}

    hourly: dict[int, int] = {}
    for b in filtered:
        try:
            hour = int(b.datetime[11:13])
        except (ValueError, IndexError):
            continue
        hourly[hour] = hourly.get(hour, 0) + b.volume

    total = sum(hourly.values())
    peak_hour = max(hourly, key=hourly.get) if hourly else None

    return {
        "hours": {str(h): {"volume": v, "pct": round(v / total * 100, 1) if total else 0} for h, v in sorted(hourly.items())},
        "peak_hour": peak_hour,
        "total_volume": total,
        "first_30min_pct": round(sum(v for h, v in hourly.items() if h == 9) / total * 100, 1) if total else 0,
        "last_30min_pct": round(sum(v for h, v in hourly.items() if h >= 15) / total * 100, 1) if total else 0,
    }


def compute_foreign_flow_summary(bars: list[DailyBar], days: int = 5) -> dict[str, Any]:
    """Summarize foreign flow from daily bars.

    Args:
        bars: Daily bars (oldest-first).
        days: Number of recent days to summarize.

    Returns:
        Dict with net_flow, buy_total, sell_total, trend direction.
    """
    recent = bars[-days:] if len(bars) >= days else bars
    if not recent:
        return {"net_flow": 0, "buy_total": 0, "sell_total": 0, "days": 0, "trend": "NO_DATA"}

    buy_total = sum(b.foreign_buy for b in recent)
    sell_total = sum(b.foreign_sell for b in recent)
    net_flow = buy_total - sell_total

    # Trend: count net positive days
    positive_days = sum(1 for b in recent if b.foreign_net > 0)
    if positive_days >= len(recent) * 0.7:
        trend = "STRONG_INFLOW"
    elif positive_days >= len(recent) * 0.5:
        trend = "MILD_INFLOW"
    elif positive_days <= len(recent) * 0.3:
        trend = "STRONG_OUTFLOW"
    else:
        trend = "MILD_OUTFLOW"

    return {
        "net_flow": net_flow,
        "buy_total": buy_total,
        "sell_total": sell_total,
        "days": len(recent),
        "positive_days": positive_days,
        "negative_days": len(recent) - positive_days,
        "trend": trend,
        "daily": [
            {"date": b.date, "net": b.foreign_net, "buy": b.foreign_buy, "sell": b.foreign_sell}
            for b in recent
        ],
    }


def reset_session() -> None:
    """Reset the rate limiter session state (call between separate workflows)."""
    _state.reset()
