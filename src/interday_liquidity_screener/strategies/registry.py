from __future__ import annotations

from interday_liquidity_screener.constants import WatchlistStatus
from .base import StrategyDefinition, StrategyEvaluation, present


DEFINITIONS = {
    "breakout": StrategyDefinition("breakout", "liquid and near prior resistance", "price challenges prior high",
        "close/stop-entry crosses prior resistance", "close falls below breakout structure", "below breakout or ATR stop",
        "2-3% net-feasible target", 3, ("RISK_ON", "NEUTRAL", "UNKNOWN"),
        ("close", "resistance_level", "avg_value_20d"), ("broker_flow", "orderbook", "market_breadth")),
    "pullback": StrategyDefinition("pullback", "uptrend and price near MA20", "controlled retracement in trend",
        "positive close reclaims MA20", "close loses MA50/structure", "below pullback low or ATR stop",
        "prior high or net-feasible target", 3, ("RISK_ON", "NEUTRAL", "UNKNOWN"),
        ("close", "ma20", "ma50"), ("broker_flow", "orderbook")),
    "rebound": StrategyDefinition("rebound", "price near prior low with valid liquidity", "reversal attempt from support",
        "positive return and strong close location", "prior low breaks", "below prior low", "2-3% net-feasible target",
        2, ("RISK_ON", "NEUTRAL", "UNKNOWN"), ("close", "support_level", "return_1d", "clv"), ("broker_flow", "orderbook")),
    "momentum_continuation": StrategyDefinition("momentum_continuation", "established uptrend", "trend continues with activity",
        "positive return with relative activity", "momentum or MA structure fails", "ATR/trailing structure stop",
        "volatility-aware target", 3, ("RISK_ON", "NEUTRAL", "UNKNOWN"),
        ("close", "ma20", "ma50", "return_1d"), ("rvol", "broker_flow", "orderbook")),
    "smart_money_discovery": StrategyDefinition("smart_money_discovery", "multi-window accumulation is present",
        "broker accumulation precedes chart confirmation", "technical setup confirms accumulation", "distribution replaces accumulation",
        "no execution stop until technical trigger", "watchlist target only", 3,
        ("RISK_ON", "NEUTRAL", "RISK_OFF", "UNKNOWN"), ("accumulation_window_count",),
        ("technical_confirmation", "orderbook")),
    "sideways_compression": StrategyDefinition("sideways_compression", "liquid low-volatility range",
        "price compresses below resistance", "close breaks above resistance with activity",
        "below compression floor", "below compression floor", "range expansion target", 3, ("RISK_ON", "NEUTRAL", "UNKNOWN"),
        ("close", "resistance_level", "support_level"), ("broker_flow", "orderbook", "rvol")),
}


def _number(row: dict, key: str, default: float = 0.0) -> float:
    try:
        return float(row.get(key, default))
    except (TypeError, ValueError):
        return default


def _select(row: dict) -> str:
    setup = str(row.get("entry_setup", "")).upper()
    context = str(row.get("technical_context", "")).upper()
    if "SIDEWAYS_COMPRESSION" in {setup, context}:
        return "sideways_compression"
    if "BREAKOUT" in setup or "BREAKOUT" in context:
        return "breakout"
    if "PULLBACK" in setup or "PULLBACK" in context:
        return "pullback"
    if "REBOUND" in setup or "REBOUND" in context or "REVERSAL" in context:
        return "rebound"
    if "UPTREND_CONTINUATION" in context or setup == "WATCH_ENTRY":
        return "momentum_continuation"
    if _number(row, "accumulation_window_count") > 0 or "ACCUMULATION" in str(row.get("bandarmology_signal", "")):
        return "smart_money_discovery"
    return "momentum_continuation"


def evaluate_strategy(row: dict) -> StrategyEvaluation:
    name = _select(row)
    definition = DEFINITIONS[name]
    missing = [field for field in definition.required_features if not present(row, field)]
    regime = str(row.get("market_regime", "UNKNOWN")).upper()
    regime_allowed = regime in definition.allowed_market_regimes
    eligible = not missing and regime_allowed
    explicit_trigger = row.get("entry_trigger_touched")
    if explicit_trigger is not None:
        trigger = bool(explicit_trigger)
    elif name == "breakout":
        trigger = _number(row, "close") >= _number(row, "resistance_level", float("inf"))
    elif name == "pullback":
        trigger = _number(row, "close") >= _number(row, "ma20", float("inf")) and _number(row, "return_1d") > 0
    elif name == "rebound":
        trigger = _number(row, "return_1d") > 0 and _number(row, "clv", 0.5) >= 0.6
    elif name == "momentum_continuation":
        trigger = _number(row, "return_1d") > 0 and _number(row, "rvol", 1.0) >= 1.0
    elif name == "sideways_compression":
        trigger = _number(row, "close") > _number(row, "resistance_level", float("inf")) and _number(row, "rvol") >= 1.0
    else:
        trigger = False
    cap = WatchlistStatus.EXECUTION_READY if eligible and trigger else (
        WatchlistStatus.READY_SOON if eligible else WatchlistStatus.WATCHLIST
    )
    if name == "smart_money_discovery" and not trigger:
        cap = WatchlistStatus.READY_SOON
    reasons = tuple([
        *(f"missing_required:{field}" for field in missing),
        *([] if regime_allowed else [f"market_regime_not_allowed:{regime}"]),
        *([] if trigger else ["entry_trigger_not_touched"]),
    ])
    return StrategyEvaluation(definition, eligible, trigger, cap, reasons)


__all__ = ["DEFINITIONS", "evaluate_strategy"]
