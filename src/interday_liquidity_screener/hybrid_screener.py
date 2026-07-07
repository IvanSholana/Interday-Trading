from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from pathlib import Path
from typing import Any
import json
import math

import pandas as pd

from .orderbook_filter import is_corp_action_active, is_notation_risky
from .trade_plan import get_idx_tick_size, round_price_to_tick


HYBRID_MODES = {
    "weekend_preparation",
    "normal_execution",
    "smart_money_first",
    "bpjs_live",
    "interday_swing",
    "hybrid_dual_flow",
}

REQUIRED_STATUSES = {
    "EARLY_WATCH",
    "READY_SOON",
    "EXECUTION_DRAFT",
    "NEED_ORDERBOOK",
    "EXECUTION_CANDIDATE",
    "EXECUTION_READY",
    "SKIP",
    "DANGER_CHASING",
    "DISTRIBUTION_WARNING",
    "ORDERBOOK_WEAK",
    "ORDERBOOK_REJECT",
    "LOW_LIQUIDITY",
    "NET_PROFIT_NOT_WORTH_IT",
    "TOO_EXPENSIVE_FOR_CAPITAL",
    "RISK_REWARD_BAD",
    "DATA_INSUFFICIENT",
}

OUTPUT_COLUMNS = [
    "symbol",
    "name",
    "date",
    "mode",
    "final_status",
    "final_score",
    "rank",
    "flow_source",
    "liquidity_score",
    "technical_score",
    "smart_money_score",
    "price_extension_score",
    "market_regime_score",
    "sector_strength_score",
    "orderbook_score",
    "risk_plan_score",
    "net_profit_feasibility_score",
    "avg_value_20d",
    "avg_frequency_20d",
    "rvol",
    "return_1d",
    "return_3d",
    "return_5d",
    "return_20d",
    "ma20",
    "ma50",
    "distance_ma20",
    "distance_ma50",
    "rsi",
    "atr_pct",
    "clv",
    "support_level",
    "resistance_level",
    "broker_net_buy_1d",
    "broker_net_buy_3d",
    "broker_net_buy_5d",
    "broker_net_buy_10d",
    "broker_net_buy_20d",
    "accumulation_window_count",
    "distribution_window_count",
    "top_buyer",
    "top_buyer_avg_price",
    "top3_buyer_dominance",
    "top_seller",
    "top_seller_avg_price",
    "top3_seller_dominance",
    "hhi_buyer",
    "hhi_seller",
    "close_vs_top_buyer_avg_pct",
    "spread_ticks",
    "spread_pct",
    "best_bid",
    "best_offer",
    "bid_depth_5",
    "offer_depth_5",
    "bid_offer_ratio_5",
    "offer_wall_ratio",
    "frequency_live",
    "value_live",
    "entry_price",
    "tp1_price",
    "tp2_price",
    "stop_loss_price",
    "target_tp_pct",
    "stop_loss_pct",
    "estimated_buy_fee",
    "estimated_sell_fee",
    "estimated_slippage",
    "gross_profit",
    "net_profit_after_fee",
    "risk_amount",
    "reward_amount",
    "risk_reward_ratio",
    "affordable_lot",
    "position_value",
    "capital_profile",
    "warnings",
    "skip_reasons",
    "explanation",
]


@dataclass(frozen=True)
class CapitalProfile:
    capital: float
    max_position_pct: float
    max_stock_price: float
    preferred_price_min: float
    preferred_price_max: float
    min_gross_tp_pct: float
    target_tp_pct_default: float
    stop_loss_pct_default: float


@dataclass(frozen=True)
class FeesConfig:
    buy_fee_pct: float = 0.0015
    sell_fee_pct: float = 0.0025
    round_trip_fee_pct_fallback: float = 0.0045
    minimum_buy_fee: float = 0.0
    minimum_sell_fee: float = 0.0
    slippage_pct_default: float = 0.001


@dataclass(frozen=True)
class LiquidityConfig:
    min_avg_value_20d: float = 2_000_000_000
    min_avg_frequency_20d: float = 500
    min_avg_volume_20d: float = 1_000_000
    min_rvol: float = 0.8
    good_rvol: float = 1.5


@dataclass(frozen=True)
class PriceExtensionConfig:
    max_return_1d_safe: float = 0.05
    max_return_3d_safe: float = 0.10
    max_return_5d_safe: float = 0.15
    max_distance_ma20_safe: float = 0.10
    danger_distance_ma20: float = 0.15
    max_distance_top_buyer_avg_safe: float = 0.07


@dataclass(frozen=True)
class TechnicalConfig:
    rsi_min: float = 40
    rsi_ideal_min: float = 45
    rsi_ideal_max: float = 70
    rsi_overbought: float = 75
    clv_good: float = 0.70
    clv_strong: float = 0.80
    ma20_distance_min: float = -0.05
    ma20_distance_max: float = 0.10


@dataclass(frozen=True)
class SmartMoneyConfig:
    accumulation_lookbacks: list[int] = field(default_factory=lambda: [1, 3, 5, 10, 20])
    min_accumulation_consistency: int = 3
    strong_accumulation_consistency: int = 4
    top3_buyer_dominance_good: float = 0.50
    top3_buyer_dominance_strong: float = 0.70
    max_close_vs_top_buyer_avg_safe: float = 0.07
    distribution_penalty_threshold: int = 3
    strong_distribution_threshold: int = 4


@dataclass(frozen=True)
class OrderbookConfig:
    max_spread_ticks_bpjs: int = 1
    max_spread_pct_bpjs: float = 0.005
    min_bid_offer_ratio: float = 0.8
    ideal_bid_offer_ratio_min: float = 1.1
    ideal_bid_offer_ratio_max: float = 3.0
    fake_bid_ratio_warning: float = 5.0
    offer_wall_ratio_warning: float = 5.0
    min_frequency_open_5m: int = 50
    min_value_open_5m: float = 100_000_000
    top_levels: int = 5


@dataclass(frozen=True)
class WatchlistConfig:
    max_candidates_bpjs: int = 5
    max_candidates_default: int = 10


@dataclass(frozen=True)
class RiskConfig:
    minimum_net_profit: float = 5_000
    minimum_risk_reward: float = 1.2
    lot_size: int = 100


@dataclass(frozen=True)
class SafetyConfig:
    hard_skip_uma: bool = True
    hard_skip_special_notation: bool = True
    hard_skip_corporate_action: bool = True
    hard_skip_fca: bool = True
    hard_market_regime_risk_off: bool = False
    hard_sector_downtrend: bool = False


@dataclass(frozen=True)
class HybridScreenerConfig:
    capital_profiles: dict[str, CapitalProfile] = field(
        default_factory=lambda: {
            "capital_500k": CapitalProfile(500_000, 1.0, 5_000, 50, 500, 0.015, 0.02, 0.01),
            "capital_1m": CapitalProfile(1_000_000, 1.0, 10_000, 50, 1_000, 0.015, 0.02, 0.01),
            "capital_1_5m": CapitalProfile(1_500_000, 1.0, 15_000, 50, 1_500, 0.015, 0.02, 0.01),
        }
    )
    fees: FeesConfig = field(default_factory=FeesConfig)
    liquidity: LiquidityConfig = field(default_factory=LiquidityConfig)
    price_extension: PriceExtensionConfig = field(default_factory=PriceExtensionConfig)
    technical: TechnicalConfig = field(default_factory=TechnicalConfig)
    smart_money: SmartMoneyConfig = field(default_factory=SmartMoneyConfig)
    orderbook: OrderbookConfig = field(default_factory=OrderbookConfig)
    watchlist: WatchlistConfig = field(default_factory=WatchlistConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    safety: SafetyConfig = field(default_factory=SafetyConfig)
    weights: dict[str, dict[str, float]] = field(
        default_factory=lambda: {
            "bpjs_live": {
                "liquidity_score": 0.25,
                "orderbook_score": 0.30,
                "net_profit_feasibility_score": 0.15,
                "technical_score": 0.10,
                "smart_money_score": 0.10,
                "price_extension_score": 0.05,
                "market_sector_score": 0.05,
            },
            "smart_money_first": {
                "smart_money_score": 0.40,
                "price_extension_score": 0.20,
                "liquidity_score": 0.15,
                "technical_score": 0.15,
                "market_sector_score": 0.10,
            },
            "interday_swing": {
                "smart_money_score": 0.25,
                "technical_score": 0.25,
                "market_sector_score": 0.15,
                "liquidity_score": 0.15,
                "price_extension_score": 0.10,
                "risk_plan_score": 0.10,
            },
            "normal_execution": {
                "liquidity_score": 0.25,
                "technical_score": 0.25,
                "smart_money_score": 0.20,
                "price_extension_score": 0.10,
                "risk_plan_score": 0.10,
                "market_sector_score": 0.10,
            },
            "weekend_preparation": {
                "liquidity_score": 0.20,
                "technical_score": 0.20,
                "smart_money_score": 0.25,
                "price_extension_score": 0.20,
                "market_sector_score": 0.15,
            },
            "hybrid_dual_flow": {
                "liquidity_score": 0.20,
                "technical_score": 0.20,
                "smart_money_score": 0.25,
                "price_extension_score": 0.15,
                "risk_plan_score": 0.10,
                "market_sector_score": 0.10,
            },
        }
    )


@dataclass(frozen=True)
class ScoreResult:
    score: float
    warnings: tuple[str, ...] = ()
    flags: tuple[str, ...] = ()


@dataclass(frozen=True)
class RiskPlan:
    entry_price: float | None
    tp1_price: float | None
    tp2_price: float | None
    stop_loss_price: float | None
    target_tp_pct: float
    stop_loss_pct: float
    estimated_buy_fee: float
    estimated_sell_fee: float
    estimated_slippage: float
    gross_profit: float
    net_profit_after_fee: float
    risk_amount: float
    reward_amount: float
    risk_reward_ratio: float
    affordable_lot: bool
    position_value: float
    lot: int
    risk_plan_score: float
    net_profit_feasibility_score: float
    warnings: tuple[str, ...] = ()
    skip_reasons: tuple[str, ...] = ()


def _safe_float(value: Any, default: float | None = None) -> float | None:
    if value is None:
        return default
    try:
        if pd.isna(value):
            return default
    except (TypeError, ValueError):
        pass
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    if math.isnan(parsed) or math.isinf(parsed):
        return default
    return parsed


def _safe_bool(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "y", "1.0", "active"}
    try:
        if pd.isna(value):
            return False
    except (TypeError, ValueError):
        pass
    return bool(value)


def _clip(value: float, low: float = 0, high: float = 100) -> float:
    return max(low, min(high, float(value)))


def _pct_score(value: float | None, threshold: float, weight: float) -> float:
    if value is None or threshold <= 0:
        return 0.0
    return min(max(value / threshold, 0), 1.0) * weight


def _first(row: dict[str, Any], keys: list[str], default: Any = None) -> Any:
    for key in keys:
        if key in row and row.get(key) is not None:
            value = row.get(key)
            try:
                if pd.isna(value):
                    continue
            except (TypeError, ValueError):
                pass
            return value
    return default


def _as_plain(value: Any) -> Any:
    if is_dataclass(value):
        return {key: _as_plain(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {key: _as_plain(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_as_plain(item) for item in value]
    return value


def _parse_scalar(text: str) -> Any:
    text = text.strip()
    if text == "":
        return ""
    if text.startswith("[") and text.endswith("]"):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return [item.strip() for item in text[1:-1].split(",") if item.strip()]
    lowered = text.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    if lowered in {"null", "none"}:
        return None
    try:
        if any(char in text for char in [".", "e", "E"]):
            return float(text)
        return int(text)
    except ValueError:
        return text.strip("'\"")


def _simple_yaml_load(path: Path) -> dict[str, Any]:
    root: dict[str, Any] = {}
    stack: list[tuple[int, dict[str, Any]]] = [(-1, root)]
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip(" "))
        key_value = line.strip()
        if ":" not in key_value:
            continue
        key, raw_value = key_value.split(":", 1)
        key = key.strip()
        while stack and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]
        if raw_value.strip() == "":
            child: dict[str, Any] = {}
            parent[key] = child
            stack.append((indent, child))
        else:
            parent[key] = _parse_scalar(raw_value)
    return root


def _deep_update(base: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_update(result[key], value)
        else:
            result[key] = value
    return result


def _dataclass_from_dict(cls: type[Any], data: dict[str, Any]) -> Any:
    kwargs = {}
    annotations = getattr(cls, "__annotations__", {})
    for name, field_type in annotations.items():
        if name in data:
            kwargs[name] = data[name]
    return cls(**kwargs)


def config_from_dict(data: dict[str, Any]) -> HybridScreenerConfig:
    defaults = _as_plain(HybridScreenerConfig())
    merged = _deep_update(defaults, data)
    capital_profiles = {
        name: _dataclass_from_dict(CapitalProfile, value)
        for name, value in merged.get("capital_profiles", {}).items()
    }
    return HybridScreenerConfig(
        capital_profiles=capital_profiles,
        fees=_dataclass_from_dict(FeesConfig, merged.get("fees", {})),
        liquidity=_dataclass_from_dict(LiquidityConfig, merged.get("liquidity", {})),
        price_extension=_dataclass_from_dict(PriceExtensionConfig, merged.get("price_extension", {})),
        technical=_dataclass_from_dict(TechnicalConfig, merged.get("technical", {})),
        smart_money=_dataclass_from_dict(SmartMoneyConfig, merged.get("smart_money", {})),
        orderbook=_dataclass_from_dict(OrderbookConfig, merged.get("orderbook", {})),
        watchlist=_dataclass_from_dict(WatchlistConfig, merged.get("watchlist", {})),
        risk=_dataclass_from_dict(RiskConfig, merged.get("risk", {})),
        safety=_dataclass_from_dict(SafetyConfig, merged.get("safety", {})),
        weights=merged.get("weights", {}),
    )


def load_hybrid_config(path: str | Path | None = None) -> HybridScreenerConfig:
    if path is None:
        return HybridScreenerConfig()
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Hybrid screener config not found: {config_path}")
    if config_path.suffix.lower() == ".json":
        data = json.loads(config_path.read_text(encoding="utf-8"))
    else:
        data = _simple_yaml_load(config_path)
    return config_from_dict(data)


def normalize_candidate_row(row: dict[str, Any] | pd.Series) -> dict[str, Any]:
    raw = row.to_dict() if isinstance(row, pd.Series) else dict(row)
    symbol = str(_first(raw, ["symbol", "ticker", "code", "yahoo_ticker"], "") or "").replace(".JK", "")
    close = _safe_float(_first(raw, ["close", "lastprice", "last_price"]))
    ma20 = _safe_float(_first(raw, ["ma20", "MA20"]))
    ma50 = _safe_float(_first(raw, ["ma50", "MA50"]))
    distance_ma20 = _safe_float(_first(raw, ["distance_ma20", "distance_to_ma20"]))
    distance_ma50 = _safe_float(_first(raw, ["distance_ma50", "distance_to_ma50"]))
    if distance_ma20 is None and close is not None and ma20 not in {None, 0}:
        distance_ma20 = (close - float(ma20)) / float(ma20)
    if distance_ma50 is None and close is not None and ma50 not in {None, 0}:
        distance_ma50 = (close - float(ma50)) / float(ma50)
    normalized = dict(raw)
    normalized.update(
        {
            "symbol": symbol,
            "name": _first(raw, ["name", "company_name"], symbol),
            "date": _first(raw, ["date", "last_date", "as_of_date"]),
            "close": close,
            "avg_value_20d": _safe_float(_first(raw, ["avg_value_20d", "average_value_20d"])),
            "avg_volume_20d": _safe_float(_first(raw, ["avg_volume_20d", "average_volume_20d"])),
            "avg_frequency_20d": _safe_float(_first(raw, ["avg_frequency_20d", "average_frequency_20d", "frequency"])),
            "rvol": _safe_float(_first(raw, ["rvol", "volume_ratio", "value_ratio"])),
            "return_1d": _safe_float(_first(raw, ["return_1d"])),
            "return_3d": _safe_float(_first(raw, ["return_3d"])),
            "return_5d": _safe_float(_first(raw, ["return_5d"])),
            "return_20d": _safe_float(_first(raw, ["return_20d"])),
            "ma20": ma20,
            "ma50": ma50,
            "distance_ma20": distance_ma20,
            "distance_ma50": distance_ma50,
            "rsi": _safe_float(_first(raw, ["rsi", "rsi14"])),
            "atr_pct": _safe_float(_first(raw, ["atr_pct"])),
            "clv": _safe_float(_first(raw, ["clv", "close_location"])),
            "support_level": _safe_float(_first(raw, ["support_level", "low_20d"])),
            "resistance_level": _safe_float(_first(raw, ["resistance_level", "high_20d"])),
            "top_buyer": _first(raw, ["top_buyer", "top_buyer_1_code"]),
            "top_seller": _first(raw, ["top_seller", "top_seller_1_code"]),
            "top_buyer_avg_price": _safe_float(_first(raw, ["top_buyer_avg_price", "top_buyer_1_avg_price"])),
            "top_seller_avg_price": _safe_float(_first(raw, ["top_seller_avg_price", "top_seller_1_avg_price"])),
            "top3_buyer_dominance": _safe_float(_first(raw, ["top3_buyer_dominance", "top3_buyer_ratio"])),
            "top3_seller_dominance": _safe_float(_first(raw, ["top3_seller_dominance", "top3_seller_ratio"])),
            "hhi_buyer": _safe_float(_first(raw, ["hhi_buyer", "buyer_hhi"])),
            "hhi_seller": _safe_float(_first(raw, ["hhi_seller", "seller_hhi"])),
            "close_vs_top_buyer_avg_pct": _safe_float(_first(raw, ["close_vs_top_buyer_avg_pct", "close_vs_top_buyer_avg"])),
            "broker_activity_available": _safe_bool(_first(raw, ["broker_activity_available"], False)),
        }
    )
    for window in [1, 3, 5, 10, 20]:
        normalized[f"broker_net_buy_{window}d"] = _safe_float(
            _first(raw, [f"broker_net_buy_{window}d", f"broker_net_buy_{window}D", f"net_buy_{window}d"])
        )
    return normalized


def score_liquidity(row: dict[str, Any], config: HybridScreenerConfig) -> ScoreResult:
    cfg = config.liquidity
    warnings: list[str] = []
    avg_value = _safe_float(row.get("avg_value_20d"))
    avg_volume = _safe_float(row.get("avg_volume_20d"))
    # avg_frequency_20d is preferred; fall back to live frequency from orderbook
    avg_frequency = _safe_float(row.get("avg_frequency_20d"))
    if avg_frequency is None:
        avg_frequency = _safe_float(_first(row, ["frequency_live", "frequency"]))
    rvol = _safe_float(row.get("rvol"))
    score = 0.0
    score += _pct_score(avg_value, cfg.min_avg_value_20d, 40)
    score += _pct_score(avg_volume, cfg.min_avg_volume_20d, 20)
    if avg_frequency is None:
        # No frequency data available from any source — assign neutral partial score
        score += 10
    else:
        score += _pct_score(avg_frequency, cfg.min_avg_frequency_20d, 20)
    if rvol is None:
        warnings.append("rvol_missing")
        score += 5
    elif rvol >= cfg.good_rvol:
        score += 20
    elif rvol >= cfg.min_rvol:
        score += 12
    else:
        score += max(0, rvol / cfg.min_rvol) * 10
    if _safe_bool(row.get("tradable", True)):
        score += 5
    return ScoreResult(_clip(score), tuple(warnings))


def score_technical(row: dict[str, Any], config: HybridScreenerConfig) -> ScoreResult:
    cfg = config.technical
    warnings: list[str] = []
    close = _safe_float(row.get("close"))
    ma20 = _safe_float(row.get("ma20"))
    ma50 = _safe_float(row.get("ma50"))
    rsi = _safe_float(row.get("rsi"))
    atr_pct = _safe_float(row.get("atr_pct"))
    clv = _safe_float(row.get("clv"), 0.5)
    distance_ma20 = _safe_float(row.get("distance_ma20"))
    return_1d = _safe_float(row.get("return_1d"))
    return_3d = _safe_float(row.get("return_3d"))
    score = 35.0
    if close is None:
        return ScoreResult(0, ("close_missing",), ("DATA_INSUFFICIENT",))
    if ma20 is None:
        warnings.append("ma20_missing")
    elif close >= ma20:
        score += 12
    if ma20 is not None and ma50 is not None:
        if close >= ma50:
            score += 10
        if ma20 >= ma50:
            score += 10
    else:
        warnings.append("ma50_missing")
    if distance_ma20 is not None and cfg.ma20_distance_min <= distance_ma20 <= cfg.ma20_distance_max:
        score += 12
    if rsi is None:
        warnings.append("rsi_missing")
        score += 5
    elif cfg.rsi_ideal_min <= rsi <= cfg.rsi_ideal_max:
        score += 15
    elif cfg.rsi_min <= rsi < cfg.rsi_ideal_min or cfg.rsi_ideal_max < rsi <= cfg.rsi_overbought:
        score += 7
    if atr_pct is None:
        warnings.append("atr_pct_missing")
        score += 4
    elif 0.012 <= atr_pct <= 0.055:
        score += 10
    elif atr_pct > 0.08:
        score -= 15
    if clv is not None and clv >= cfg.clv_strong:
        score += 10
    elif clv is not None and clv >= cfg.clv_good:
        score += 6
    if return_1d is not None and return_1d > 0:
        score += 4
    if return_3d is not None and return_3d > 0:
        score += 2
    return ScoreResult(_clip(score), tuple(warnings))


def score_smart_money(row: dict[str, Any], config: HybridScreenerConfig) -> ScoreResult:
    cfg = config.smart_money
    warnings: list[str] = []
    flags: list[str] = []
    broker_score = _safe_float(_first(row, ["smart_money_score", "bandarmology_score", "weighted_bandarmology_score"]))
    broker_available = _safe_bool(row.get("broker_activity_available")) or broker_score is not None
    acc_count = _safe_float(row.get("accumulation_window_count"))
    dist_count = _safe_float(row.get("distribution_window_count"))
    if acc_count is None:
        acc_count = 0
        for window in cfg.accumulation_lookbacks:
            value = _safe_float(row.get(f"broker_net_buy_{window}d"))
            if value is not None and value > 0:
                acc_count += 1
    if dist_count is None:
        dist_count = 0
        for window in cfg.accumulation_lookbacks:
            value = _safe_float(row.get(f"broker_net_buy_{window}d"))
            if value is not None and value < 0:
                dist_count += 1
    if not broker_available and acc_count == 0 and dist_count == 0:
        return ScoreResult(50, ("broker_flow_missing_neutral_score",), ("NO_BROKER_FLOW",))
    score = broker_score if broker_score is not None else 50.0
    score += min(acc_count, 5) * 7
    score -= min(dist_count, 5) * 8
    buyer_dom = _safe_float(row.get("top3_buyer_dominance"))
    seller_dom = _safe_float(row.get("top3_seller_dominance"))
    hhi_buyer = _safe_float(row.get("hhi_buyer"))
    hhi_seller = _safe_float(row.get("hhi_seller"))
    if buyer_dom is not None:
        if buyer_dom >= cfg.top3_buyer_dominance_strong:
            score += 10
        elif buyer_dom >= cfg.top3_buyer_dominance_good:
            score += 6
    if seller_dom is not None and seller_dom >= 0.60:
        score -= 8
    close_vs_top_buyer = _safe_float(row.get("close_vs_top_buyer_avg_pct"))
    if close_vs_top_buyer is not None and close_vs_top_buyer > cfg.max_close_vs_top_buyer_avg_safe:
        score -= 8
        flags.append("CLOSE_FAR_ABOVE_TOP_BUYER_AVG")
    if dist_count >= cfg.strong_distribution_threshold:
        flags.append("STRONG_DISTRIBUTION")
    elif dist_count >= cfg.distribution_penalty_threshold:
        flags.append("DISTRIBUTION_WARNING")
    top_buyer = row.get("top_buyer")
    top_seller = row.get("top_seller")
    if (
        top_buyer
        and top_seller
        and top_buyer == top_seller
        and buyer_dom is not None
        and seller_dom is not None
        and buyer_dom >= cfg.top3_buyer_dominance_good
        and seller_dom >= 0.50
    ):
        flags.append("FAKE_ACCUMULATION_RISK")
        warnings.append("same_top_buyer_and_seller_concentration")
        score -= 12
    if hhi_buyer is not None and hhi_seller is not None and hhi_buyer > 0.45 and hhi_seller > 0.45:
        flags.append("CROSSING_OR_POCKET_RISK")
        warnings.append("buyer_and_seller_hhi_both_high")
        score -= 6
    return ScoreResult(_clip(score), tuple(warnings), tuple(flags))


def score_price_extension(row: dict[str, Any], config: HybridScreenerConfig) -> ScoreResult:
    cfg = config.price_extension
    warnings: list[str] = []
    flags: list[str] = []
    score = 100.0
    checks = [
        ("return_1d", cfg.max_return_1d_safe, 15),
        ("return_3d", cfg.max_return_3d_safe, 25),
        ("return_5d", cfg.max_return_5d_safe, 25),
    ]
    for column, threshold, penalty in checks:
        value = _safe_float(row.get(column))
        if value is not None and value > threshold:
            score -= penalty
            warnings.append(f"{column}_above_safe_threshold")
            if column in {"return_3d", "return_5d"}:
                flags.append("DANGER_CHASING")
    distance_ma20 = _safe_float(row.get("distance_ma20"))
    if distance_ma20 is not None:
        if distance_ma20 > cfg.danger_distance_ma20:
            score -= 35
            flags.append("DANGER_CHASING")
            warnings.append("distance_ma20_danger")
        elif distance_ma20 > cfg.max_distance_ma20_safe:
            score -= 15
            warnings.append("distance_ma20_above_safe_threshold")
    close_vs_top_buyer = _safe_float(row.get("close_vs_top_buyer_avg_pct"))
    if close_vs_top_buyer is not None and close_vs_top_buyer > cfg.max_distance_top_buyer_avg_safe:
        score -= 15
        warnings.append("close_far_above_top_buyer_average")
        flags.append("DANGER_CHASING")
    rvol = _safe_float(row.get("rvol"))
    return_20d = _safe_float(row.get("return_20d"))
    if rvol is not None and return_20d is not None and rvol >= 3 and return_20d > 0.25:
        score -= 15
        flags.append("LATE_VOLUME_SPIKE_AFTER_RALLY")
    return ScoreResult(_clip(score), tuple(warnings), tuple(dict.fromkeys(flags)))


def score_market_regime(row: dict[str, Any]) -> ScoreResult:
    score = _safe_float(_first(row, ["market_regime_score", "ihsg_score"]))
    if score is None:
        return ScoreResult(50, ("market_regime_unavailable_neutral_score",))
    flags: list[str] = []
    if str(row.get("market_regime", "")).upper() in {"RISK_OFF", "HARD_RISK_OFF"} or score < 30:
        flags.append("MARKET_RISK_OFF")
    return ScoreResult(_clip(score), flags=tuple(flags))


def score_sector_strength(row: dict[str, Any]) -> ScoreResult:
    score = _safe_float(_first(row, ["sector_strength_score", "sector_score"]))
    if score is None:
        return ScoreResult(50, ("sector_strength_unavailable_neutral_score",))
    flags: list[str] = []
    if str(row.get("sector_regime", "")).upper() in {"DOWNTREND", "HARD_DOWNTREND"} or score < 30:
        flags.append("SECTOR_DOWNTREND")
    return ScoreResult(_clip(score), flags=tuple(flags))


def orderbook_available(row: dict[str, Any]) -> bool:
    explicit = row.get("orderbook_available")
    if explicit is not None:
        return _safe_bool(explicit)
    return any(
        _safe_float(row.get(key)) is not None
        for key in ["best_bid", "best_offer", "spread_pct", "orderbook_score", "bid_volume_top5", "bid_depth_5"]
    )


def score_orderbook(row: dict[str, Any], config: HybridScreenerConfig, mode: str) -> ScoreResult:
    if not orderbook_available(row):
        return ScoreResult(0, ("orderbook_missing",), ("NO_ORDERBOOK",))
    cfg = config.orderbook
    warnings: list[str] = []
    flags: list[str] = []
    best_bid = _safe_float(row.get("best_bid"))
    best_offer = _safe_float(row.get("best_offer"))
    spread_pct = _safe_float(row.get("spread_pct"))
    spread_ticks = _safe_float(row.get("spread_ticks"))
    if spread_ticks is None and best_bid is not None and best_offer is not None and best_bid > 0:
        try:
            spread_ticks = (best_offer - best_bid) / get_idx_tick_size(best_bid)
        except ValueError:
            spread_ticks = None
    bid_depth = _safe_float(_first(row, ["bid_depth_5", "bid_volume_top5"]))
    offer_depth = _safe_float(_first(row, ["offer_depth_5", "offer_volume_top5"]))
    ratio = _safe_float(row.get("bid_offer_ratio_5"))
    if ratio is None and bid_depth is not None and offer_depth not in {None, 0}:
        ratio = bid_depth / offer_depth
    offer_wall = _safe_float(_first(row, ["offer_wall_ratio", "offer_wall_ratio_top5"]))
    frequency = _safe_float(_first(row, ["frequency_live", "frequency"]))
    value_live = _safe_float(_first(row, ["value_live", "value"]))
    score = _safe_float(row.get("orderbook_score"), 50) or 50
    if spread_pct is not None:
        if spread_pct <= cfg.max_spread_pct_bpjs:
            score += 12
        else:
            score -= 20
            warnings.append("spread_pct_too_wide")
            if mode == "bpjs_live":
                flags.append("ORDERBOOK_REJECT")
    if spread_ticks is not None and mode == "bpjs_live" and spread_ticks > cfg.max_spread_ticks_bpjs:
        flags.append("ORDERBOOK_REJECT")
        warnings.append("spread_ticks_too_wide_for_bpjs")
        score -= 25
    if ratio is not None:
        if cfg.ideal_bid_offer_ratio_min <= ratio <= cfg.ideal_bid_offer_ratio_max:
            score += 12
        elif ratio < cfg.min_bid_offer_ratio:
            score -= 20
            flags.append("ORDERBOOK_WEAK")
            warnings.append("bid_depth_weaker_than_offer")
        elif ratio >= cfg.fake_bid_ratio_warning:
            score -= 10
            flags.append("FAKE_BID_RISK")
            warnings.append("bid_offer_ratio_extreme")
    if offer_wall is not None and offer_wall >= cfg.offer_wall_ratio_warning:
        score -= 25
        flags.append("ORDERBOOK_REJECT")
        warnings.append("huge_offer_wall")
    if frequency is not None:
        if frequency < cfg.min_frequency_open_5m:
            score -= 12
            flags.append("LOW_FREQUENCY")
            warnings.append("live_frequency_below_threshold")
        else:
            score += 5
    if value_live is not None:
        if value_live < cfg.min_value_open_5m:
            score -= 8
            warnings.append("live_value_below_threshold")
        else:
            score += 5
    if not _safe_bool(row.get("tradable", True)):
        score = min(score, 20)
        flags.append("ORDERBOOK_REJECT")
        warnings.append("not_tradable")
    if _safe_bool(row.get("uma")):
        score = min(score, 20)
        flags.append("ORDERBOOK_REJECT")
        warnings.append("uma_flag")
    if is_notation_risky(row.get("notation")):
        score -= 15
        warnings.append("special_notation_risk")
    if is_corp_action_active(row.get("corp_action")):
        score -= 15
        warnings.append("corporate_action_risk")
    return ScoreResult(_clip(score), tuple(warnings), tuple(dict.fromkeys(flags)))


def build_risk_plan(row: dict[str, Any], config: HybridScreenerConfig, capital_profile: str, mode: str) -> RiskPlan:
    profile = config.capital_profiles[capital_profile]
    fees = config.fees
    warnings: list[str] = []
    skip_reasons: list[str] = []
    close = _safe_float(row.get("close"))
    best_offer = _safe_float(row.get("best_offer"))
    entry = best_offer if mode == "bpjs_live" and best_offer is not None else _safe_float(_first(row, ["entry_price", "lastprice"]), close)
    target_tp_pct = _safe_float(row.get("target_tp_pct"))
    if target_tp_pct is None or target_tp_pct <= 0:
        target_tp_pct = profile.target_tp_pct_default
    stop_loss_pct = _safe_float(row.get("stop_loss_pct"))
    if stop_loss_pct is None or stop_loss_pct <= 0:
        stop_loss_pct = profile.stop_loss_pct_default
    if entry is None or entry <= 0:
        return RiskPlan(None, None, None, None, target_tp_pct, stop_loss_pct, 0, 0, 0, 0, -1, 0, 0, 0, False, 0, 0, 0, 0, ("entry_price_missing",), ("DATA_INSUFFICIENT",))
    try:
        entry = float(entry)
        target_tp_pct = float(target_tp_pct)
        stop_loss_pct = float(stop_loss_pct)
        try:
            entry = round_price_to_tick(entry, "nearest")
            tp1 = round_price_to_tick(entry * (1 + target_tp_pct), "floor")
            tp2 = round_price_to_tick(entry * (1 + max(target_tp_pct * 1.5, target_tp_pct + 0.01)), "floor")
            stop_loss = round_price_to_tick(entry * (1 - stop_loss_pct), "floor")
        except ValueError:
            tp1 = entry * (1 + target_tp_pct)
            tp2 = entry * (1 + max(target_tp_pct * 1.5, target_tp_pct + 0.01))
            stop_loss = entry * (1 - stop_loss_pct)
        max_position_value = float(profile.capital) * float(profile.max_position_pct)
        lot_value = entry * float(config.risk.lot_size)
        lot = int(max_position_value // lot_value) if lot_value > 0 else 0
        affordable_lot = lot >= 1
        if not affordable_lot:
            skip_reasons.append("TOO_EXPENSIVE_FOR_CAPITAL")
        if entry > float(profile.max_stock_price):
            skip_reasons.append("TOO_EXPENSIVE_FOR_CAPITAL")
        position_value = lot * lot_value
        estimated_buy_fee = max(position_value * float(fees.buy_fee_pct), float(fees.minimum_buy_fee) if position_value else 0)
        estimated_sell_fee = max((lot * float(config.risk.lot_size) * float(tp1)) * float(fees.sell_fee_pct), float(fees.minimum_sell_fee) if position_value else 0)
        estimated_slippage = position_value * float(fees.slippage_pct_default) + (lot * float(config.risk.lot_size) * float(tp1) * float(fees.slippage_pct_default))
        gross_profit = max(0.0, (float(tp1) - entry) * lot * float(config.risk.lot_size))
        net_profit = gross_profit - estimated_buy_fee - estimated_sell_fee - estimated_slippage
        risk_amount = max(0.0, (entry - float(stop_loss)) * lot * float(config.risk.lot_size))
        reward_amount = gross_profit
        risk_reward_ratio = reward_amount / risk_amount if risk_amount > 0 else 0.0
        if target_tp_pct < float(profile.min_gross_tp_pct):
            skip_reasons.append("NET_PROFIT_NOT_WORTH_IT")
            warnings.append("target_tp_below_profile_min_gross_tp")
        if net_profit <= 0 or net_profit < float(config.risk.minimum_net_profit):
            skip_reasons.append("NET_PROFIT_NOT_WORTH_IT")
        if risk_reward_ratio < float(config.risk.minimum_risk_reward):
            skip_reasons.append("RISK_REWARD_BAD")
        if stop_loss_pct > target_tp_pct:
            warnings.append("stop_loss_pct_wider_than_target_tp")
        risk_score = 100.0
        if not affordable_lot:
            risk_score -= 50
        if "RISK_REWARD_BAD" in skip_reasons:
            risk_score -= 30
        if "NET_PROFIT_NOT_WORTH_IT" in skip_reasons:
            risk_score -= 25
        if entry > float(profile.preferred_price_max):
            risk_score -= 10
            warnings.append("price_above_preferred_profile_range")
        if entry < float(profile.preferred_price_min):
            warnings.append("price_below_preferred_profile_range")
        net_score = 100.0 if net_profit >= float(config.risk.minimum_net_profit) else max(0.0, 50.0 * max(net_profit, 0) / max(float(config.risk.minimum_net_profit), 1))
        return RiskPlan(
            entry,
            tp1,
            tp2,
            stop_loss,
            target_tp_pct,
            stop_loss_pct,
            estimated_buy_fee,
            estimated_sell_fee,
            estimated_slippage,
            gross_profit,
            net_profit,
            risk_amount,
            reward_amount,
            risk_reward_ratio,
            affordable_lot,
            position_value,
            lot,
            _clip(risk_score),
            _clip(net_score),
            tuple(warnings),
            tuple(dict.fromkeys(skip_reasons)),
        )
    except Exception as e:
        print(f"Warning: build_risk_plan error for entry={entry}: {e}")
        return RiskPlan(None, None, None, None, target_tp_pct, stop_loss_pct, 0, 0, 0, 0, -1, 0, 0, 0, False, 0, 0, 0, 0, (f"risk_calc_error:{e}",), ("DATA_INSUFFICIENT",))


def stage0_safety(row: dict[str, Any], scores: dict[str, ScoreResult], risk: RiskPlan, config: HybridScreenerConfig) -> tuple[list[str], list[str]]:
    cfg = config.safety
    skip_reasons: list[str] = []
    warnings: list[str] = []
    avg_value = _safe_float(row.get("avg_value_20d"))
    avg_frequency = _safe_float(row.get("avg_frequency_20d"))
    if avg_frequency is None:
        avg_frequency = _safe_float(_first(row, ["frequency_live", "frequency"]))
    if cfg.hard_skip_fca and (
        _safe_bool(row.get("fca"))
        or _safe_bool(row.get("full_call_auction"))
        or "pemantauan" in str(row.get("board", row.get("papan", ""))).lower()
    ):
        skip_reasons.append("SKIP_FCA_OR_SPECIAL_BOARD")
    if cfg.hard_skip_uma and _safe_bool(row.get("uma")):
        skip_reasons.append("SKIP_UMA")
    status_text = str(row.get("status", "")).lower()
    if _safe_bool(row.get("suspended")) or "suspend" in status_text or not _safe_bool(row.get("tradable", True)):
        skip_reasons.append("SKIP_NOT_TRADABLE")
    if cfg.hard_skip_special_notation and is_notation_risky(row.get("notation")):
        skip_reasons.append("SKIP_SPECIAL_NOTATION")
    if avg_value is None:
        warnings.append("avg_value_20d_missing")
    elif avg_value < config.liquidity.min_avg_value_20d:
        skip_reasons.append("LOW_LIQUIDITY")
    if avg_frequency is not None and avg_frequency < config.liquidity.min_avg_frequency_20d:
        skip_reasons.append("LOW_LIQUIDITY")
    if cfg.hard_skip_corporate_action and is_corp_action_active(row.get("corp_action")):
        skip_reasons.append("SKIP_CORPORATE_ACTION")
    if "DANGER_CHASING" in scores["price_extension"].flags:
        skip_reasons.append("DANGER_CHASING")
    if "STRONG_DISTRIBUTION" in scores["smart_money"].flags:
        skip_reasons.append("DISTRIBUTION_WARNING")
    if cfg.hard_market_regime_risk_off and "MARKET_RISK_OFF" in scores["market_regime"].flags:
        skip_reasons.append("SKIP_MARKET_RISK_OFF")
    if cfg.hard_sector_downtrend and "SECTOR_DOWNTREND" in scores["sector_strength"].flags:
        skip_reasons.append("SKIP_SECTOR_DOWNTREND")
    skip_reasons.extend(risk.skip_reasons)
    return list(dict.fromkeys(skip_reasons)), list(dict.fromkeys(warnings))


def _combined_market_sector(market_score: float, sector_score: float) -> float:
    return (market_score + sector_score) / 2


def calculate_final_score(scores: dict[str, ScoreResult], risk: RiskPlan, mode: str, config: HybridScreenerConfig) -> float:
    weights = config.weights.get(mode if mode != "hybrid_dual_flow" else "hybrid_dual_flow", config.weights["normal_execution"])
    components = {
        "liquidity_score": float(scores["liquidity"].score),
        "technical_score": float(scores["technical"].score),
        "smart_money_score": float(scores["smart_money"].score),
        "price_extension_score": float(scores["price_extension"].score),
        "orderbook_score": float(scores["orderbook"].score),
        "risk_plan_score": float(risk.risk_plan_score),
        "net_profit_feasibility_score": float(risk.net_profit_feasibility_score),
        "market_sector_score": _combined_market_sector(float(scores["market_regime"].score), float(scores["sector_strength"].score)),
    }
    weight_total = sum(weights.values())
    if weight_total <= 0:
        return 0.0
    try:
        return round(sum(float(components.get(name, 0)) * float(weight) for name, weight in weights.items()) / weight_total, 2)
    except (TypeError, ValueError) as e:
        print(f"Warning: calculate_final_score error: {e}")
        return 0.0


def determine_flow_source(scores: dict[str, ScoreResult], risk: RiskPlan) -> str:
    safe = (
        scores["liquidity"].score >= 60
        and scores["technical"].score >= 60
        and scores["price_extension"].score >= 60
        and risk.risk_plan_score >= 55
    )
    smart = (
        scores["smart_money"].score >= 60
        and scores["liquidity"].score >= 45
        and scores["price_extension"].score >= 60
        and "STRONG_DISTRIBUTION" not in scores["smart_money"].flags
    )
    if safe and smart:
        return "both"
    if safe:
        return "safe_execution"
    if smart:
        return "smart_money_discovery"
    return "none"


def determine_status(
    row: dict[str, Any],
    scores: dict[str, ScoreResult],
    risk: RiskPlan,
    skip_reasons: list[str],
    flow_source: str,
    mode: str,
) -> str:
    if not row.get("symbol"):
        return "DATA_INSUFFICIENT"
    if "LOW_LIQUIDITY" in skip_reasons:
        return "LOW_LIQUIDITY"
    if "TOO_EXPENSIVE_FOR_CAPITAL" in skip_reasons:
        return "TOO_EXPENSIVE_FOR_CAPITAL"
    if "DANGER_CHASING" in skip_reasons:
        return "DANGER_CHASING"
    if "DISTRIBUTION_WARNING" in skip_reasons:
        return "DISTRIBUTION_WARNING"
    hard_safety = [reason for reason in skip_reasons if reason.startswith("SKIP_")]
    if hard_safety:
        return "SKIP"
    has_orderbook = orderbook_available(row)
    orderbook_flags = set(scores["orderbook"].flags)
    risk_flags = set(risk.skip_reasons)
    if mode == "smart_money_first":
        if scores["smart_money"].score >= 70 and scores["price_extension"].score >= 70 and scores["technical"].score >= 55:
            return "READY_SOON"
        if scores["smart_money"].score >= 60 and scores["price_extension"].score >= 65:
            return "EARLY_WATCH"
        return "SKIP"
    if mode == "weekend_preparation":
        if scores["smart_money"].score >= 70 and scores["technical"].score >= 60 and risk.risk_plan_score >= 55:
            return "READY_SOON"
        if scores["smart_money"].score >= 60 or flow_source in {"safe_execution", "smart_money_discovery", "both"}:
            return "EARLY_WATCH"
        return "SKIP"
    if flow_source == "none":
        return "SKIP"
    if "NET_PROFIT_NOT_WORTH_IT" in risk_flags:
        return "NET_PROFIT_NOT_WORTH_IT"
    if "RISK_REWARD_BAD" in risk_flags:
        return "RISK_REWARD_BAD"
    if mode == "bpjs_live":
        if not has_orderbook:
            return "NEED_ORDERBOOK"
        if "ORDERBOOK_REJECT" in orderbook_flags:
            return "ORDERBOOK_REJECT"
        if "ORDERBOOK_WEAK" in orderbook_flags or scores["orderbook"].score < 55:
            return "ORDERBOOK_WEAK"
        return "EXECUTION_READY"
    if has_orderbook:
        if "ORDERBOOK_REJECT" in orderbook_flags:
            return "ORDERBOOK_REJECT"
        if "ORDERBOOK_WEAK" in orderbook_flags or scores["orderbook"].score < 45:
            return "ORDERBOOK_WEAK"
        return "EXECUTION_READY"
    if mode == "normal_execution":
        return "EXECUTION_DRAFT"
    return "EXECUTION_CANDIDATE"


def build_explanation(status: str, scores: dict[str, ScoreResult], risk: RiskPlan, flow_source: str, warnings: list[str], skip_reasons: list[str]) -> str:
    if status == "READY_SOON":
        return "READY_SOON because smart money and technical structure are improving, price is not extended, but execution still needs live validation."
    if status == "EARLY_WATCH":
        return "EARLY_WATCH because the stock is worth monitoring, but the setup is not yet an execution signal."
    if status == "NEED_ORDERBOOK":
        return "NEED_ORDERBOOK because BPJS live mode requires a live orderbook before any execution-ready status is allowed."
    if status == "EXECUTION_DRAFT":
        return "EXECUTION_DRAFT because pre-market scores are acceptable, but live orderbook validation has not been supplied."
    if status == "EXECUTION_CANDIDATE":
        return "EXECUTION_CANDIDATE because liquidity, setup, smart money, extension, and risk gates are acceptable before final live validation."
    if status == "EXECUTION_READY":
        return "EXECUTION_READY because the hybrid candidate passed scoring, risk, net-profit, and live orderbook gates. This is not an order instruction."
    if status == "DANGER_CHASING":
        return "DANGER_CHASING because price extension is above configured safety thresholds."
    if status == "DISTRIBUTION_WARNING":
        return "DISTRIBUTION_WARNING because broker-flow distribution risk is too strong for a clean watchlist candidate."
    if status == "ORDERBOOK_REJECT":
        return "ORDERBOOK_REJECT because spread, offer wall, tradability, or other orderbook safety gates failed."
    if status == "ORDERBOOK_WEAK":
        return "ORDERBOOK_WEAK because live depth, spread, or frequency is not supportive enough for micro execution."
    if status == "NET_PROFIT_NOT_WORTH_IT":
        return "NET_PROFIT_NOT_WORTH_IT because expected TP is too small after estimated fees and slippage."
    if status == "RISK_REWARD_BAD":
        return "RISK_REWARD_BAD because the configured stop and target do not meet minimum R:R."
    if status == "TOO_EXPENSIVE_FOR_CAPITAL":
        return "TOO_EXPENSIVE_FOR_CAPITAL because one lot or the stock price exceeds the selected capital profile."
    if status == "LOW_LIQUIDITY":
        return "LOW_LIQUIDITY because average value or frequency is below configured execution thresholds."
    if status == "DATA_INSUFFICIENT":
        return "DATA_INSUFFICIENT because required symbol or price data is missing."
    reason_text = ", ".join(skip_reasons[:3]) if skip_reasons else "scores did not meet the watchlist gates"
    warning_text = f" Warnings: {', '.join(warnings[:4])}." if warnings else ""
    return f"SKIP because {reason_text}.{warning_text}"


def build_output_row(row: dict[str, Any], mode: str, capital_profile: str, config: HybridScreenerConfig) -> dict[str, Any]:
    normalized = normalize_candidate_row(row)
    scores = {
        "liquidity": score_liquidity(normalized, config),
        "technical": score_technical(normalized, config),
        "smart_money": score_smart_money(normalized, config),
        "price_extension": score_price_extension(normalized, config),
        "market_regime": score_market_regime(normalized),
        "sector_strength": score_sector_strength(normalized),
        "orderbook": score_orderbook(normalized, config, mode),
    }
    risk = build_risk_plan(normalized, config, capital_profile, mode)
    flow_source = determine_flow_source(scores, risk)
    safety_skip, safety_warnings = stage0_safety(normalized, scores, risk, config)
    warnings = list(dict.fromkeys([*safety_warnings, *risk.warnings, *[warning for score in scores.values() for warning in score.warnings]]))
    skip_reasons = list(dict.fromkeys([*safety_skip, *risk.skip_reasons]))
    status = determine_status(normalized, scores, risk, skip_reasons, flow_source, mode)
    final_score = calculate_final_score(scores, risk, mode, config)
    best_bid = _safe_float(normalized.get("best_bid"))
    best_offer = _safe_float(normalized.get("best_offer"))
    spread_ticks = _safe_float(normalized.get("spread_ticks"))
    if spread_ticks is None and best_bid is not None and best_offer is not None and best_bid > 0:
        try:
            spread_ticks = (best_offer - best_bid) / get_idx_tick_size(best_bid)
        except ValueError:
            spread_ticks = None
    bid_depth = _safe_float(_first(normalized, ["bid_depth_5", "bid_volume_top5"]))
    offer_depth = _safe_float(_first(normalized, ["offer_depth_5", "offer_volume_top5"]))
    ratio = _safe_float(normalized.get("bid_offer_ratio_5"))
    if ratio is None and bid_depth is not None and offer_depth not in {None, 0}:
        ratio = bid_depth / offer_depth
    output = {
        "symbol": normalized.get("symbol"),
        "name": normalized.get("name"),
        "date": normalized.get("date"),
        "mode": mode,
        "final_status": status,
        "final_score": final_score,
        "rank": None,
        "flow_source": flow_source,
        "liquidity_score": round(float(scores["liquidity"].score), 2),
        "technical_score": round(float(scores["technical"].score), 2),
        "smart_money_score": round(float(scores["smart_money"].score), 2),
        "price_extension_score": round(float(scores["price_extension"].score), 2),
        "market_regime_score": round(float(scores["market_regime"].score), 2),
        "sector_strength_score": round(float(scores["sector_strength"].score), 2),
        "orderbook_score": round(float(scores["orderbook"].score), 2),
        "risk_plan_score": round(float(risk.risk_plan_score), 2),
        "net_profit_feasibility_score": round(float(risk.net_profit_feasibility_score), 2),
        "avg_value_20d": normalized.get("avg_value_20d"),
        "avg_frequency_20d": normalized.get("avg_frequency_20d"),
        "rvol": normalized.get("rvol"),
        "return_1d": normalized.get("return_1d"),
        "return_3d": normalized.get("return_3d"),
        "return_5d": normalized.get("return_5d"),
        "return_20d": normalized.get("return_20d"),
        "ma20": normalized.get("ma20"),
        "ma50": normalized.get("ma50"),
        "distance_ma20": normalized.get("distance_ma20"),
        "distance_ma50": normalized.get("distance_ma50"),
        "rsi": normalized.get("rsi"),
        "atr_pct": normalized.get("atr_pct"),
        "clv": normalized.get("clv"),
        "support_level": normalized.get("support_level"),
        "resistance_level": normalized.get("resistance_level"),
        "accumulation_window_count": _safe_float(normalized.get("accumulation_window_count")),
        "distribution_window_count": _safe_float(normalized.get("distribution_window_count")),
        "top_buyer": normalized.get("top_buyer"),
        "top_buyer_avg_price": normalized.get("top_buyer_avg_price"),
        "top3_buyer_dominance": normalized.get("top3_buyer_dominance"),
        "top_seller": normalized.get("top_seller"),
        "top_seller_avg_price": normalized.get("top_seller_avg_price"),
        "top3_seller_dominance": normalized.get("top3_seller_dominance"),
        "hhi_buyer": normalized.get("hhi_buyer"),
        "hhi_seller": normalized.get("hhi_seller"),
        "close_vs_top_buyer_avg_pct": normalized.get("close_vs_top_buyer_avg_pct"),
        "spread_ticks": spread_ticks,
        "spread_pct": _safe_float(normalized.get("spread_pct")),
        "best_bid": best_bid,
        "best_offer": best_offer,
        "bid_depth_5": bid_depth,
        "offer_depth_5": offer_depth,
        "bid_offer_ratio_5": ratio,
        "offer_wall_ratio": _safe_float(_first(normalized, ["offer_wall_ratio", "offer_wall_ratio_top5"])),
        "frequency_live": _safe_float(_first(normalized, ["frequency_live", "frequency"])),
        "value_live": _safe_float(_first(normalized, ["value_live", "value"])),
        "entry_price": risk.entry_price,
        "tp1_price": risk.tp1_price,
        "tp2_price": risk.tp2_price,
        "stop_loss_price": risk.stop_loss_price,
        "target_tp_pct": risk.target_tp_pct,
        "stop_loss_pct": risk.stop_loss_pct,
        "estimated_buy_fee": risk.estimated_buy_fee,
        "estimated_sell_fee": risk.estimated_sell_fee,
        "estimated_slippage": risk.estimated_slippage,
        "gross_profit": risk.gross_profit,
        "net_profit_after_fee": risk.net_profit_after_fee,
        "risk_amount": risk.risk_amount,
        "reward_amount": risk.reward_amount,
        "risk_reward_ratio": risk.risk_reward_ratio,
        "affordable_lot": risk.affordable_lot,
        "position_value": risk.position_value,
        "capital_profile": capital_profile,
        "warnings": ";".join(warnings),
        "skip_reasons": ";".join(skip_reasons),
        "explanation": build_explanation(status, scores, risk, flow_source, warnings, skip_reasons),
    }
    for window in [1, 3, 5, 10, 20]:
        output[f"broker_net_buy_{window}d"] = normalized.get(f"broker_net_buy_{window}d")
    return output


def build_hybrid_watchlist(
    candidates: pd.DataFrame,
    mode: str = "normal_execution",
    capital_profile: str = "capital_1m",
    config: HybridScreenerConfig | None = None,
    date: str | None = None,
    max_candidates: int | None = None,
) -> pd.DataFrame:
    config = config or HybridScreenerConfig()
    if mode not in HYBRID_MODES:
        raise ValueError(f"Unsupported hybrid screener mode: {mode}")
    if capital_profile not in config.capital_profiles:
        raise ValueError(f"Unknown capital profile: {capital_profile}")
    rows = []
    for _, row in candidates.iterrows():
        try:
            output = build_output_row(row, mode, capital_profile, config)
            if date:
                output["date"] = date
            rows.append(output)
        except Exception as e:
            ticker = row.get("ticker", row.get("symbol", "unknown"))
            print(f"Warning: Skipping ticker {ticker} in hybrid watchlist due to error: {e}")
            continue
    output_df = pd.DataFrame(rows)
    for column in OUTPUT_COLUMNS:
        if column not in output_df.columns:
            output_df[column] = None
    status_rank = {
        "EXECUTION_READY": 0,
        "EXECUTION_CANDIDATE": 1,
        "EXECUTION_DRAFT": 2,
        "READY_SOON": 3,
        "EARLY_WATCH": 4,
        "NEED_ORDERBOOK": 5,
        "ORDERBOOK_WEAK": 6,
        "ORDERBOOK_REJECT": 7,
        "NET_PROFIT_NOT_WORTH_IT": 8,
        "RISK_REWARD_BAD": 9,
        "DANGER_CHASING": 10,
        "DISTRIBUTION_WARNING": 11,
        "LOW_LIQUIDITY": 12,
        "TOO_EXPENSIVE_FOR_CAPITAL": 13,
        "DATA_INSUFFICIENT": 14,
        "SKIP": 15,
    }
    output_df["_status_rank"] = output_df["final_status"].map(status_rank).fillna(99)
    output_df = output_df.sort_values(["_status_rank", "final_score"], ascending=[True, False], na_position="last")
    output_df["rank"] = range(1, len(output_df) + 1)
    if max_candidates is None:
        max_candidates = config.watchlist.max_candidates_bpjs if mode == "bpjs_live" else config.watchlist.max_candidates_default
    limited = output_df.head(max_candidates).copy() if max_candidates and max_candidates > 0 else output_df
    return limited[OUTPUT_COLUMNS]


def merge_candidate_sources(
    input_path: str | Path,
    broker_flow_path: str | Path | None = None,
    orderbook_path: str | Path | None = None,
) -> pd.DataFrame:
    try:
        candidates = pd.read_csv(input_path)
        if candidates.empty:
            raise ValueError("Tidak ada emiten yang lolos screening Stage 2 (Technical). Watchlist kosong.")
    except (pd.errors.EmptyDataError, ValueError):
        raise ValueError("Tidak ada emiten yang lolos screening Stage 2 (Technical). Watchlist kosong.")
        
    if broker_flow_path:
        try:
            broker = pd.read_csv(broker_flow_path)
        except pd.errors.EmptyDataError:
            print("Warning: Broker flow CSV is empty.")
            broker = pd.DataFrame(columns=["ticker", "bandarmology_score", "bandarmology_signal", "broker_activity_available"])
            
        key = "ticker" if "ticker" in candidates.columns and "ticker" in broker.columns else "symbol"
        candidates = candidates.merge(broker, on=key, how="left", suffixes=("", "_broker"))
        
    if orderbook_path:
        try:
            orderbook = pd.read_csv(orderbook_path)
        except pd.errors.EmptyDataError:
            print("Warning: Orderbook CSV is empty.")
            orderbook = pd.DataFrame(columns=["ticker", "orderbook_status", "orderbook_score"])
            
        key = "ticker" if "ticker" in candidates.columns and "ticker" in orderbook.columns else "symbol"
        candidates = candidates.merge(orderbook, on=key, how="left", suffixes=("", "_orderbook"))
        
    return candidates


def run_hybrid_screener(
    input_path: str | Path,
    output_path: str | Path,
    mode: str = "normal_execution",
    capital_profile: str = "capital_1m",
    config_path: str | Path | None = None,
    broker_flow_path: str | Path | None = None,
    orderbook_path: str | Path | None = None,
    date: str | None = None,
    max_candidates: int | None = None,
) -> pd.DataFrame:
    config = load_hybrid_config(config_path)
    candidates = merge_candidate_sources(input_path, broker_flow_path, orderbook_path)
    watchlist = build_hybrid_watchlist(candidates, mode, capital_profile, config, date, max_candidates)
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    watchlist.to_csv(path, index=False)
    return watchlist


def explain_candidate(watchlist_path: str | Path, symbol: str, date: str | None = None) -> str:
    watchlist = pd.read_csv(watchlist_path)
    symbol_column = "symbol" if "symbol" in watchlist.columns else "ticker"
    mask = watchlist[symbol_column].astype(str).str.replace(".JK", "", regex=False).str.upper() == symbol.replace(".JK", "").upper()
    if date and "date" in watchlist.columns:
        mask &= watchlist["date"].astype(str) == str(date)
    matches = watchlist[mask]
    if matches.empty:
        raise ValueError(f"No candidate found for {symbol}")
    row = matches.iloc[0]
    return str(row.get("explanation", "No explanation available."))
