from __future__ import annotations

from dataclasses import dataclass
import ast
import json
from pathlib import Path
import time
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pandas as pd

from .constants import WatchlistStatus
from .stockbit_collector import get_stockbit_token, parse_number

ORDERBOOK_URL = "https://exodus.stockbit.com/company-price-feed/v2/orderbook/companies/{ticker}"
FETCH_SIGNALS = {"STRONG_ACCUMULATION", "MILD_ACCUMULATION", "PULLBACK_WITH_MEDIUM_ACCUMULATION"}
SKIP_CONTEXTS = {"TOO_VOLATILE", "TOO_QUIET_ABSOLUTE", "INVALID_DATA"}


@dataclass(frozen=True)
class OrderbookFilterConfig:
    sleep_seconds: float = 2.0
    max_retries: int = 3
    retry_backoff_seconds: float = 10.0
    max_spread_pct: float = 0.01
    supportive_spread_pct: float = 0.005
    min_depth_imbalance: float = -0.20
    max_offer_wall_ratio: float = 3.0
    near_ara_arb_threshold: float = 0.02
    min_intraday_value: float = 5_000_000_000
    min_frequency: int = 100


def _headers(token: str) -> dict[str, str]:
    return {
        "Accept": "application/json",
        "Authorization": f"Bearer {token}",
        "Origin": "https://stockbit.com",
        "Referer": "https://stockbit.com/",
        "User-Agent": "Mozilla/5.0",
    }


def _bool_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "y", "1.0"}
    if isinstance(value, (list, tuple, set, dict)):
        return len(value) > 0
    try:
        if not isinstance(value, (list, tuple, set, dict)) and pd.isna(value):
            return False
    except (TypeError, ValueError):
        return False
    return bool(value)


def _text_has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, (list, tuple, set, dict)):
        return len(value) > 0
    try:
        if not isinstance(value, (list, tuple, set, dict)) and pd.isna(value):
            return False
    except (TypeError, ValueError):
        return False
    return str(value).strip() not in {"", "-", "None", "nan", "[]", "{}"}


def parse_jsonish_value(value: Any) -> Any:
    if value is None:
        return None
    try:
        if not isinstance(value, (dict, list, tuple, bool, int, float)) and pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, (dict, list, tuple, bool, int, float)):
        return value
    if isinstance(value, str):
        text = value.strip()
        if text in {"", "-", "None", "none", "null", "nan"}:
            return None
        if text in {"[]", "{}"}:
            return [] if text == "[]" else {}
        for parser in (json.loads, ast.literal_eval):
            try:
                return parser(text)
            except (ValueError, SyntaxError, TypeError, json.JSONDecodeError):
                continue
        return text
    return value


def is_corp_action_active(value: Any) -> bool:
    parsed = parse_jsonish_value(value)
    if parsed is None:
        return False
    if isinstance(parsed, dict):
        if "active" in parsed:
            return _bool_value(parsed.get("active"))
        return False
    if isinstance(parsed, (list, tuple, set)):
        return any(is_corp_action_active(item) for item in parsed)
    return _text_has_value(parsed)


def is_notation_risky(value: Any) -> bool:
    parsed = parse_jsonish_value(value)
    if parsed is None:
        return False
    if isinstance(parsed, dict):
        return bool(parsed)
    if isinstance(parsed, (list, tuple, set)):
        return len(parsed) > 0
    return _text_has_value(parsed)


def fetch_orderbook(ticker: str, config: OrderbookFilterConfig, token: str | None = None) -> dict[str, Any]:
    token = token or get_stockbit_token()
    url = ORDERBOOK_URL.format(ticker=ticker)
    for attempt in range(config.max_retries + 1):
        try:
            request = Request(url, headers=_headers(token), method="GET")
            with urlopen(request, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            if exc.code == 401:
                raise RuntimeError("Stockbit token expired/invalid. Login again and update STOCKBIT_TOKEN in .env.") from exc
            if exc.code == 429 and attempt < config.max_retries:
                time.sleep(config.retry_backoff_seconds)
                continue
            raise
        except Exception:
            if attempt < config.max_retries:
                time.sleep(config.retry_backoff_seconds)
                continue
            raise
    raise RuntimeError(f"Failed to fetch Stockbit orderbook for {ticker}")


def save_orderbook_raw_json(payload: dict[str, Any], ticker: str, raw_dir: str | Path) -> Path:
    path = Path(raw_dir)
    path.mkdir(parents=True, exist_ok=True)
    file_path = path / f"{ticker}_orderbook.json"
    file_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return file_path


def _data(payload: dict[str, Any]) -> dict[str, Any]:
    data = payload.get("data") if isinstance(payload, dict) else {}
    return data if isinstance(data, dict) else {}


def _levels(data: dict[str, Any], side: str) -> list[dict[str, Any]]:
    levels = data.get(side, [])
    return levels if isinstance(levels, list) else []


def _level_number(level: dict[str, Any], key: str) -> float:
    parsed = parse_number(level.get(key))
    return parsed if parsed is not None else 0.0


def _sum_levels(levels: list[dict[str, Any]], key: str, count: int) -> float:
    return float(sum(_level_number(level, key) for level in levels[:count]))


def _imbalance(bid_volume: float, offer_volume: float) -> float | None:
    total = bid_volume + offer_volume
    if total <= 0:
        return None
    return (bid_volume - offer_volume) / total


def _wall(levels: list[dict[str, Any]], count: int) -> tuple[float | None, float, float | None]:
    subset = levels[:count]
    if not subset:
        return None, 0.0, None
    volumes = [_level_number(level, "volume") for level in subset]
    max_volume = max(volumes) if volumes else 0.0
    max_index = volumes.index(max_volume) if volumes else 0
    avg_volume = sum(volumes) / len(volumes) if volumes else 0.0
    price = parse_number(subset[max_index].get("price"))
    ratio = max_volume / avg_volume if avg_volume > 0 else None
    return price, max_volume, ratio


def normalize_orderbook_payload(payload: dict[str, Any], ticker: str, config: OrderbookFilterConfig | None = None) -> dict[str, Any]:
    config = config or OrderbookFilterConfig()
    data = _data(payload)
    if not data:
        return _empty_orderbook_row(ticker, "NO_ORDERBOOK_DATA")

    bid = _levels(data, "bid")
    offer = _levels(data, "offer")
    row: dict[str, Any] = {"ticker": ticker, "orderbook_available": bool(bid and offer)}
    for field in [
        "symbol",
        "name",
        "lastprice",
        "open",
        "high",
        "low",
        "close",
        "previous",
        "change",
        "percentage_change",
        "average",
        "volume",
        "value",
        "frequency",
        "foreign",
        "domestic",
        "fbuy",
        "fsell",
        "fnet",
        "ara",
        "arb",
        "next_ara",
        "next_arb",
        "status",
        "tradable",
        "notation",
        "uma",
        "corp_action",
    ]:
        value = data.get(field)
        row[field] = parse_number(value) if field not in {"symbol", "name", "status", "tradable", "notation", "uma", "corp_action"} else value

    row["bid_levels"] = len(bid)
    row["offer_levels"] = len(offer)
    row["best_bid"] = parse_number(bid[0].get("price")) if bid else None
    row["best_offer"] = parse_number(offer[0].get("price")) if offer else None
    if row["best_bid"] is not None and row["best_offer"] is not None:
        row["mid_price"] = (row["best_bid"] + row["best_offer"]) / 2
        row["spread"] = row["best_offer"] - row["best_bid"]
        row["spread_pct"] = row["spread"] / row["mid_price"] if row["mid_price"] else None
    else:
        row["mid_price"] = row["spread"] = row["spread_pct"] = None

    for count in [1, 3, 5, 10]:
        bid_volume = _sum_levels(bid, "volume", count)
        offer_volume = _sum_levels(offer, "volume", count)
        row[f"bid_volume_top{count}"] = bid_volume
        row[f"offer_volume_top{count}"] = offer_volume
        row[f"depth_imbalance_top{count}"] = _imbalance(bid_volume, offer_volume)
    row["bid_queue_top1"] = _sum_levels(bid, "que_num", 1)
    row["offer_queue_top1"] = _sum_levels(offer, "que_num", 1)
    row["bid_queue_top5"] = _sum_levels(bid, "que_num", 5)
    row["offer_queue_top5"] = _sum_levels(offer, "que_num", 5)

    row["max_bid_wall_price"], row["max_bid_wall_volume"], row["bid_wall_ratio_top5"] = _wall(bid, 5)
    row["max_offer_wall_price"], row["max_offer_wall_volume"], row["offer_wall_ratio_top5"] = _wall(offer, 5)

    value = row.get("value")
    fnet = row.get("fnet")
    row["foreign_net_ratio"] = float(fnet) / float(value) if value not in {None, 0} and pd.notna(value) and fnet is not None and pd.notna(fnet) else None
    lastprice = row.get("lastprice")
    ara = row.get("ara")
    arb = row.get("arb")
    row["distance_to_ara"] = (float(ara) - float(lastprice)) / float(lastprice) if lastprice and ara and pd.notna(lastprice) and pd.notna(ara) else None
    row["distance_to_arb"] = (float(lastprice) - float(arb)) / float(lastprice) if lastprice and arb and pd.notna(lastprice) and pd.notna(arb) else None
    row["near_ara"] = row["distance_to_ara"] is not None and row["distance_to_ara"] <= config.near_ara_arb_threshold
    row["near_arb"] = row["distance_to_arb"] is not None and row["distance_to_arb"] <= config.near_ara_arb_threshold
    row["corp_action_active"] = is_corp_action_active(row.get("corp_action"))
    row["notation_risky"] = is_notation_risky(row.get("notation"))
    row["orderbook_score"] = calculate_orderbook_score(row, config)
    row["orderbook_status"] = classify_orderbook(row, config)
    row["orderbook_reason"] = build_orderbook_reason(row)
    row["orderbook_summary"] = build_orderbook_summary(row)
    return row


def _empty_orderbook_row(ticker: str, status: str) -> dict[str, Any]:
    row = {"ticker": ticker, "orderbook_available": False, "orderbook_status": status, "orderbook_score": 0}
    row["orderbook_reason"] = "no_orderbook_data_available"
    row["orderbook_summary"] = "No orderbook data available for execution-quality review."
    return row


def calculate_orderbook_score(row: dict[str, Any], config: OrderbookFilterConfig) -> int:
    if not row.get("orderbook_available"):
        return 0
    score = 50
    spread_pct = row.get("spread_pct")
    if spread_pct is not None and pd.notna(spread_pct):
        if spread_pct <= 0.005:
            score += 15
        if spread_pct <= 0.0025:
            score += 10
        if spread_pct > 0.01:
            score -= 15
        elif spread_pct > 0.005:
            score -= 10
    if row.get("depth_imbalance_top5") is not None and pd.notna(row.get("depth_imbalance_top5")):
        if row["depth_imbalance_top5"] >= 0.20:
            score += 15
        if row["depth_imbalance_top5"] <= -0.20:
            score -= 15
    if row.get("depth_imbalance_top3") is not None and pd.notna(row.get("depth_imbalance_top3")) and row["depth_imbalance_top3"] >= 0.10:
        score += 10
    if row.get("bid_volume_top5", 0) > row.get("offer_volume_top5", 0):
        score += 10
    if row.get("fnet") is not None and pd.notna(row.get("fnet")) and row["fnet"] > 0:
        score += 5
    if row.get("frequency") is not None and pd.notna(row.get("frequency")) and row["frequency"] >= config.min_frequency:
        score += 5
    if row.get("value") is not None and pd.notna(row.get("value")) and row["value"] >= config.min_intraday_value:
        score += 5
    tradable_val = row.get("tradable")
    is_tradable = True
    if tradable_val is not None and not pd.isna(tradable_val):
        is_tradable = _bool_value(tradable_val)
    if not is_tradable:
        score -= 20
    if _bool_value(row.get("uma")):
        score -= 20
    if row.get("notation_risky", is_notation_risky(row.get("notation"))):
        score -= 15
    if row.get("corp_action_active", is_corp_action_active(row.get("corp_action"))):
        score -= 15
    if row.get("offer_wall_ratio_top5") is not None and pd.notna(row.get("offer_wall_ratio_top5")) and row["offer_wall_ratio_top5"] >= 3.0:
        score -= 10
    if row.get("near_ara") or row.get("near_arb"):
        score -= 10
    foreign_net_ratio = row.get("foreign_net_ratio")
    if row.get("fnet") is not None and pd.notna(row.get("fnet")) and row["fnet"] < 0 and foreign_net_ratio is not None and pd.notna(foreign_net_ratio) and abs(foreign_net_ratio) >= 0.05:
        score -= 10
    return max(0, min(100, int(round(score))))


def classify_orderbook(row: dict[str, Any], config: OrderbookFilterConfig) -> str:
    if not row.get("orderbook_available"):
        return "NO_ORDERBOOK_DATA"
    tradable_val = row.get("tradable")
    is_tradable = True
    if tradable_val is not None and not pd.isna(tradable_val):
        is_tradable = _bool_value(tradable_val)
    if not is_tradable:
        return "REJECT_NOT_TRADABLE"
    if _bool_value(row.get("uma")) or row.get("notation_risky", is_notation_risky(row.get("notation"))):
        return "REJECT_UMA_OR_NOTATION_RISK"
    if row.get("corp_action_active", is_corp_action_active(row.get("corp_action"))):
        return "REJECT_CORPORATE_ACTION_RISK"
    if row.get("near_ara") or row.get("near_arb"):
        return "WAIT_NEAR_ARA_ARB"
    if row.get("spread_pct") is not None and pd.notna(row.get("spread_pct")) and row["spread_pct"] > config.max_spread_pct:
        return "WAIT_SPREAD_TOO_WIDE"
    if row.get("offer_wall_ratio_top5") is not None and pd.notna(row.get("offer_wall_ratio_top5")) and row["offer_wall_ratio_top5"] >= config.max_offer_wall_ratio:
        return "WAIT_OFFER_WALL"
    if row.get("depth_imbalance_top5") is not None and pd.notna(row.get("depth_imbalance_top5")) and row["depth_imbalance_top5"] <= config.min_depth_imbalance:
        return "WAIT_BID_DEPTH_WEAK"
    score = int(row.get("orderbook_score") or 0)
    if score >= 70:
        return "ORDERBOOK_SUPPORTIVE"
    if score >= 50:
        return "ORDERBOOK_NEUTRAL"
    return "ORDERBOOK_WEAK"


def build_orderbook_reason(row: dict[str, Any]) -> str:
    mapping = {
        "NO_ORDERBOOK_DATA": "no_orderbook_data_available",
        "REJECT_NOT_TRADABLE": "stock_is_not_tradable_now",
        "REJECT_UMA_OR_NOTATION_RISK": "uma_or_special_notation_risk",
        "REJECT_CORPORATE_ACTION_RISK": "corporate_action_risk_detected",
        "WAIT_NEAR_ARA_ARB": "price_is_too_close_to_auto_reject_band",
        "WAIT_SPREAD_TOO_WIDE": "spread_is_too_wide_for_clean_execution",
        "WAIT_OFFER_WALL": "large_offer_wall_near_best_offer",
        "WAIT_BID_DEPTH_WEAK": "bid_depth_is_weak_relative_to_offer_depth",
        "ORDERBOOK_SUPPORTIVE": "orderbook_supports_execution_quality",
        "ORDERBOOK_NEUTRAL": "orderbook_execution_quality_is_neutral",
        "ORDERBOOK_WEAK": "orderbook_execution_quality_is_weak",
    }
    return mapping.get(str(row.get("orderbook_status")), "orderbook_status_not_classified")


def build_orderbook_summary(row: dict[str, Any]) -> str:
    status = row.get("orderbook_status")
    if status == "ORDERBOOK_SUPPORTIVE":
        return "Orderbook is supportive: spread is acceptable and bid depth is not weak."
    if status == "ORDERBOOK_NEUTRAL":
        return "Orderbook is neutral: execution is possible but not strongly supported by depth."
    if status == "WAIT_OFFER_WALL":
        return "Offer wall is heavy near the top of book. Wait for supply to thin before execution."
    if status == "WAIT_SPREAD_TOO_WIDE":
        return "Spread is too wide for clean execution. Wait for a tighter orderbook."
    if status == "WAIT_BID_DEPTH_WEAK":
        return "Bid depth is weak versus offer depth. Wait for stronger support."
    if status == "WAIT_NEAR_ARA_ARB":
        return "Price is close to ARA/ARB. Avoid chasing execution around auto-reject bands."
    if status and str(status).startswith("REJECT"):
        return "Orderbook has execution or risk flags. Do not execute by default."
    return "No usable orderbook data for execution-quality review."


def load_orderbook_universe(
    stage2_path: str | Path,
    bandarmology_path: str | Path,
    watchlist_path: str | Path | None = None,
) -> pd.DataFrame:
    stage2 = pd.read_csv(stage2_path)
    bandar = pd.read_csv(bandarmology_path)
    merged = stage2.merge(
        bandar[["ticker", "broker_activity_available", "bandarmology_signal"]],
        on="ticker",
        how="left",
        suffixes=("", "_bandar"),
    )
    mask = (
        merged["is_data_valid"].astype(str).str.lower().isin({"true", "1", "yes"})
        & merged["liquidity_bucket"].isin(["HIGH_LIQUIDITY", "GOOD_LIQUIDITY"])
        & merged["bandar_watch_eligible"].astype(str).str.lower().isin({"true", "1", "yes"})
        & merged["broker_activity_available"].astype(str).str.lower().isin({"true", "1", "yes"})
        & merged["bandarmology_signal"].isin(FETCH_SIGNALS)
        & ~merged["technical_context"].isin(SKIP_CONTEXTS)
    )
    selected_tickers = set(merged.loc[mask, "ticker"].astype(str))

    # A morning resume must validate the candidates produced by the previous
    # hybrid pass. The broker-flow filter alone can be much narrower than the
    # safe-execution path (for example when broker data is unavailable), which
    # previously left NEED_ORDERBOOK candidates permanently unresolved.
    if watchlist_path and Path(watchlist_path).exists():
        try:
            watchlist = pd.read_csv(watchlist_path)
        except pd.errors.EmptyDataError:
            watchlist = pd.DataFrame()
        ticker_column = "symbol" if "symbol" in watchlist.columns else "ticker"
        live_confirmation_statuses = {
            WatchlistStatus.NEED_ORDERBOOK.value,
            WatchlistStatus.EXECUTION_DRAFT.value,
            WatchlistStatus.EXECUTION_CANDIDATE.value,
            WatchlistStatus.READY_SOON.value,
        }
        if ticker_column in watchlist.columns and "final_status" in watchlist.columns:
            needs_live_confirmation = watchlist["final_status"].astype(str).isin(live_confirmation_statuses)
            selected_tickers.update(watchlist.loc[needs_live_confirmation, ticker_column].dropna().astype(str))

    return merged[merged["ticker"].astype(str).isin(selected_tickers)].copy()


def run_stage3c_orderbook_filter(
    stage2_path: str | Path,
    bandarmology_path: str | Path,
    output_path: str | Path,
    raw_dir: str | Path,
    config: OrderbookFilterConfig | None = None,
    watchlist_path: str | Path | None = None,
) -> pd.DataFrame:
    config = config or OrderbookFilterConfig()
    universe = load_orderbook_universe(stage2_path, bandarmology_path, watchlist_path=watchlist_path)
    token = get_stockbit_token()
    print(f"Stage 3C orderbook tickers: {len(universe)}")
    rows: list[dict[str, Any]] = []
    success = failed = unauthorized = rate_limited = 0
    for _, row in universe.iterrows():
        ticker = str(row["ticker"]).replace(".JK", "")
        try:
            payload = fetch_orderbook(ticker, config, token=token)
            save_orderbook_raw_json(payload, ticker, raw_dir)
            rows.append(normalize_orderbook_payload(payload, ticker, config))
            success += 1
        except RuntimeError as exc:
            failed += 1
            if "expired/invalid" in str(exc):
                unauthorized += 1
            print(f"{ticker}: {exc}")
            rows.append(_empty_orderbook_row(ticker, "NO_ORDERBOOK_DATA"))
        except HTTPError as exc:
            failed += 1
            if exc.code == 401:
                unauthorized += 1
            if exc.code == 429:
                rate_limited += 1
            print(f"{ticker}: HTTP {exc.code}")
            rows.append(_empty_orderbook_row(ticker, "NO_ORDERBOOK_DATA"))
        except Exception as exc:
            failed += 1
            print(f"{ticker}: fetch_failed {exc}")
            rows.append(_empty_orderbook_row(ticker, "NO_ORDERBOOK_DATA"))
        time.sleep(config.sleep_seconds)

    output = pd.DataFrame(rows)
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    output.to_csv(path, index=False)
    print(f"Fetched success: {success}")
    print(f"Failed: {failed}")
    print(f"401 count: {unauthorized}")
    print(f"429 count: {rate_limited}")
    print(f"Output saved to: {path}")
    print(f"Raw dir path: {raw_dir}")
    return output
