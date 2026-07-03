from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import time
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd


@dataclass(frozen=True)
class StockbitCollectorConfig:
    base_url: str = "https://exodus.stockbit.com/marketdetectors"
    transaction_type: str = "TRANSACTION_TYPE_NET"
    market_board: str = "MARKET_BOARD_REGULER"
    investor_type: str = "INVESTOR_TYPE_ALL"
    limit: int = 25
    sleep_seconds: float = 3.0
    max_retries: int = 3
    retry_backoff_seconds: float = 10.0


def parse_number(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text or text == "-":
        return None
    multiplier = 1.0
    suffix = text[-1].upper()
    if suffix in {"K", "M", "B", "T"}:
        text = text[:-1]
        multiplier = {"K": 1_000, "M": 1_000_000, "B": 1_000_000_000, "T": 1_000_000_000_000}[suffix]
    text = text.replace(",", "")
    try:
        return float(text) * multiplier
    except ValueError:
        return None


def _load_dotenv(path: str | Path = ".env") -> None:
    env_path = Path(path)
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def get_stockbit_token() -> str:
    _load_dotenv()
    token = os.environ.get("STOCKBIT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("STOCKBIT_TOKEN is empty. Put your valid Stockbit bearer token in .env.")
    return token


def load_stage2_bandar_watchlist(input_path: str | Path) -> pd.DataFrame:
    df = pd.read_csv(input_path)
    required = {"ticker", "bandar_watch_eligible"}
    missing = required.difference(df.columns)
    if missing:
        raise ValueError(f"Stage 2 file is missing columns: {', '.join(sorted(missing))}")
    mask = df["bandar_watch_eligible"].astype(str).str.lower().isin({"true", "1", "yes"})
    return df[mask].copy()


def build_marketdetector_url(
    ticker: str,
    from_date: str,
    to_date: str,
    config: StockbitCollectorConfig,
) -> str:
    params = urlencode(
        {
            "from": from_date,
            "to": to_date,
            "transaction_type": config.transaction_type,
            "market_board": config.market_board,
            "investor_type": config.investor_type,
            "limit": config.limit,
        }
    )
    return f"{config.base_url}/{ticker}?{params}"


def _headers(token: str) -> dict[str, str]:
    return {
        "Accept": "application/json",
        "Authorization": f"Bearer {token}",
        "Origin": "https://stockbit.com",
        "Referer": "https://stockbit.com/",
        "User-Agent": "Mozilla/5.0",
    }


def fetch_marketdetector(
    ticker: str,
    from_date: str,
    to_date: str,
    config: StockbitCollectorConfig,
    token: str | None = None,
) -> dict[str, Any]:
    token = token or get_stockbit_token()
    url = build_marketdetector_url(ticker, from_date, to_date, config)
    last_error: Exception | None = None
    for attempt in range(config.max_retries + 1):
        try:
            request = Request(url, headers=_headers(token), method="GET")
            with urlopen(request, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            last_error = exc
            if exc.code == 401:
                raise RuntimeError("Stockbit token expired/invalid. Login again and update STOCKBIT_TOKEN in .env.") from exc
            if exc.code == 429 and attempt < config.max_retries:
                time.sleep(config.retry_backoff_seconds)
                continue
            raise
        except Exception as exc:
            last_error = exc
            if attempt < config.max_retries:
                time.sleep(config.retry_backoff_seconds)
                continue
            raise
    raise RuntimeError(f"Failed to fetch Stockbit marketdetector for {ticker}: {last_error}")


def save_raw_json(payload: dict[str, Any], ticker: str, from_date: str, to_date: str, raw_dir: str | Path) -> Path:
    path = Path(raw_dir)
    path.mkdir(parents=True, exist_ok=True)
    file_path = path / f"{ticker}_{from_date}_{to_date}.json"
    file_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return file_path


def _response_data(payload: dict[str, Any]) -> dict[str, Any]:
    data = payload.get("data") if isinstance(payload, dict) else {}
    return data if isinstance(data, dict) else {}


def _metric_block(detector: dict[str, Any], name: str) -> dict[str, Any]:
    block = detector.get(name)
    return block if isinstance(block, dict) else {}


def normalize_bandar_detector_summary(
    payload: dict[str, Any],
    ticker: str,
    from_date: str,
    to_date: str,
) -> dict[str, Any]:
    detector = _response_data(payload).get("bandar_detector", {})
    detector = detector if isinstance(detector, dict) else {}
    row: dict[str, Any] = {
        "ticker": ticker,
        "from_date": from_date,
        "to_date": to_date,
        "detector_average_price": parse_number(detector.get("average")),
        "broker_accdist": detector.get("broker_accdist"),
        "number_broker_buysell": parse_number(detector.get("number_broker_buysell")),
        "total_buyer": parse_number(detector.get("total_buyer")),
        "total_seller": parse_number(detector.get("total_seller")),
        "detector_total_value": parse_number(detector.get("value")),
        "detector_total_volume": parse_number(detector.get("volume")),
        "raw_bandar_detector_json": json.dumps(detector, ensure_ascii=False),
    }
    for name in ["avg", "avg5", "top1", "top3", "top5", "top10"]:
        block = _metric_block(detector, name)
        prefix = name
        row[f"{prefix}_accdist"] = block.get("accdist")
        row[f"{prefix}_amount"] = parse_number(block.get("amount"))
        row[f"{prefix}_percent"] = parse_number(block.get("percent"))
        row[f"{prefix}_volume"] = parse_number(block.get("vol"))
    return row


def normalize_broker_summary_long(
    payload: dict[str, Any],
    ticker: str,
    from_date: str,
    to_date: str,
) -> list[dict[str, Any]]:
    broker_summary = _response_data(payload).get("broker_summary", {})
    broker_summary = broker_summary if isinstance(broker_summary, dict) else {}
    rows: list[dict[str, Any]] = []
    for side, key in [("BUY", "brokers_buy"), ("SELL", "brokers_sell")]:
        items = broker_summary.get(key, [])
        if not isinstance(items, list):
            continue
        for rank, item in enumerate(items, start=1):
            item_dict = item if isinstance(item, dict) else {"value": item}
            if side == "BUY":
                net_lot = item_dict.get("blot")
                net_value = item_dict.get("bval")
                gross_volume = item_dict.get("blotv")
                gross_value = item_dict.get("bvalv")
                avg_price = item_dict.get("netbs_buy_avg_price")
            else:
                net_lot = item_dict.get("slot", item_dict.get("blot"))
                net_value = item_dict.get("sval", item_dict.get("bval"))
                gross_volume = item_dict.get("slotv", item_dict.get("blotv"))
                gross_value = item_dict.get("svalv", item_dict.get("bvalv"))
                avg_price = item_dict.get("netbs_sell_avg_price", item_dict.get("netbs_buy_avg_price"))
            rows.append(
                {
                    "ticker": ticker,
                    "from_date": from_date,
                    "to_date": to_date,
                    "side": side,
                    "rank": rank,
                    "broker_code": item_dict.get("netbs_broker_code"),
                    "investor_type": item_dict.get("type"),
                    "net_lot": parse_number(net_lot),
                    "net_value": parse_number(net_value),
                    "gross_volume": parse_number(gross_volume),
                    "gross_value": parse_number(gross_value),
                    "avg_price": parse_number(avg_price),
                    "frequency": parse_number(item_dict.get("freq")),
                    "raw_item_json": json.dumps(item, ensure_ascii=False),
                }
            )
    if not rows:
        rows.append(
            {
                "ticker": ticker,
                "from_date": from_date,
                "to_date": to_date,
                "raw_item_json": json.dumps(broker_summary, ensure_ascii=False),
            }
        )
    return rows


def _extract_items(payload: Any) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []
    candidates = [
        payload.get("data"),
        payload.get("result"),
        payload.get("items"),
        payload.get("marketdetectors"),
    ]
    for candidate in candidates:
        if isinstance(candidate, list):
            return candidate
        if isinstance(candidate, dict):
            nested = _extract_items(candidate)
            if nested:
                return nested
    for value in payload.values():
        if isinstance(value, list) and value and isinstance(value[0], dict):
            return value
    return []


def _pick(data: dict[str, Any], keys: list[str]) -> Any:
    lowered = {str(key).lower(): value for key, value in data.items()}
    for key in keys:
        if key in data:
            return data[key]
        if key.lower() in lowered:
            return lowered[key.lower()]
    return None


def normalize_marketdetector_payload(
    payload: dict[str, Any],
    ticker: str,
    from_date: str,
    to_date: str,
) -> list[dict[str, Any]]:
    rows = []
    for index, item in enumerate(_extract_items(payload), start=1):
        item_dict = item if isinstance(item, dict) else {"value": item}
        buyer = _pick(item_dict, ["buyer", "buyer_code", "broker_buyer", "bidder"])
        seller = _pick(item_dict, ["seller", "seller_code", "broker_seller", "offer"])
        rows.append(
            {
                "ticker": ticker,
                "from_date": from_date,
                "to_date": to_date,
                "rank": parse_number(_pick(item_dict, ["rank"])) or index,
                "buyer_code": _pick(item_dict, ["buyer_code", "buyerCode", "buyer"]) if not isinstance(buyer, dict) else _pick(buyer, ["code", "broker_code", "name"]),
                "buyer_value": parse_number(_pick(item_dict, ["buyer_value", "buyerValue", "buy_value", "buyval"]) if not isinstance(buyer, dict) else _pick(buyer, ["value", "net_value", "amount"])),
                "buyer_lot": parse_number(_pick(item_dict, ["buyer_lot", "buyerLot", "buy_lot"]) if not isinstance(buyer, dict) else _pick(buyer, ["lot", "lots"])),
                "buyer_avg": parse_number(_pick(item_dict, ["buyer_avg", "buyerAvg", "buy_avg", "buyer_average"]) if not isinstance(buyer, dict) else _pick(buyer, ["avg", "average", "avg_price"])),
                "seller_code": _pick(item_dict, ["seller_code", "sellerCode", "seller"]) if not isinstance(seller, dict) else _pick(seller, ["code", "broker_code", "name"]),
                "seller_value": parse_number(_pick(item_dict, ["seller_value", "sellerValue", "sell_value", "sellval"]) if not isinstance(seller, dict) else _pick(seller, ["value", "net_value", "amount"])),
                "seller_lot": parse_number(_pick(item_dict, ["seller_lot", "sellerLot", "sell_lot"]) if not isinstance(seller, dict) else _pick(seller, ["lot", "lots"])),
                "seller_avg": parse_number(_pick(item_dict, ["seller_avg", "sellerAvg", "sell_avg", "seller_average"]) if not isinstance(seller, dict) else _pick(seller, ["avg", "average", "avg_price"])),
                "raw_item_json": json.dumps(item, ensure_ascii=False),
            }
        )
    if not rows:
        rows.append(
            {
                "ticker": ticker,
                "from_date": from_date,
                "to_date": to_date,
                "rank": None,
                "raw_item_json": json.dumps(payload, ensure_ascii=False),
            }
        )
    return rows


def run_stage3a_broker_collector(
    input_path: str | Path,
    output_path: str | Path,
    raw_dir: str | Path,
    from_date: str,
    to_date: str,
    config: StockbitCollectorConfig,
) -> pd.DataFrame:
    watchlist = load_stage2_bandar_watchlist(input_path)
    token = get_stockbit_token()
    print(f"Stage 3A watchlist tickers: {len(watchlist)}")

    detector_rows: list[dict[str, Any]] = []
    broker_rows: list[dict[str, Any]] = []
    success = failed = unauthorized = rate_limited = 0
    for _, row in watchlist.iterrows():
        ticker = str(row["ticker"]).replace(".JK", "")
        try:
            payload = fetch_marketdetector(ticker, from_date, to_date, config, token=token)
            save_raw_json(payload, ticker, from_date, to_date, raw_dir)
            detector_rows.append(normalize_bandar_detector_summary(payload, ticker, from_date, to_date))
            broker_rows.extend(normalize_broker_summary_long(payload, ticker, from_date, to_date))
            success += 1
        except RuntimeError as exc:
            failed += 1
            if "expired/invalid" in str(exc):
                unauthorized += 1
            print(f"{ticker}: {exc}")
        except HTTPError as exc:
            failed += 1
            if exc.code == 401:
                unauthorized += 1
            if exc.code == 429:
                rate_limited += 1
            print(f"{ticker}: HTTP {exc.code}")
        except Exception as exc:
            failed += 1
            print(f"{ticker}: fetch_failed {exc}")
        time.sleep(config.sleep_seconds)

    broker_output = pd.DataFrame(broker_rows)
    broker_path = Path(output_path)
    broker_path.parent.mkdir(parents=True, exist_ok=True)
    broker_output.to_csv(broker_path, index=False)

    detector_output = pd.DataFrame(detector_rows)
    detector_path = broker_path.with_name("stage3a_bandar_detector_summary.csv")
    detector_output.to_csv(detector_path, index=False)
    print(f"Fetched success: {success}")
    print(f"Failed: {failed}")
    print(f"401 count: {unauthorized}")
    print(f"429 count: {rate_limited}")
    print(f"Broker summary output path: {broker_path}")
    print(f"Bandar detector summary path: {detector_path}")
    print(f"Raw dir path: {raw_dir}")
    return broker_output
