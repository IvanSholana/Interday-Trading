from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path
from urllib.request import Request, urlopen
from typing import Any

from .stockbit_collector import get_stockbit_token, _headers

COMMODITY_MAP = {
    # Coal
    "ADRO": "COAL-NEWCASTLE",
    "PTBA": "COAL-NEWCASTLE",
    "ITMG": "COAL-NEWCASTLE",
    "HRUM": "COAL-NEWCASTLE",
    "BUMI": "COAL-NEWCASTLE",
    "DEWA": "COAL-NEWCASTLE",
    "BSSR": "COAL-NEWCASTLE",
    "INDY": "COAL-NEWCASTLE",
    # Gold / Silver / Copper
    "ANTM": "XAU",
    "MDKA": "XAU",
    "BRMS": "XAU",
    "PSAB": "XAU",
    "DKFT": "XAU",
    # Nickel
    "INCO": "NICKEL",
    "MBMA": "NICKEL",
    "NICL": "NICKEL",
    # Oil & Gas
    "MEDC": "OIL",
    "ELSA": "OIL",
    "PGAS": "GAS",
    "ENRG": "OIL",
    # Tin
    "TINS": "TIN",
    # CPO
    "AALI": "CPO",
    "LSIP": "CPO",
    "TAPG": "CPO",
    "DSNG": "CPO",
    "SSMS": "CPO",
    "BWPT": "CPO"
}

def fetch_live_commodities(token: str | None = None, force_refresh: bool = False) -> dict[str, dict[str, Any]]:
    today_str = date.today().isoformat()
    cache_dir = Path("data/cache")
    cache_file = cache_dir / f"commodities_{today_str}.json"
    
    if not force_refresh and cache_file.exists():
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass

    token = token or get_stockbit_token()
    url = "https://exodus.stockbit.com/emitten/v3/sector/73/subsector/74/company"
    
    try:
        request = Request(url, headers=_headers(token), method="GET")
        with urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
            data = payload.get("data", [])
            
            # Index by symbol for quick O(1) lookups
            indexed = {}
            for item in data:
                symbol = item.get("symbol")
                if symbol:
                    indexed[symbol] = {
                        "symbol": symbol,
                        "name": item.get("name"),
                        "last": float(item.get("last", 0)) if item.get("last") else 0.0,
                        "percent": float(item.get("percent", 0)) if item.get("percent") else 0.0
                    }
                    
            # Save cache
            cache_dir.mkdir(parents=True, exist_ok=True)
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(indexed, f, ensure_ascii=False, indent=2)
                
            return indexed
    except Exception as e:
        print(f"Error fetching commodities: {e}")
        # Return empty or load cached fallback even if expired
        if cache_file.exists():
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

def evaluate_commodity_sentiment(ticker: str, threshold: float = -1.5, token: str | None = None) -> tuple[bool, float, str]:
    clean_ticker = ticker.replace(".JK", "").upper()
    if clean_ticker not in COMMODITY_MAP:
        return False, 0.0, ""
        
    commodity_code = COMMODITY_MAP[clean_ticker]
    commodities = fetch_live_commodities(token=token)
    
    if commodity_code not in commodities:
        return False, 0.0, ""
        
    item = commodities[commodity_code]
    change_pct = item.get("percent", 0.0)
    is_headwind = change_pct < threshold
    
    return is_headwind, change_pct, item.get("name", "")
