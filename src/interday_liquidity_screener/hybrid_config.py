from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from pathlib import Path
from typing import Any
import json

from .enhancements import (
    AdaptiveTPConfig,
    BlackoutConfig,
    BrokerWindowConfig,
    LiquiditySizerConfig,
    MarketRegimeConfig,
    MultiBarConfig,
)
from .market_data_cache import DEFAULT_MARKET_DATA_DB


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
    risk_per_trade_pct: float = 0.005


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
    market_regime: MarketRegimeConfig = field(default_factory=MarketRegimeConfig)
    multibar_confirm: MultiBarConfig = field(default_factory=MultiBarConfig)
    multibar_enabled_for_swing: bool = True
    multibar_enabled_for_bpjs: bool = False
    blackout: BlackoutConfig = field(default_factory=BlackoutConfig)
    adaptive_tp: AdaptiveTPConfig = field(default_factory=AdaptiveTPConfig)
    liquidity_sizer: LiquiditySizerConfig = field(default_factory=LiquiditySizerConfig)
    broker_window: BrokerWindowConfig = field(default_factory=BrokerWindowConfig)
    market_data_db: Path = DEFAULT_MARKET_DATA_DB
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
    for name in annotations:
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
        market_regime=_dataclass_from_dict(MarketRegimeConfig, merged.get("market_regime", {})),
        multibar_confirm=_dataclass_from_dict(MultiBarConfig, merged.get("multibar_confirm", {})),
        multibar_enabled_for_swing=bool(merged.get("multibar_enabled_for_swing", True)),
        multibar_enabled_for_bpjs=bool(merged.get("multibar_enabled_for_bpjs", False)),
        blackout=_dataclass_from_dict(BlackoutConfig, merged.get("blackout", {})),
        adaptive_tp=_dataclass_from_dict(AdaptiveTPConfig, merged.get("adaptive_tp", {})),
        liquidity_sizer=_dataclass_from_dict(LiquiditySizerConfig, merged.get("liquidity_sizer", {})),
        broker_window=_dataclass_from_dict(BrokerWindowConfig, merged.get("broker_window", {})),
        market_data_db=Path(merged.get("market_data_db", DEFAULT_MARKET_DATA_DB)),
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
