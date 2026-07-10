from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from urllib.request import Request, urlopen
import pandas as pd
from typing import Any

from .stockbit_collector import get_stockbit_token, _headers

@dataclass
class BandarTrackerConfig:
    whitelist_brokers: list[str] = field(default_factory=lambda: ["AK", "ZP", "BK", "XL", "RX", "KZ", "YJ"])
    track_investor_type: str = "INVESTOR_TYPE_FOREIGN"
    track_period: str = "RT_PERIOD_LAST_7_DAYS"
    min_accumulation_value: float = 1000000000.0

    @classmethod
    def load_from_file(cls, path: str | Path) -> BandarTrackerConfig:
        p = Path(path)
        if not p.exists():
            return cls()
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            return cls(
                whitelist_brokers=data.get("whitelist_brokers", ["AK", "ZP", "BK", "XL", "RX", "KZ", "YJ"]),
                track_investor_type=data.get("track_investor_type", "INVESTOR_TYPE_FOREIGN"),
                track_period=data.get("track_period", "RT_PERIOD_LAST_7_DAYS"),
                min_accumulation_value=float(data.get("min_accumulation_value", 1000000000.0))
            )
        except Exception as e:
            print(f"Error loading bandar tracker config: {e}. Using defaults.")
            return cls()

def fetch_broker_activity_multi(
    brokers: list[str],
    investor_type: str,
    period: str,
    token: str | None = None,
    limit: int = 100
) -> dict[str, Any]:
    token = token or get_stockbit_token()
    
    param_pairs = [f"broker_code={b}" for b in brokers]
    param_pairs.extend([
        f"limit={limit}",
        "page=1",
        "transaction_type=TRANSACTION_TYPE_NET",
        "market_board=MARKET_TYPE_REGULER",
        f"investor_type={investor_type}",
        f"period={period}"
    ])
    
    query_str = "&".join(param_pairs)
    url = f"https://exodus.stockbit.com/order-trade/broker/activity?{query_str}"
    
    request = Request(url, headers=_headers(token), method="GET")
    with urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))

def aggregate_bandar_accum(payload: dict[str, Any]) -> pd.DataFrame:
    data = payload.get("data", {})
    tx = data.get("broker_activity_transaction", {})
    buys = tx.get("brokers_buy", [])
    
    if not buys:
        return pd.DataFrame()
        
    records = []
    for item in buys:
        ticker = item.get("stock_code")
        value = float(item.get("value", 0))
        lot = float(item.get("lot", 0))
        freq = int(item.get("freq", 0))
        
        detail = item.get("company_detail", {})
        corpaction = detail.get("corpaction", {}).get("active", False)
        notations = detail.get("notation", [])
        if isinstance(notations, list):
            notations_list = []
            for n in notations:
                if isinstance(n, dict):
                    notations_list.append(str(n.get("code", "")))
                elif n is not None:
                    notations_list.append(str(n))
            notations_str = ",".join(notations_list)
        else:
            notations_str = str(notations) if notations is not None else ""
        
        records.append({
            "ticker": f"{ticker}.JK",
            "net_buy_value": value,
            "net_buy_lot": lot,
            "frequency": freq,
            "corp_action_active": corpaction,
            "special_notations": notations_str
        })
        
    df = pd.DataFrame(records)
    
    agg = df.groupby("ticker").agg({
        "net_buy_value": "sum",
        "net_buy_lot": "sum",
        "frequency": "sum",
        "corp_action_active": "max",
        "special_notations": "first"
    }).reset_index()
    
    agg["avg_price"] = agg.apply(
        lambda r: r["net_buy_value"] / (r["net_buy_lot"] * 100) if r["net_buy_lot"] > 0 else 0,
        axis=1
    )
    
    agg = agg.sort_values(by="net_buy_value", ascending=False).reset_index(drop=True)
    return agg

def run_bandar_scan(
    config_path: str | Path,
    output_path: str | Path = "data/output/bandar_scan_results.csv",
    force_refresh: bool = False,
    override_investor_type: str | None = None,
    override_period: str | None = None
) -> pd.DataFrame:
    config = BandarTrackerConfig.load_from_file(config_path)
    investor_type = override_investor_type or config.track_investor_type
    period = override_period or config.track_period
    
    today_str = date.today().isoformat()
    cache_dir = Path("data/cache")
    cache_file = cache_dir / f"bandar_scan_{investor_type}_{period}_{today_str}.json"
    
    payload = None
    if not force_refresh and cache_file.exists():
        print(f"Loading broker activity from daily cache: {cache_file.name}")
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                payload = json.load(f)
        except Exception as e:
            print(f"Failed to read cache file: {e}. Re-fetching.")
            payload = None

    if payload is None:
        print(f"Fetching live activity for {len(config.whitelist_brokers)} brokers from Stockbit...")
        try:
            payload = fetch_broker_activity_multi(
                brokers=config.whitelist_brokers,
                investor_type=investor_type,
                period=period
            )
            cache_dir.mkdir(parents=True, exist_ok=True)
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Error fetching from Stockbit: {e}")
            return pd.DataFrame()

    df_agg = aggregate_bandar_accum(payload)
    if df_agg.empty:
        print("No buy transactions found for target brokers.")
        return pd.DataFrame()
        
    filtered = df_agg[df_agg["net_buy_value"] >= config.min_accumulation_value].copy()
    
    out_p = Path(output_path)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    filtered.to_csv(out_p, index=False)
    
    return filtered
