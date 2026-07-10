from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
import pandas as pd
from typing import Any

import os
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from .orderbook_filter import OrderbookFilterConfig, fetch_orderbook, normalize_orderbook_payload, classify_orderbook
from .stockbit_collector import get_stockbit_token

class LiveTickerMonitor:
    def __init__(
        self,
        watchlist_path: str | Path,
        status_output_path: str | Path = "data/output/live_monitor_status.json",
        config: OrderbookFilterConfig | None = None
    ):
        self.watchlist_path = Path(watchlist_path)
        self.status_output_path = Path(status_output_path)
        self.config = config or OrderbookFilterConfig()
        self.monitored_tickers: list[dict[str, Any]] = []
        self.token = get_stockbit_token()
        self.sent_alerts: set[str] = set()

    def load_candidates(self) -> list[dict[str, Any]]:
        if not self.watchlist_path.exists():
            print(f"Warning: Watchlist CSV not found at {self.watchlist_path}")
            return []
        try:
            df = pd.read_csv(self.watchlist_path)
        except Exception as e:
            print(f"Error loading watchlist: {e}")
            return []

        valid_statuses = {"VALID_TRADE_PLAN", "ENTRY_READY", "EXECUTION_READY", "READY_SOON", "EARLY_WATCH"}
        candidates = []
        for _, row in df.iterrows():
            status_val = row.get("trade_status")
            if pd.isna(status_val) or not status_val or str(status_val).lower() == "nan":
                status_val = row.get("final_status")
            status = str(status_val) if pd.notna(status_val) and str(status_val).lower() != "nan" else ""
            ticker = str(row.get("ticker", ""))
            
            is_valid = status in valid_statuses or status.startswith("WATCH_")
            if is_valid and ticker:
                candidates.append({
                    "ticker": ticker.replace(".JK", ""),
                    "close": float(row.get("close", 0)),
                    "entry_price": float(row.get("entry_price", 0)) if pd.notna(row.get("entry_price")) else None,
                    "stop_loss": float(row.get("stop_loss", 0)) if pd.notna(row.get("stop_loss")) else None,
                    "take_profit_1": float(row.get("take_profit_1", 0)) if pd.notna(row.get("take_profit_1")) else None,
                    "take_profit_2": float(row.get("take_profit_2", 0)) if pd.notna(row.get("take_profit_2")) else None,
                    "trade_status": status,
                    "trade_reason": str(row.get("trade_reason", ""))
                })
        return candidates

    def is_market_open(self, bypass: bool = False) -> bool:
        if bypass:
            return True
        jakarta_tz = timezone(timedelta(hours=7))
        now_jkt = datetime.now(jakarta_tz)
        
        if now_jkt.weekday() > 4:
            return False
            
        start_time = now_jkt.replace(hour=9, minute=0, second=0, microsecond=0)
        end_time = now_jkt.replace(hour=16, minute=0, second=0, microsecond=0)
        return start_time <= now_jkt <= end_time

    def process_ticker(self, candidate: dict[str, Any]) -> dict[str, Any]:
        ticker = candidate["ticker"]
        result = candidate.copy()
        
        try:
            payload = fetch_orderbook(ticker, self.config, token=self.token)
            normalized = normalize_orderbook_payload(payload, ticker, self.config)
            orderbook_status = classify_orderbook(normalized, self.config)
            
            last_price = normalized.get("lastprice")
            result.update({
                "live_price": last_price,
                "best_bid": normalized.get("best_bid"),
                "best_offer": normalized.get("best_offer"),
                "bid_volume": normalized.get("bid_volume_top5"),
                "offer_volume": normalized.get("offer_volume_top5"),
                "orderbook_status": orderbook_status,
                "fetched_at": datetime.now().isoformat(),
                "error": None
            })
            
            alerts = []
            if last_price:
                if candidate["stop_loss"] and last_price <= candidate["stop_loss"]:
                    alerts.append("STOP_LOSS_TRIGGERED")
                
                if candidate["take_profit_2"] and last_price >= candidate["take_profit_2"]:
                    alerts.append("TP2_TRIGGERED")
                elif candidate["take_profit_1"] and last_price >= candidate["take_profit_1"]:
                    alerts.append("TP1_TRIGGERED")
                
                if candidate["entry_price"] and candidate["stop_loss"]:
                    in_entry_zone = candidate["stop_loss"] < last_price <= candidate["entry_price"] * 1.005
                    if in_entry_zone and orderbook_status in {"ORDERBOOK_SUPPORTIVE", "ORDERBOOK_NEUTRAL"}:
                        alerts.append("ENTRY_ZONE_SUPPORTIVE")
                    elif in_entry_zone:
                        alerts.append("ENTRY_ZONE_PENDING_ORDERBOOK")
                        
            result["alerts"] = alerts
            
        except Exception as e:
            result.update({
                "live_price": None,
                "orderbook_status": "FETCH_FAILED",
                "fetched_at": datetime.now().isoformat(),
                "error": str(e),
                "alerts": []
            })
        return result

    def send_telegram_alert(self, res: dict[str, Any], alert: str) -> None:
        ticker = res["ticker"]
        live_price = res.get("live_price")
        orderbook_status = res.get("orderbook_status", "UNKNOWN")
        
        emoji = "⚠️"
        title = alert.replace("_", " ")
        details = ""
        
        if alert == "STOP_LOSS_TRIGGERED":
            emoji = "🚨"
            title = "STOP LOSS TRIGGERED"
            details = (
                f"• Live Price: <b>Rp {live_price:,.0f}</b>\n"
                f"• Stop Loss: Rp {res.get('stop_loss', 0):,.0f}\n"
                f"• Plan Entry: Rp {res.get('entry_price', 0):,.0f}"
            )
        elif alert in {"TP1_TRIGGERED", "TP2_TRIGGERED"}:
            emoji = "🎉" if alert == "TP2_TRIGGERED" else "💰"
            title = "TAKE PROFIT TRIGGERED" if alert == "TP1_TRIGGERED" else "TP2 TARGET REACHED"
            target_key = "take_profit_2" if alert == "TP2_TRIGGERED" else "take_profit_1"
            details = (
                f"• Live Price: <b>Rp {live_price:,.0f}</b>\n"
                f"• Target Price: Rp {res.get(target_key, 0):,.0f}"
            )
        elif alert == "ENTRY_ZONE_SUPPORTIVE":
            emoji = "🟢"
            title = "ENTRY BUY TRIGGER"
            details = (
                f"• Live Price: <b>Rp {live_price:,.0f}</b> (Zone: &lt;= Rp {res.get('entry_price', 0)*1.005:,.0f})\n"
                f"• Stop Loss: Rp {res.get('stop_loss', 0):,.0f}\n"
                f"• Orderbook: {orderbook_status} (Supportive)"
            )
        elif alert == "ENTRY_ZONE_PENDING_ORDERBOOK":
            emoji = "⏳"
            title = "ENTRY ZONE REACHED"
            details = (
                f"• Live Price: <b>Rp {live_price:,.0f}</b>\n"
                f"• Stop Loss: Rp {res.get('stop_loss', 0):,.0f}\n"
                f"• Orderbook: {orderbook_status} (Wait Supportive)"
            )
        else:
            details = f"• Live Price: Rp {live_price:,.0f}\n• Orderbook: {orderbook_status}"

        message = (
            f"{emoji} <b>{title}: {ticker}</b> {emoji}\n\n"
            f"{details}\n"
            f"• Waktu: {datetime.now().strftime('%H:%M:%S')} JKT"
        )
        
        token = os.getenv("TELEGRAM_TOKEN")
        chat_id = os.getenv("TELEGRAM_CHAT_ID")
        
        if not token or not chat_id:
            print(f"[Telegram Alert] {ticker} - {alert} triggered, but TELEGRAM_TOKEN/TELEGRAM_CHAT_ID not configured.")
            return

        from urllib.request import Request, urlopen
        import json
        
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML"
        }
        headers = {"Content-Type": "application/json"}
        
        try:
            data = json.dumps(payload).encode("utf-8")
            req = Request(url, data=data, headers=headers, method="POST")
            with urlopen(req, timeout=10) as response:
                if response.status == 200:
                    print(f"[Telegram Alert] Notification sent for {ticker} ({alert}).")
                else:
                    print(f"[Telegram Alert] Failed to send. Status: {response.status}")
        except Exception as e:
            print(f"[Telegram Alert] Request failed: {e}")

    def monitor_once(self, bypass_market_hours: bool = False) -> list[dict[str, Any]]:
        if not self.is_market_open(bypass_market_hours):
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Market is closed (outside trading hours or weekend).")
            return []

        candidates = self.load_candidates()
        if not candidates:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] No candidates to monitor.")
            return []

        print(f"\n--- Live Market Scan: Monitoring {len(candidates)} tickers ---")
        monitored = []
        for c in candidates:
            res = self.process_ticker(c)
            monitored.append(res)
            
            for alert in res.get("alerts", []):
                alert_key = f"{res['ticker']}_{alert}"
                if alert_key not in self.sent_alerts:
                    self.send_telegram_alert(res, alert)
                    self.sent_alerts.add(alert_key)
            
            alert_str = f" | Alerts: {', '.join(res['alerts'])}" if res["alerts"] else ""
            print(f"[{res['ticker']}] Live: {res['live_price']} (Plan Entry: {res['entry_price']}) | Orderbook: {res['orderbook_status']}{alert_str}")
            time.sleep(self.config.sleep_seconds)

        self.status_output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.status_output_path, "w", encoding="utf-8") as f:
            json.dump(monitored, f, indent=2)
            
        return monitored

    def start_monitoring_loop(self, interval_seconds: float = 300.0, bypass_market_hours: bool = False) -> None:
        print(f"Starting Live Ticker Monitor loop (every {interval_seconds}s). Press Ctrl+C to exit.")
        try:
            while True:
                self.monitor_once(bypass_market_hours=bypass_market_hours)
                time.sleep(interval_seconds)
        except KeyboardInterrupt:
            print("Live monitor daemon stopped by user.")
