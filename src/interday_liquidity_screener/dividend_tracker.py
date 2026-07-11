"""
dividend_tracker.py – Real-time dividend/corporate action tracker from Stockbit.

Fetches upcoming cum-dates, ex-dates, and dividend values to:
1. Block trades on ex-date (guaranteed drop)
2. Adjust SL for stocks near ex-date
3. Identify cum-date plays (buy before cum for dividend)
4. Reject BPJS candidates on ex-date morning

Usage:
    from interday_liquidity_screener.dividend_tracker import (
        fetch_upcoming_dividends,
        is_exdate_danger,
        get_dividend_yield,
    )
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from .stockbit_collector import get_stockbit_token, _headers

logger = logging.getLogger(__name__)

_CACHE_DIR = Path("data/cache")
_CACHE_FILE_PATTERN = "dividends_{date}.json"
_DIVIDEND_API = "https://exodus.stockbit.com/corpaction/dividend"


@dataclass
class DividendEvent:
    """Single upcoming dividend event."""
    ticker: str
    cum_date: str  # Last day to buy for dividend eligibility
    ex_date: str   # Price drops here — DON'T buy
    rec_date: str  # Record date
    pay_date: str  # Payment date
    dividend_per_share: float
    last_price: float
    is_active: bool

    @property
    def yield_pct(self) -> float:
        """Dividend yield as percentage of current price."""
        if self.last_price <= 0:
            return 0.0
        return self.dividend_per_share / self.last_price * 100

    @property
    def drop_estimate_pct(self) -> float:
        """Estimated price drop on ex-date (= dividend / price)."""
        return self.yield_pct


def _parse_dividend_item(item: dict[str, Any]) -> DividendEvent:
    """Parse one item from the API response."""
    price_str = item.get("lastprice", "0")
    try:
        price = float(str(price_str).replace(",", ""))
    except (ValueError, TypeError):
        price = 0.0

    div_str = item.get("dividend_value", "0")
    try:
        div_value = float(str(div_str).replace(",", ""))
    except (ValueError, TypeError):
        div_value = 0.0

    return DividendEvent(
        ticker=item.get("company_symbol", ""),
        cum_date=item.get("dividend_cumdate", ""),
        ex_date=item.get("dividend_exdate", ""),
        rec_date=item.get("dividend_recdate", ""),
        pay_date=item.get("dividend_paydate", ""),
        dividend_per_share=div_value,
        last_price=price,
        is_active=bool(item.get("corp_action_active", False)),
    )


def fetch_upcoming_dividends(
    token: str | None = None,
    use_cache: bool = True,
) -> list[DividendEvent]:
    """Fetch upcoming/active dividend events from Stockbit.

    Returns list of DividendEvent sorted by ex_date (soonest first).
    """
    today_str = date.today().isoformat()
    cache_file = _CACHE_DIR / _CACHE_FILE_PATTERN.format(date=today_str)

    if use_cache and cache_file.exists():
        try:
            cached = json.loads(cache_file.read_text(encoding="utf-8"))
            return [DividendEvent(**d) for d in cached]
        except Exception:
            logger.debug("Dividend cache read failed, fetching fresh")

    token = token or get_stockbit_token()
    if not token:
        logger.warning("No Stockbit token for dividend fetch")
        return []

    headers = _headers(token)
    try:
        from urllib.request import Request, urlopen
        req = Request(_DIVIDEND_API, headers=headers)
        raw = urlopen(req, timeout=15).read().decode("utf-8")
        data = json.loads(raw)
    except Exception as exc:
        logger.warning("Failed to fetch dividend data: %s", exc)
        return []

    items = data.get("data", {}).get("dividend", [])
    events = [_parse_dividend_item(item) for item in items if item.get("company_symbol")]

    # Sort by ex_date
    events.sort(key=lambda e: e.ex_date)

    # Cache
    if use_cache and events:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_data = [
            {
                "ticker": e.ticker, "cum_date": e.cum_date, "ex_date": e.ex_date,
                "rec_date": e.rec_date, "pay_date": e.pay_date,
                "dividend_per_share": e.dividend_per_share, "last_price": e.last_price,
                "is_active": e.is_active,
            }
            for e in events
        ]
        cache_file.write_text(json.dumps(cache_data, ensure_ascii=False, indent=2), encoding="utf-8")

    return events


def is_exdate_danger(
    ticker: str,
    events: list[DividendEvent],
    check_date: date | None = None,
    danger_window_days: int = 1,
) -> tuple[bool, DividendEvent | None]:
    """Check if a ticker is in the ex-date danger zone.

    Returns (is_danger, event) — True if the ticker's ex-date is within
    danger_window_days of check_date. DON'T BUY if True.

    Args:
        ticker: IDX ticker (without .JK).
        events: List from fetch_upcoming_dividends.
        check_date: Date to check against (default: today).
        danger_window_days: How many days before ex-date to flag (1 = ex-date only).
    """
    check = check_date or date.today()
    clean = ticker.replace(".JK", "").upper()

    for event in events:
        if event.ticker.upper() != clean:
            continue
        try:
            ex = date.fromisoformat(event.ex_date)
        except (ValueError, TypeError):
            continue
        # Danger zone: ex_date itself and danger_window_days before
        if 0 <= (ex - check).days <= danger_window_days:
            return True, event

    return False, None


def is_cumdate_opportunity(
    ticker: str,
    events: list[DividendEvent],
    check_date: date | None = None,
    min_yield_pct: float = 2.0,
) -> tuple[bool, DividendEvent | None]:
    """Check if a ticker has an upcoming cum-date play opportunity.

    Returns (is_opportunity, event) — True if cum-date is upcoming (within 5 days)
    and dividend yield meets minimum threshold.
    """
    check = check_date or date.today()
    clean = ticker.replace(".JK", "").upper()

    for event in events:
        if event.ticker.upper() != clean:
            continue
        try:
            cum = date.fromisoformat(event.cum_date)
        except (ValueError, TypeError):
            continue
        days_to_cum = (cum - check).days
        if 0 <= days_to_cum <= 5 and event.yield_pct >= min_yield_pct:
            return True, event

    return False, None


def get_dividend_yield(ticker: str, events: list[DividendEvent]) -> float | None:
    """Get dividend yield for a ticker if it has an active event."""
    clean = ticker.replace(".JK", "").upper()
    for event in events:
        if event.ticker.upper() == clean and event.is_active:
            return event.yield_pct
    return None


def get_exdate_tickers(events: list[DividendEvent], target_date: date | None = None) -> list[str]:
    """Get all tickers that have ex-date on target_date. These should be BLOCKED."""
    target = target_date or date.today()
    return [e.ticker for e in events if e.ex_date == target.isoformat()]
