"""
insider_tracker.py – Insider transaction tracker from Stockbit structured API.

Fetches and analyzes IDX insider buy/sell transactions (major shareholders,
directors, commissioners) via the structured `/insider/company/majorholder`
endpoint for use in scoring boosts and danger detection.

Usage:
    from interday_liquidity_screener.insider_tracker import (
        fetch_insider_transactions,
        analyze_insider_activity,
        get_insider_score_adjustment,
        get_insider_support_price,
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
_CACHE_FILE_PATTERN = "insider_majorholder_{date}.json"

# API base
_INSIDER_API = "https://exodus.stockbit.com/insider/company/majorholder"


@dataclass
class InsiderTransaction:
    """Single insider transaction from structured Stockbit API."""
    ticker: str
    date: str
    investor: str
    action: str  # "BUY" or "SELL"
    shares_changed: int
    shares_pct: float
    current_shares: int
    previous_shares: int
    price: float
    nationality: str  # "LOCAL" or "FOREIGN"
    source: str  # "IDX"

    @property
    def value(self) -> float:
        return abs(self.shares_changed) * self.price

    @property
    def is_buy(self) -> bool:
        return self.action == "BUY"

    @property
    def is_sell(self) -> bool:
        return self.action == "SELL"


def _parse_number(s: str) -> int:
    """Parse formatted number like '+149,100' or '42,138,500'."""
    if not s:
        return 0
    cleaned = s.replace(",", "").replace("+", "").replace(" ", "")
    try:
        return int(cleaned)
    except ValueError:
        return 0


def _parse_pct(s: str) -> float:
    """Parse percentage like '+0.0019' or '0.52'."""
    if not s:
        return 0.0
    cleaned = s.replace("+", "").replace("%", "").strip()
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def _parse_api_item(item: dict[str, Any]) -> InsiderTransaction:
    """Parse one item from the structured API response."""
    action_type = item.get("action_type", "")
    if "BUY" in action_type:
        action = "BUY"
    elif "SELL" in action_type:
        action = "SELL"
    else:
        action = "UNKNOWN"

    changes = item.get("changes", {})
    current = item.get("current", {})
    previous = item.get("previous", {})

    nationality_raw = item.get("nationality", "")
    nationality = "FOREIGN" if "FOREIGN" in nationality_raw else "LOCAL"

    price_str = item.get("price_formatted", "0")
    try:
        price = float(price_str.replace(",", ""))
    except (ValueError, TypeError):
        price = 0.0

    return InsiderTransaction(
        ticker=item.get("symbol", ""),
        date=item.get("date", ""),
        investor=item.get("name", ""),
        action=action,
        shares_changed=_parse_number(changes.get("value", "")),
        shares_pct=_parse_pct(changes.get("percentage", "")),
        current_shares=_parse_number(current.get("value", "")),
        previous_shares=_parse_number(previous.get("value", "")),
        price=price,
        nationality=nationality,
        source=item.get("data_source", {}).get("type", "SOURCE_TYPE_IDX"),
    )


def fetch_insider_transactions(
    limit: int = 50,
    lookback_days: int = 30,
    action_filter: str = "ACTION_TYPE_UNSPECIFIED",
    token: str | None = None,
    use_cache: bool = True,
) -> list[InsiderTransaction]:
    """Fetch recent insider transactions from Stockbit structured API.

    Args:
        limit: Max entries per page (API max ~50).
        lookback_days: How far back to look.
        action_filter: ACTION_TYPE_UNSPECIFIED, ACTION_TYPE_BUY, or ACTION_TYPE_SELL.
        token: Stockbit auth token override.
        use_cache: Cache results daily.

    Returns:
        List of InsiderTransaction sorted newest-first.
    """
    today_str = date.today().isoformat()
    cache_file = _CACHE_DIR / _CACHE_FILE_PATTERN.format(date=today_str)

    if use_cache and cache_file.exists():
        try:
            cached = json.loads(cache_file.read_text(encoding="utf-8"))
            return [InsiderTransaction(**tx) for tx in cached]
        except Exception:
            logger.debug("Insider cache read failed, fetching fresh")

    token = token or get_stockbit_token()
    if not token:
        logger.warning("No Stockbit token for insider fetch")
        return []

    headers = _headers(token)
    today = date.today()
    start_date = (today - timedelta(days=lookback_days)).isoformat()
    end_date = today.isoformat()

    url = (
        f"{_INSIDER_API}?"
        f"date_start={start_date}&date_end={end_date}"
        f"&page=1&limit={limit}"
        f"&action_type={action_filter}"
        f"&source_type=SOURCE_TYPE_UNSPECIFIED"
    )

    try:
        from urllib.request import Request, urlopen
        req = Request(url, headers=headers)
        raw = urlopen(req, timeout=15).read().decode("utf-8")
        data = json.loads(raw)
    except Exception as exc:
        logger.warning("Failed to fetch insider data: %s", exc)
        return []

    items = data.get("data", {}).get("movement", [])
    transactions = [_parse_api_item(item) for item in items if item.get("symbol")]

    # Cache
    if use_cache and transactions:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_data = [
            {
                "ticker": tx.ticker, "date": tx.date, "investor": tx.investor,
                "action": tx.action, "shares_changed": tx.shares_changed,
                "shares_pct": tx.shares_pct, "current_shares": tx.current_shares,
                "previous_shares": tx.previous_shares, "price": tx.price,
                "nationality": tx.nationality, "source": tx.source,
            }
            for tx in transactions
        ]
        cache_file.write_text(json.dumps(cache_data, ensure_ascii=False, indent=2), encoding="utf-8")

    return transactions


def analyze_insider_activity(
    transactions: list[InsiderTransaction],
    lookback_days: int = 7,
) -> dict[str, dict[str, Any]]:
    """Aggregate insider activity per ticker within lookback period.

    Returns:
        Dict mapping ticker → activity summary with scoring adjustment.
    """
    today = date.today()
    cutoff = today - timedelta(days=lookback_days)

    per_ticker: dict[str, list[InsiderTransaction]] = {}
    for tx in transactions:
        tx_date = _parse_tx_date(tx.date)
        if tx_date and tx_date >= cutoff:
            per_ticker.setdefault(tx.ticker, []).append(tx)

    result: dict[str, dict[str, Any]] = {}
    for ticker, txs in per_ticker.items():
        buys = [t for t in txs if t.is_buy]
        sells = [t for t in txs if t.is_sell]
        buy_shares = sum(t.shares_changed for t in buys)
        sell_shares = sum(abs(t.shares_changed) for t in sells)
        buy_value = sum(t.value for t in buys)
        avg_buy_price = buy_value / buy_shares if buy_shares > 0 else 0

        # Signal scoring
        if len(buys) >= 3 and sell_shares == 0:
            signal = "STRONG_INSIDER_BUY"
            score_adj = 15
        elif len(buys) >= 2 and buy_shares > sell_shares * 2:
            signal = "MODERATE_INSIDER_BUY"
            score_adj = 10
        elif buy_shares > sell_shares:
            signal = "MILD_INSIDER_BUY"
            score_adj = 5
        elif len(sells) >= 2 and sell_shares > buy_shares * 3:
            signal = "STRONG_INSIDER_SELL"
            score_adj = -15
        elif sell_shares > buy_shares:
            signal = "MILD_INSIDER_SELL"
            score_adj = -5
        else:
            signal = "NEUTRAL"
            score_adj = 0

        investors = list(set(t.investor for t in txs if t.investor))

        result[ticker] = {
            "signal": signal,
            "score_adjustment": score_adj,
            "buy_count": len(buys),
            "sell_count": len(sells),
            "net_shares": buy_shares - sell_shares,
            "buy_shares": buy_shares,
            "sell_shares": sell_shares,
            "avg_buy_price": round(avg_buy_price, 0),
            "total_buy_value": buy_value,
            "investors": investors[:5],
            "latest_date": max(t.date for t in txs) if txs else "",
            "transactions": len(txs),
        }

    return result


def get_insider_score_adjustment(ticker: str, activity: dict[str, dict[str, Any]]) -> tuple[int, str]:
    """Get score adjustment and signal for a specific ticker.

    NOTE: Score adjustments (+15/-15) are heuristic rule-of-thumb values,
    NOT validated against historical backtest data. They should be treated
    as directional signals, not precise alpha measurements. Future work:
    validate optimal thresholds by measuring actual post-insider-buy returns.
    """
    clean = ticker.replace(".JK", "").upper()
    info = activity.get(clean)
    if not info:
        return 0, "NO_INSIDER_DATA"
    return info["score_adjustment"], info["signal"]


def get_insider_support_price(ticker: str, activity: dict[str, dict[str, Any]]) -> float | None:
    """Get average insider buy price as implicit support level."""
    clean = ticker.replace(".JK", "").upper()
    info = activity.get(clean)
    if not info or info["avg_buy_price"] <= 0:
        return None
    return info["avg_buy_price"]


def _parse_tx_date(date_str: str) -> date | None:
    """Parse dates like '10 Jul 26' or '2026-07-10'."""
    if not date_str:
        return None
    try:
        return date.fromisoformat(date_str)
    except ValueError:
        pass
    try:
        dt = datetime.strptime(date_str.strip(), "%d %b %y")
        return dt.date()
    except ValueError:
        pass
    return None
