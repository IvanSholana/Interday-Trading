from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
from typing import Any

import pandas as pd

from .bpjs_config import DEFAULT_BPJS_PROFILE

ACTIONABLE_SETUPS = {
    "WATCH_ENTRY",
    "BREAKOUT_CANDIDATE",
    "PULLBACK_CANDIDATE",
    "REBOUND_CANDIDATE",
}

ACTIVE_TECHNICAL_CONTEXTS = {
    "BREAKOUT_NEAR",
    "REBOUND_NEAR_LOW",
    "PULLBACK_TO_MA",
    "UPTREND_CONTINUATION",
    "VOLUME_SPIKE",
    "EARLY_REVERSAL_ATTEMPT",
    "SIDEWAYS_COMPRESSION",
    "TOO_QUIET_ABSOLUTE",
}

_FUNNEL_COUNTS: dict[str, int] = {}

def reset_funnel_counts() -> None:
    global _FUNNEL_COUNTS
    _FUNNEL_COUNTS = {
        "total_inputs": 0,
        "pre_gate_is_data_valid_fail": 0,
        "pre_gate_is_bandar_path": 0,
        # Bandar path
        "bandar_liquidity_bucket_fail": 0,
        "bandar_watch_eligible_fail": 0,
        "bandar_technical_context_invalid_fail": 0,
        "bandar_technical_context_too_volatile_fail": 0,
        "bandar_technical_context_too_quiet_fail": 0,
        "bandar_broker_data_unavailable_fail": 0,
        "bandar_distribution_fail": 0,
        "bandar_short_term_against_medium_watch": 0,
        "bandar_pullback_with_medium_acc_watch": 0,
        "bandar_neutral_flow_fail": 0,
        "bandar_low_score_fail": 0,
        "bandar_no_accumulation_fail": 0,
        "bandar_position_too_small_fail": 0,
        "bandar_weak_but_liquid_watch": 0,
        "bandar_inactive_technical_context_fail": 0,
        "bandar_orderbook_status_fail": 0,
        "bandar_pre_gate_pass": 0,
        # Non-Bandar path
        "non_bandar_entry_setup_fail": 0,
        "non_bandar_watch_eligible_fail": 0,
        "non_bandar_technical_context_fail": 0,
        "non_bandar_position_too_small_fail": 0,
        "non_bandar_pre_gate_pass": 0,
        # Trade status gate
        "trade_gate_inputs": 0,
        "trade_gate_atr_pct_fail": 0,
        "trade_gate_invalid_stop_fail": 0,
        "trade_gate_stop_too_wide_fail": 0,
        "trade_gate_non_bandar_volume_fail": 0,
        "trade_gate_non_bandar_rebound_fail": 0,
        "trade_gate_non_bandar_activity_fail": 0,
        "trade_gate_non_bandar_pullback_fail": 0,
        "trade_gate_bad_rr_tp1_fail": 0,
        "trade_gate_bad_rr_tp2_fail": 0,
        "trade_gate_position_size_lots_fail": 0,
        "trade_gate_pending_orderbook_draft": 0,
        "trade_gate_pass_valid_plan": 0,
    }

def _inc_funnel(key: str) -> None:
    global _FUNNEL_COUNTS
    if key not in _FUNNEL_COUNTS:
        _FUNNEL_COUNTS[key] = 0
    _FUNNEL_COUNTS[key] += 1

def print_funnel_summary_report() -> None:
    global _FUNNEL_COUNTS
    if not _FUNNEL_COUNTS or _FUNNEL_COUNTS.get("total_inputs", 0) == 0:
        return

    print("=" * 60)
    print("STAGE 4 FUNNEL REJECTION ANALYSIS REPORT")
    print("=" * 60)
    total = _FUNNEL_COUNTS["total_inputs"]
    print(f"Total Tickers Input: {total}")
    print(f"  - Invalid Data (Stage 2): {_FUNNEL_COUNTS.get('pre_gate_is_data_valid_fail', 0)}")
    
    # Bandar Path
    bandar_total = _FUNNEL_COUNTS.get("pre_gate_is_bandar_path", 0)
    print(f"\nBandar Path: {bandar_total} tickers")
    if bandar_total > 0:
        rem = bandar_total
        print(f"  [Start] {rem} tickers")
        
        rem -= _FUNNEL_COUNTS.get("bandar_liquidity_bucket_fail", 0)
        print(f"  -> Liquidity Bucket (HIGH/GOOD): {rem} (filtered {_FUNNEL_COUNTS.get('bandar_liquidity_bucket_fail', 0)})")
        
        rem -= _FUNNEL_COUNTS.get("bandar_watch_eligible_fail", 0)
        print(f"  -> Bandar Watch Eligible: {rem} (filtered {_FUNNEL_COUNTS.get('bandar_watch_eligible_fail', 0)})")
        
        rem -= _FUNNEL_COUNTS.get("bandar_technical_context_invalid_fail", 0)
        print(f"  -> Technical Context Valid: {rem} (filtered {_FUNNEL_COUNTS.get('bandar_technical_context_invalid_fail', 0)})")
        
        rem -= _FUNNEL_COUNTS.get("bandar_technical_context_too_volatile_fail", 0)
        print(f"  -> Technical Volatility <= Limit: {rem} (filtered {_FUNNEL_COUNTS.get('bandar_technical_context_too_volatile_fail', 0)})")
        
        rem -= _FUNNEL_COUNTS.get("bandar_technical_context_too_quiet_fail", 0)
        print(f"  -> Technical Activity Not Too Quiet: {rem} (filtered {_FUNNEL_COUNTS.get('bandar_technical_context_too_quiet_fail', 0)})")
        
        rem -= _FUNNEL_COUNTS.get("bandar_broker_data_unavailable_fail", 0)
        print(f"  -> Broker Data Available: {rem} (filtered {_FUNNEL_COUNTS.get('bandar_broker_data_unavailable_fail', 0)})")
        
        rem -= _FUNNEL_COUNTS.get("bandar_distribution_fail", 0)
        print(f"  -> Not Distribution (STRONG/MILD): {rem} (filtered {_FUNNEL_COUNTS.get('bandar_distribution_fail', 0)})")
        
        rem -= _FUNNEL_COUNTS.get("bandar_short_term_against_medium_watch", 0)
        print(f"  -> Short term vs Medium distribution watch: {rem} (filtered {_FUNNEL_COUNTS.get('bandar_short_term_against_medium_watch', 0)})")
        
        rem -= _FUNNEL_COUNTS.get("bandar_pullback_with_medium_acc_watch", 0)
        print(f"  -> Pullback with medium accumulation watch: {rem} (filtered {_FUNNEL_COUNTS.get('bandar_pullback_with_medium_acc_watch', 0)})")
        
        rem -= _FUNNEL_COUNTS.get("bandar_neutral_flow_fail", 0)
        print(f"  -> Not Neutral Flow: {rem} (filtered {_FUNNEL_COUNTS.get('bandar_neutral_flow_fail', 0)})")
        
        rem -= _FUNNEL_COUNTS.get("bandar_low_score_fail", 0)
        print(f"  -> Score >= Min Score: {rem} (filtered {_FUNNEL_COUNTS.get('bandar_low_score_fail', 0)})")
        
        rem -= _FUNNEL_COUNTS.get("bandar_no_accumulation_fail", 0)
        print(f"  -> Accumulation confirmed: {rem} (filtered {_FUNNEL_COUNTS.get('bandar_no_accumulation_fail', 0)})")
        
        rem -= _FUNNEL_COUNTS.get("bandar_position_too_small_fail", 0)
        print(f"  -> Affordable minimum lot: {rem} (filtered {_FUNNEL_COUNTS.get('bandar_position_too_small_fail', 0)})")
        
        rem -= _FUNNEL_COUNTS.get("bandar_weak_but_liquid_watch", 0)
        print(f"  -> Bandar Accumulation (Weak Technical): {rem} (filtered {_FUNNEL_COUNTS.get('bandar_weak_but_liquid_watch', 0)})")
        
        rem -= _FUNNEL_COUNTS.get("bandar_inactive_technical_context_fail", 0)
        print(f"  -> Whitelisted active tech context: {rem} (filtered {_FUNNEL_COUNTS.get('bandar_inactive_technical_context_fail', 0)})")
        
        rem -= _FUNNEL_COUNTS.get("bandar_orderbook_status_fail", 0)
        print(f"  -> Orderbook confirmation check: {rem} (filtered {_FUNNEL_COUNTS.get('bandar_orderbook_status_fail', 0)})")
        
        print(f"  -> Passed Pre-gate: {_FUNNEL_COUNTS.get('bandar_pre_gate_pass', 0)}")

    # Non-Bandar Path
    non_bandar_total = total - _FUNNEL_COUNTS.get("pre_gate_is_data_valid_fail", 0) - bandar_total
    print(f"\nNon-Bandar Path: {non_bandar_total} tickers")
    if non_bandar_total > 0:
        rem = non_bandar_total
        print(f"  [Start] {rem} tickers")
        
        rem -= _FUNNEL_COUNTS.get("non_bandar_entry_setup_fail", 0)
        print(f"  -> Actionable entry setup: {rem} (filtered {_FUNNEL_COUNTS.get('non_bandar_entry_setup_fail', 0)})")
        
        rem -= _FUNNEL_COUNTS.get("non_bandar_watch_eligible_fail", 0)
        print(f"  -> Watch Eligible: {rem} (filtered {_FUNNEL_COUNTS.get('non_bandar_watch_eligible_fail', 0)})")
        
        rem -= _FUNNEL_COUNTS.get("non_bandar_technical_context_fail", 0)
        print(f"  -> Technical Context Valid: {rem} (filtered {_FUNNEL_COUNTS.get('non_bandar_technical_context_fail', 0)})")
        
        rem -= _FUNNEL_COUNTS.get("non_bandar_position_too_small_fail", 0)
        print(f"  -> Affordable minimum lot: {rem} (filtered {_FUNNEL_COUNTS.get('non_bandar_position_too_small_fail', 0)})")
        
        print(f"  -> Passed Pre-gate: {_FUNNEL_COUNTS.get('non_bandar_pre_gate_pass', 0)}")

    # Trade Status Gate
    trade_inputs = _FUNNEL_COUNTS.get("trade_gate_inputs", 0)
    print(f"\nTrade Status Evaluation: {trade_inputs} tickers entered")
    if trade_inputs > 0:
        rem = trade_inputs
        print(f"  [Start] {rem} tickers")
        
        rem -= _FUNNEL_COUNTS.get("trade_gate_atr_pct_fail", 0)
        print(f"  -> Volatility ATR % <= 7%: {rem} (filtered {_FUNNEL_COUNTS.get('trade_gate_atr_pct_fail', 0)})")
        
        rem -= _FUNNEL_COUNTS.get("trade_gate_invalid_stop_fail", 0)
        print(f"  -> Stop Loss Valid (< Entry): {rem} (filtered {_FUNNEL_COUNTS.get('trade_gate_invalid_stop_fail', 0)})")
        
        rem -= _FUNNEL_COUNTS.get("trade_gate_stop_too_wide_fail", 0)
        print(f"  -> Stop Loss Risk <= Max Allowed: {rem} (filtered {_FUNNEL_COUNTS.get('trade_gate_stop_too_wide_fail', 0)})")
        
        # Non-Bandar specifics
        non_bandar_rejections = (
            _FUNNEL_COUNTS.get("trade_gate_non_bandar_volume_fail", 0) +
            _FUNNEL_COUNTS.get("trade_gate_non_bandar_rebound_fail", 0) +
            _FUNNEL_COUNTS.get("trade_gate_non_bandar_activity_fail", 0) +
            _FUNNEL_COUNTS.get("trade_gate_non_bandar_pullback_fail", 0)
        )
        rem -= non_bandar_rejections
        print(f"  -> Non-Bandar volume/setup triggers: {rem} (filtered sum of non-bandar volume, rebound, activity, pullback filters)")
        
        rem -= _FUNNEL_COUNTS.get("trade_gate_bad_rr_tp1_fail", 0)
        print(f"  -> Risk/Reward TP1 >= Threshold: {rem} (filtered {_FUNNEL_COUNTS.get('trade_gate_bad_rr_tp1_fail', 0)})")
        
        rem -= _FUNNEL_COUNTS.get("trade_gate_bad_rr_tp2_fail", 0)
        print(f"  -> Risk/Reward TP2 >= Threshold: {rem} (filtered {_FUNNEL_COUNTS.get('trade_gate_bad_rr_tp2_fail', 0)})")
        
        rem -= _FUNNEL_COUNTS.get("trade_gate_position_size_lots_fail", 0)
        print(f"  -> Theoretical Position Size >= 1 lot: {rem} (filtered {_FUNNEL_COUNTS.get('trade_gate_position_size_lots_fail', 0)})")
        
        rem -= _FUNNEL_COUNTS.get("trade_gate_pending_orderbook_draft", 0)
        print(f"  -> Orderbook confirmed (not pending): {rem} (filtered/draft pending {_FUNNEL_COUNTS.get('trade_gate_pending_orderbook_draft', 0)})")
        
        print(f"  -> VALID TRADE PLANS: {_FUNNEL_COUNTS.get('trade_gate_pass_valid_plan', 0)}")
    print("=" * 60)

IDX_TICK_TABLE = [
    {"min_price": 0, "max_price": 200, "tick": 1},
    {"min_price": 200, "max_price": 500, "tick": 2},
    {"min_price": 500, "max_price": 2000, "tick": 5},
    {"min_price": 2000, "max_price": 5000, "tick": 10},
    {"min_price": 5000, "max_price": None, "tick": 25},
]

TRADE_STATUSES = [
    "VALID_TRADE_PLAN",
    "DRAFT_PLAN_PENDING_ORDERBOOK",
    "SKIPPED_NOT_TRADE_CANDIDATE",
    "SKIPPED_NO_BROKER_DATA",
    "SKIPPED_NO_ORDERBOOK_DATA",
    "SKIPPED_LOW_BANDARMOLOGY_SCORE",
    "SKIPPED_NO_BANDAR_CONFIRMATION",
    "WATCH_BANDAR_ACCUMULATION_WAIT_TECHNICAL_TRIGGER",
    "WATCH_SHORT_TERM_ACCUMULATION_AGAINST_DISTRIBUTION",
    "WATCH_PULLBACK_WITH_MEDIUM_ACCUMULATION",
    "WATCH_CORPORATE_ACTION_RISK",
    "INVALID_DATA",
    "WAIT_FOR_VOLUME_CONFIRMATION",
    "WAIT_FOR_REBOUND_CONFIRMATION",
    "WAIT_FOR_PULLBACK",
    "WAIT_FOR_ACTIVITY",
    "WAIT_FOR_BETTER_ENTRY",
    "REJECT_INVALID_STOP",
    "REJECT_STOP_TOO_WIDE",
    "REJECT_BAD_RISK_REWARD_TP1",
    "REJECT_BAD_RISK_REWARD_TP2",
    "REJECT_TOO_VOLATILE",
    "REJECT_POSITION_TOO_SMALL",
    "REJECT_NOT_TRADABLE",
    "REJECT_UMA_OR_NOTATION_RISK",
    "REJECT_CORPORATE_ACTION_RISK",
    "WAIT_ORDERBOOK_SPREAD_TOO_WIDE",
    "WAIT_ORDERBOOK_OFFER_WALL",
    "WAIT_ORDERBOOK_BID_DEPTH_WEAK",
    "WAIT_ORDERBOOK_NEAR_ARA_ARB",
]

PLAN_NUMERIC_COLUMNS = [
    "raw_entry_trigger_price",
    "raw_entry_price",
    "raw_entry_zone_low",
    "raw_entry_zone_high",
    "raw_stop_loss",
    "raw_take_profit_1",
    "raw_take_profit_2",
    "entry_trigger_price",
    "entry_price",
    "entry_zone_low",
    "entry_zone_high",
    "stop_loss",
    "take_profit_1",
    "take_profit_2",
    "risk_pct",
    "reward_pct_tp1",
    "reward_pct_tp2",
    "risk_reward_tp1",
    "risk_reward_tp2",
    "risk_per_share",
    "risk_per_lot",
    "theoretical_position_size_lots",
    "executable_position_size_lots",
    "position_size_lots",
    "theoretical_position_value",
    "executable_position_value",
    "theoretical_max_loss_amount",
    "executable_max_loss_amount",
]

STAGE3_OUTPUT_COLUMNS = [
    "ticker",
    "yahoo_ticker",
    "last_date",
    "entry_setup",
    "trade_status",
    "is_plan_valid",
    "trade_reason",
    "trade_summary",
    "close",
    "raw_entry_trigger_price",
    "raw_entry_price",
    "raw_entry_zone_low",
    "raw_entry_zone_high",
    "raw_stop_loss",
    "raw_take_profit_1",
    "raw_take_profit_2",
    "entry_trigger_price",
    "entry_price",
    "entry_zone_low",
    "entry_zone_high",
    "stop_loss",
    "take_profit_1",
    "take_profit_2",
    "tick_size",
    "prices_are_tick_valid",
    "rounding_applied",
    "rounding_note",
    "risk_pct",
    "reward_pct_tp1",
    "reward_pct_tp2",
    "risk_reward_tp1",
    "risk_reward_tp2",
    "capital",
    "risk_per_trade_pct",
    "risk_amount",
    "risk_per_share",
    "risk_per_lot",
    "theoretical_position_size_lots",
    "executable_position_size_lots",
    "position_size_lots",
    "theoretical_position_value",
    "executable_position_value",
    "theoretical_max_loss_amount",
    "executable_max_loss_amount",
    "time_stop_days",
    "strategy_mode",
    "force_exit_same_day",
    "orderbook_confirmation_required",
    "liquidity_bucket",
    "relative_activity_bucket",
    "technical_context",
    "bandar_watch_eligible",
    "bandarmology_score",
    "bandarmology_signal",
    "bandarmology_reason",
    "bandarmology_summary",
    "broker_activity_available",
    "orderbook_status",
    "orderbook_score",
    "spread_pct",
    "depth_imbalance_top5",
    "offer_wall_ratio_top5",
    "bid_volume_top5",
    "offer_volume_top5",
    "fnet",
    "foreign_net_ratio",
    "tradable",
    "uma",
    "notation",
    "notation_risky",
    "corp_action",
    "corp_action_active",
    "near_ara",
    "near_arb",
    "execution_quality_note",
    "volume",
    "value_est",
    "avg_volume_20d",
    "avg_value_20d",
    "trend_score",
    "momentum_score",
    "volatility_score",
    "rsi14",
    "atr14",
    "atr_pct",
    "volume_ratio",
    "value_ratio",
    "return_1d",
    "return_3d",
    "return_5d",
    "return_10d",
    "return_20d",
    "ma20",
    "ma50",
    "ma100",
    "ma200",
    "high_20d",
    "low_20d",
    "distance_to_20d_high",
    "distance_from_20d_low",
    "distance_to_ma20",
    "distance_to_ma50",
    "close_location",
    "data_points",
    "is_data_valid",
]


@dataclass(frozen=True)
class TradePlanConfig:
    capital: float = 500_000
    risk_per_trade_pct: float | None = None
    max_risk_per_trade_pct: float | None = None
    max_position_pct: float | None = None
    tp1_pct: float | None = None
    tp2_pct: float | None = None
    max_stop_loss_pct: float | None = None
    min_rr_tp1: float = 1.0
    min_rr_tp2: float = 1.5
    rebound_min_rr_tp1: float = 1.1
    rebound_min_rr_tp2: float = 1.6
    time_stop_days: int | None = None
    lot_size: int = 100
    bandarmology_min_score: int = 50
    allow_trade_without_broker_data: bool = False
    require_orderbook_confirmation: bool | None = None
    strategy_mode: str = "interday"
    force_exit_same_day: bool | None = None
    strict_corporate_action_filter: bool = False

    def __post_init__(self) -> None:
        mode = str(self.strategy_mode or "interday").lower()
        if mode not in {"interday", "bpjs"}:
            raise ValueError("strategy_mode must be either 'interday' or 'bpjs'")
        object.__setattr__(self, "strategy_mode", mode)

        defaults = {
            "interday": {
                "risk_per_trade_pct": 0.005,
                "max_risk_per_trade_pct": 0.01,
                "max_position_pct": 0.20,
                "tp1_pct": 0.05,
                "tp2_pct": 0.08,
                "max_stop_loss_pct": 0.10,
                "time_stop_days": 10,
                "require_orderbook_confirmation": False,
                "force_exit_same_day": False,
            },
            "bpjs": {
                "risk_per_trade_pct": DEFAULT_BPJS_PROFILE.risk_per_trade_pct,
                "max_risk_per_trade_pct": DEFAULT_BPJS_PROFILE.max_risk_per_trade_pct,
                "max_position_pct": DEFAULT_BPJS_PROFILE.max_position_pct,
                "tp1_pct": DEFAULT_BPJS_PROFILE.target_tp1_pct,
                "tp2_pct": DEFAULT_BPJS_PROFILE.target_tp2_pct,
                "max_stop_loss_pct": DEFAULT_BPJS_PROFILE.maximum_stop_loss_pct,
                "time_stop_days": DEFAULT_BPJS_PROFILE.maximum_holding_sessions,
                "require_orderbook_confirmation": True,
                "force_exit_same_day": False,
            },
        }[mode]
        for field_name, default_value in defaults.items():
            if getattr(self, field_name) is None:
                object.__setattr__(self, field_name, default_value)

    @property
    def risk_amount(self) -> float:
        bounded_risk_pct = min(float(self.risk_per_trade_pct), float(self.max_risk_per_trade_pct))
        return self.capital * bounded_risk_pct


def _value(row: dict[str, Any] | pd.Series, key: str, default: float = 0.0) -> float:
    value = row.get(key, default)
    return float(value) if value is not None and pd.notna(value) else default


def _bool_value(value: Any) -> bool:
    if value is None or pd.isna(value):
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "y"}
    return bool(value)


def _has_bandarmology_context(row: dict[str, Any] | pd.Series) -> bool:
    return any(key in row for key in ["bandarmology_signal", "bandarmology_score", "broker_activity_available"])


def _has_orderbook_context(row: dict[str, Any] | pd.Series) -> bool:
    return any(key in row for key in ["orderbook_status", "orderbook_score"])


def _nan_plan_fields(result: dict[str, Any]) -> None:
    for column in PLAN_NUMERIC_COLUMNS:
        result[column] = pd.NA
    result["tick_size"] = pd.NA
    result["prices_are_tick_valid"] = False
    result["rounding_applied"] = False
    result["rounding_note"] = pd.NA


def get_idx_tick_size(price: float, tick_table: list[dict[str, Any]] | None = None) -> int:
    tick_table = tick_table or IDX_TICK_TABLE
    if price is None or pd.isna(price) or price < 0:
        raise ValueError(f"Invalid price for IDX tick size: {price!r}")

    for rule in tick_table:
        min_price = rule["min_price"]
        max_price = rule["max_price"]
        if price >= min_price and (max_price is None or price < max_price):
            return int(rule["tick"])
    raise ValueError(f"No IDX tick rule found for price: {price}")


def round_price_to_tick(price: float, mode: str = "nearest") -> float:
    if price is None or pd.isna(price):
        return pd.NA
    tick = get_idx_tick_size(float(price))
    scaled = float(price) / tick
    if mode == "floor":
        return float(math.floor(scaled) * tick)
    if mode == "ceil":
        return float(math.ceil(scaled) * tick)
    if mode == "nearest":
        return float(math.floor(scaled + 0.5) * tick)
    raise ValueError(f"Unsupported rounding mode: {mode}")


def _price_is_tick_valid(price: float) -> bool:
    if price is None or pd.isna(price):
        return False
    tick = get_idx_tick_size(float(price))
    return math.isclose(float(price) % tick, 0.0, abs_tol=1e-9)


def round_trade_plan_prices(plan: dict[str, Any]) -> dict[str, Any]:
    rounded = dict(plan)
    rounded["entry_trigger_price"] = round_price_to_tick(plan["raw_entry_trigger_price"], "nearest")
    rounded["entry_price"] = round_price_to_tick(plan["raw_entry_price"], "nearest")
    rounded["entry_zone_low"] = round_price_to_tick(plan["raw_entry_zone_low"], "floor")
    rounded["entry_zone_high"] = round_price_to_tick(plan["raw_entry_zone_high"], "ceil")
    rounded["stop_loss"] = round_price_to_tick(plan["raw_stop_loss"], "floor")
    rounded["take_profit_1"] = round_price_to_tick(plan["raw_take_profit_1"], "floor")
    rounded["take_profit_2"] = round_price_to_tick(plan["raw_take_profit_2"], "floor")
    rounded["tick_size"] = get_idx_tick_size(float(rounded["entry_price"]))

    raw_to_final = [
        ("raw_entry_trigger_price", "entry_trigger_price"),
        ("raw_entry_price", "entry_price"),
        ("raw_entry_zone_low", "entry_zone_low"),
        ("raw_entry_zone_high", "entry_zone_high"),
        ("raw_stop_loss", "stop_loss"),
        ("raw_take_profit_1", "take_profit_1"),
        ("raw_take_profit_2", "take_profit_2"),
    ]
    rounding_applied = any(
        not math.isclose(float(rounded[raw]), float(rounded[final]), abs_tol=1e-9)
        for raw, final in raw_to_final
    )
    rounded["rounding_applied"] = rounding_applied
    rounded["prices_are_tick_valid"] = all(
        _price_is_tick_valid(rounded[column])
        for column in ["entry_trigger_price", "entry_price", "stop_loss", "take_profit_1", "take_profit_2"]
    )
    rounded["rounding_note"] = "prices_rounded_to_idx_tick_size" if rounding_applied else "no_rounding_needed"
    return rounded


def load_stage_2_candidates(input_path: str | Path) -> pd.DataFrame:
    path = Path(input_path)
    if not path.exists():
        raise FileNotFoundError(f"Stage 2 input file not found: {path}")

    df = pd.read_csv(path)
    required = {
        "ticker",
        "yahoo_ticker",
        "last_date",
        "close",
        "entry_setup",
        "liquidity_bucket",
        "relative_activity_bucket",
        "trend_score",
        "momentum_score",
        "volatility_score",
        "atr14",
        "atr_pct",
        "volume_ratio",
        "value_ratio",
        "high_20d",
        "low_20d",
        "ma20",
        "ma50",
        "distance_from_20d_low",
        "distance_to_ma20",
        "close_location",
        "is_data_valid",
    }
    missing = required.difference(df.columns)
    if missing:
        raise ValueError(f"Stage 2 input is missing columns: {', '.join(sorted(missing))}")
    return df.copy()


def determine_entry_style(row: dict[str, Any] | pd.Series) -> str:
    setup = _plan_setup(row)
    if setup == "BREAKOUT_CANDIDATE":
        return "BREAKOUT_TRIGGER"
    if setup == "PULLBACK_CANDIDATE":
        return "PULLBACK_CONTINUATION"
    if setup == "REBOUND_CANDIDATE":
        return "REBOUND_CONFIRMATION"
    if setup == "WATCH_ENTRY":
        return "MOMENTUM_CONTINUATION"
    return "NO_TRADE"


def _plan_setup(row: dict[str, Any] | pd.Series) -> str:
    setup = row.get("entry_setup")
    if setup in ACTIONABLE_SETUPS:
        return str(setup)

    context = row.get("technical_context")
    if context == "BREAKOUT_NEAR":
        return "BREAKOUT_CANDIDATE"
    if context in {"PULLBACK_TO_MA", "UPTREND_CONTINUATION"}:
        return "PULLBACK_CANDIDATE"
    if context in {"REBOUND_NEAR_LOW", "EARLY_REVERSAL_ATTEMPT"}:
        return "REBOUND_CANDIDATE"
    if context in {"VOLUME_SPIKE", "SIDEWAYS_COMPRESSION"}:
        return "WATCH_ENTRY"
    return "NO_TRADE"


def calculate_entry_plan(row: dict[str, Any] | pd.Series) -> dict[str, float | str]:
    if row.get("entry_price") is not None and pd.notna(row.get("entry_price")):
        entry_price = _value(row, "entry_price")
        return {
            "entry_style": determine_entry_style(row),
            "entry_trigger_price": _value(row, "entry_trigger_price", entry_price),
            "entry_price": entry_price,
            "entry_zone_low": _value(row, "entry_zone_low", entry_price),
            "entry_zone_high": _value(row, "entry_zone_high", entry_price),
        }

    close = _value(row, "close")
    atr14 = _value(row, "atr14")
    high_20d = _value(row, "high_20d", close)
    ma20 = _value(row, "ma20", close)
    setup = _plan_setup(row)

    if setup == "BREAKOUT_CANDIDATE":
        entry_price = max(close, high_20d * 0.98)
        return {
            "entry_style": "BREAKOUT_TRIGGER",
            "entry_trigger_price": entry_price,
            "entry_price": entry_price,
            "entry_zone_low": entry_price,
            "entry_zone_high": entry_price * 1.01,
        }
    if setup == "PULLBACK_CANDIDATE":
        zone_low = min(close, ma20 * 0.99)
        zone_high = max(close, ma20 * 1.01)
        return {
            "entry_style": "PULLBACK_CONTINUATION",
            "entry_trigger_price": close,
            "entry_price": close,
            "entry_zone_low": zone_low,
            "entry_zone_high": zone_high,
        }
    if setup == "REBOUND_CANDIDATE":
        entry_price = close + (0.10 * atr14)
        return {
            "entry_style": "REBOUND_CONFIRMATION",
            "entry_trigger_price": entry_price,
            "entry_price": entry_price,
            "entry_zone_low": close,
            "entry_zone_high": close + (0.50 * atr14),
        }
    if setup == "WATCH_ENTRY":
        return {
            "entry_style": "MOMENTUM_CONTINUATION",
            "entry_trigger_price": close,
            "entry_price": close,
            "entry_zone_low": close * 0.995,
            "entry_zone_high": close * 1.01,
        }

    return {
        "entry_style": "NO_TRADE",
        "entry_trigger_price": pd.NA,
        "entry_price": pd.NA,
        "entry_zone_low": pd.NA,
        "entry_zone_high": pd.NA,
    }


def calculate_stop_loss(row: dict[str, Any] | pd.Series, entry_price: float) -> float:
    if row.get("stop_loss") is not None and pd.notna(row.get("stop_loss")):
        return _value(row, "stop_loss")

    setup = _plan_setup(row)
    close = _value(row, "close")
    atr14 = _value(row, "atr14")
    low_20d = _value(row, "low_20d", close)
    ma20 = _value(row, "ma20", close)
    ma50 = _value(row, "ma50", close)

    if setup == "BREAKOUT_CANDIDATE":
        return max(entry_price - (1.5 * atr14), ma20 * 0.97)
    if setup == "PULLBACK_CANDIDATE":
        return min(ma20 * 0.97, entry_price - atr14)
    if setup == "REBOUND_CANDIDATE":
        return min(low_20d * 0.99, entry_price - (1.2 * atr14))
    if setup == "WATCH_ENTRY":
        return max(entry_price - (1.3 * atr14), ma50 * 0.98)
    return pd.NA


def calculate_theoretical_position_size(
    entry_price: float,
    stop_loss: float,
    config: TradePlanConfig,
) -> dict[str, float | int]:
    risk_per_share = max(entry_price - stop_loss, 0)
    risk_per_lot = risk_per_share * config.lot_size
    if entry_price <= 0 or risk_per_share <= 0:
        return {
            "risk_per_share": risk_per_share,
            "risk_per_lot": risk_per_lot,
            "theoretical_position_size_lots": 0,
            "theoretical_position_value": 0.0,
            "theoretical_max_loss_amount": 0.0,
        }

    risk_based_lots = int(config.risk_amount // risk_per_lot) if risk_per_lot > 0 else 0
    max_position_value = config.capital * config.max_position_pct
    capital_based_lots = int(max_position_value // (entry_price * config.lot_size))
    lots = max(0, min(risk_based_lots, capital_based_lots))
    position_value = lots * config.lot_size * entry_price
    max_loss = lots * risk_per_lot
    return {
        "risk_per_share": risk_per_share,
        "risk_per_lot": risk_per_lot,
        "theoretical_position_size_lots": lots,
        "theoretical_position_value": position_value,
        "theoretical_max_loss_amount": max_loss,
    }


def _minimum_lot_reference_price(row: dict[str, Any] | pd.Series) -> float:
    for column in ["entry_price", "raw_entry_price", "close"]:
        price = _value(row, column)
        if price > 0:
            return price
    return 0.0


def can_afford_minimum_lot(row: dict[str, Any] | pd.Series, config: TradePlanConfig) -> bool:
    reference_price = _minimum_lot_reference_price(row)
    if reference_price <= 0:
        return True
    minimum_lot_value = reference_price * config.lot_size
    max_position_value = config.capital * config.max_position_pct
    return max_position_value >= minimum_lot_value


def _status_reason_summary(status: str) -> tuple[str, str]:
    mapping = {
        "VALID_TRADE_PLAN": (
            "valid_trade_plan_with_acceptable_risk_reward_and_position_size",
            "Trade plan is valid under the configured risk limit. Entry, stop-loss, take-profit, and executable position size are defined.",
        ),
        "DRAFT_PLAN_PENDING_ORDERBOOK": (
            "draft_plan_pending_orderbook_confirmation",
            "Draft trade plan is otherwise valid, but Stage 3C orderbook confirmation has not been checked yet. Do not execute until orderbook is reviewed.",
        ),
        "SKIPPED_NOT_TRADE_CANDIDATE": (
            "skipped_because_stage2_setup_is_not_trade_candidate",
            "Skipped because Stage 2 did not classify this ticker as an actionable trade candidate.",
        ),
        "SKIPPED_NO_BROKER_DATA": (
            "skipped_because_no_broker_summary_data_available",
            "Skipped because no broker summary data is available and broker confirmation is required.",
        ),
        "SKIPPED_NO_ORDERBOOK_DATA": (
            "skipped_because_no_orderbook_data_available",
            "Skipped because orderbook confirmation is required but no orderbook data is available.",
        ),
        "SKIPPED_LOW_BANDARMOLOGY_SCORE": (
            "skipped_because_bandarmology_score_below_threshold",
            "Skipped because bandarmology score is below the configured threshold.",
        ),
        "SKIPPED_NO_BANDAR_CONFIRMATION": (
            "skipped_because_broker_flow_does_not_confirm_accumulation",
            "Skipped because broker flow does not show accumulation confirmation.",
        ),
        "WATCH_BANDAR_ACCUMULATION_WAIT_TECHNICAL_TRIGGER": (
            "watching_bandar_accumulation_but_waiting_for_technical_trigger",
            "Broker flow shows accumulation, but technical context is still weak. Wait for a cleaner technical trigger before building an executable trade plan.",
        ),
        "WATCH_SHORT_TERM_ACCUMULATION_AGAINST_DISTRIBUTION": (
            "short_term_accumulation_against_medium_distribution",
            "Short-term broker flow improves, but medium-window distribution is still dominant. Keep on watchlist, do not execute by default.",
        ),
        "WATCH_PULLBACK_WITH_MEDIUM_ACCUMULATION": (
            "pullback_inside_medium_term_accumulation",
            "Short-term selling appears inside a medium-term accumulation structure. Watch for reversal confirmation before execution.",
        ),
        "WATCH_CORPORATE_ACTION_RISK": (
            "watching_because_corporate_action_risk_is_active",
            "Corporate action risk is active. Keep this ticker on watchlist and avoid building an executable trade plan by default.",
        ),
        "INVALID_DATA": (
            "invalid_data_from_stage2",
            "Skipped because Stage 2 data is invalid or incomplete.",
        ),
        "WAIT_FOR_VOLUME_CONFIRMATION": (
            "waiting_for_volume_confirmation",
            "Setup is technically interesting, but volume or value confirmation is not strong enough yet.",
        ),
        "WAIT_FOR_REBOUND_CONFIRMATION": (
            "waiting_for_rebound_confirmation",
            "Rebound setup is interesting, but relative activity is not supportive enough yet.",
        ),
        "WAIT_FOR_PULLBACK": (
            "waiting_for_pullback_to_entry_zone",
            "Pullback setup is interesting, but price is still too far from the intended MA20 entry zone.",
        ),
        "WAIT_FOR_ACTIVITY": (
            "waiting_for_activity_to_return",
            "Setup is technically interesting, but today's relative activity is too quiet.",
        ),
        "WAIT_FOR_BETTER_ENTRY": (
            "waiting_for_better_entry_to_improve_risk_reward",
            "Setup is technically interesting, but a better entry is needed to improve risk-reward.",
        ),
        "REJECT_INVALID_STOP": (
            "rejected_because_stop_loss_is_invalid",
            "Trade plan is rejected because the stop-loss is not valid below the entry price.",
        ),
        "REJECT_STOP_TOO_WIDE": (
            "rejected_because_stop_loss_exceeds_maximum_allowed_risk",
            "Setup is technically interesting, but the required stop-loss is wider than the configured maximum risk. Wait for a better entry.",
        ),
        "REJECT_BAD_RISK_REWARD_TP1": (
            "rejected_because_risk_reward_tp1_is_below_threshold",
            "Setup is technically interesting, but the first upside target does not compensate for the downside risk.",
        ),
        "REJECT_BAD_RISK_REWARD_TP2": (
            "rejected_because_risk_reward_tp2_is_below_threshold",
            "Setup is technically interesting, but the second upside target does not compensate for the downside risk.",
        ),
        "REJECT_TOO_VOLATILE": (
            "rejected_because_atr_pct_is_above_limit",
            "Trade plan is rejected because volatility is too high for a clean 5-10% take-profit setup.",
        ),
        "REJECT_POSITION_TOO_SMALL": (
            "rejected_because_position_size_is_too_small",
            "Trade plan is rejected because the configured capital and risk limit cannot buy at least one lot.",
        ),
        "REJECT_NOT_TRADABLE": (
            "rejected_because_stock_is_not_tradable",
            "Orderbook says the stock is not tradable now. Do not execute.",
        ),
        "REJECT_UMA_OR_NOTATION_RISK": (
            "rejected_because_uma_or_special_notation_risk",
            "Orderbook has UMA or special notation risk. Do not execute by default.",
        ),
        "COMMODITY_HEADWIND": (
            "watching_because_commodity_headwind_is_active",
            "The underlying global commodity is down heavily. Avoid buying this ticker now.",
        ),
        "REJECT_CORPORATE_ACTION_RISK": (
            "rejected_because_corporate_action_risk",
            "Corporate action risk is present. Do not execute by default.",
        ),
        "WAIT_ORDERBOOK_SPREAD_TOO_WIDE": (
            "waiting_because_orderbook_spread_is_too_wide",
            "Orderbook spread is too wide for clean execution. Wait for a tighter spread.",
        ),
        "WAIT_ORDERBOOK_OFFER_WALL": (
            "waiting_because_orderbook_offer_wall_is_heavy",
            "Offer wall is heavy near the top of book. Wait for supply to thin before execution.",
        ),
        "WAIT_ORDERBOOK_BID_DEPTH_WEAK": (
            "waiting_because_orderbook_bid_depth_is_weak",
            "Bid depth is weak versus offer depth. Wait for stronger support before execution.",
        ),
        "WAIT_ORDERBOOK_NEAR_ARA_ARB": (
            "waiting_because_price_is_near_auto_reject_band",
            "Price is too close to ARA/ARB. Avoid chasing execution around auto-reject bands.",
        ),
    }
    return mapping[status]


def _apply_rounding_reason_summary(result: dict[str, Any]) -> None:
    status = result.get("trade_status")
    if status == "VALID_TRADE_PLAN":
        result["trade_reason"] = "valid_trade_plan_after_idx_tick_rounding"
        result["trade_summary"] = (
            "Trade plan remains valid after IDX tick-size rounding. Entry, stop-loss, take-profit, "
            "and executable position size are defined using valid price increments."
        )
        return

    if not result.get("rounding_applied"):
        return

    if status == "REJECT_STOP_TOO_WIDE":
        result["trade_reason"] = "rounded_stop_loss_increased_actual_risk"
        result["trade_summary"] = (
            "Stop-loss rounding increased actual downside risk. Trade is rejected because risk exceeds "
            "the configured limit."
        )
    elif status in {"REJECT_BAD_RISK_REWARD_TP1", "REJECT_BAD_RISK_REWARD_TP2"}:
        result["trade_reason"] = "rejected_after_tick_rounding_because_risk_reward_deteriorated"
        result["trade_summary"] = (
            "Raw trade plan looked valid, but after conservative IDX tick-size rounding, risk/reward "
            "no longer meets the configured threshold."
        )


def recalculate_plan_after_rounding(
    plan: dict[str, Any],
    row: dict[str, Any] | pd.Series,
    config: TradePlanConfig,
) -> dict[str, Any]:
    entry_price = _value(plan, "entry_price")
    stop_loss = _value(plan, "stop_loss")
    take_profit_1 = _value(plan, "take_profit_1")
    take_profit_2 = _value(plan, "take_profit_2")

    risk_per_share = entry_price - stop_loss if entry_price > 0 else 0
    plan["risk_pct"] = risk_per_share / entry_price if entry_price > 0 else pd.NA
    plan["reward_pct_tp1"] = (take_profit_1 - entry_price) / entry_price if entry_price > 0 else pd.NA
    plan["reward_pct_tp2"] = (take_profit_2 - entry_price) / entry_price if entry_price > 0 else pd.NA
    plan["risk_reward_tp1"] = (take_profit_1 - entry_price) / risk_per_share if risk_per_share > 0 else 0
    plan["risk_reward_tp2"] = (take_profit_2 - entry_price) / risk_per_share if risk_per_share > 0 else 0
    plan.update(calculate_theoretical_position_size(entry_price, stop_loss, config))
    plan["risk_per_share"] = risk_per_share
    plan["risk_per_lot"] = risk_per_share * config.lot_size
    return plan


def build_execution_quality_note(row: dict[str, Any] | pd.Series, config: TradePlanConfig) -> str:
    if not _has_orderbook_context(row):
        return "No orderbook snapshot was provided."
    status = row.get("orderbook_status")
    score = row.get("orderbook_score")
    spread_pct = row.get("spread_pct")
    imbalance = row.get("depth_imbalance_top5")
    parts = [f"Orderbook status: {status or 'UNKNOWN'}"]
    if score is not None and pd.notna(score):
        parts.append(f"score={float(score):.0f}")
    if spread_pct is not None and pd.notna(spread_pct):
        parts.append(f"spread_pct={float(spread_pct):.4f}")
    if imbalance is not None and pd.notna(imbalance):
        parts.append(f"depth_imbalance_top5={float(imbalance):.2f}")
    if _bool_value(row.get("corp_action_active")):
        parts.append("corporate_action_active=True")
    if _bool_value(row.get("notation_risky")):
        parts.append("notation_risky=True")
    parts.append(f"strategy_mode={config.strategy_mode}")
    return "; ".join(parts)


def _orderbook_trade_status(row: dict[str, Any] | pd.Series, config: TradePlanConfig) -> str | None:
    if _bool_value(row.get("orderbook_confirmation_required")) and row.get("orderbook_status") == "NOT_CHECKED":
        return None
    corp_action_active = _bool_value(row.get("corp_action_active"))
    if config.strategy_mode == "interday":
        if corp_action_active and config.strict_corporate_action_filter:
            return "REJECT_CORPORATE_ACTION_RISK"
        if corp_action_active:
            return "WATCH_CORPORATE_ACTION_RISK"
        if not config.require_orderbook_confirmation:
            return None
    if config.strategy_mode == "bpjs" and corp_action_active:
        return "REJECT_CORPORATE_ACTION_RISK"
    if not config.require_orderbook_confirmation:
        return None
    status = row.get("orderbook_status")
    if status is None or pd.isna(status) or status == "":
        return "SKIPPED_NO_ORDERBOOK_DATA"
    mapping = {
        "NO_ORDERBOOK_DATA": "SKIPPED_NO_ORDERBOOK_DATA",
        "REJECT_NOT_TRADABLE": "REJECT_NOT_TRADABLE",
        "REJECT_UMA_OR_NOTATION_RISK": "REJECT_UMA_OR_NOTATION_RISK",
        "REJECT_CORPORATE_ACTION_RISK": "REJECT_CORPORATE_ACTION_RISK",
        "WAIT_SPREAD_TOO_WIDE": "WAIT_ORDERBOOK_SPREAD_TOO_WIDE",
        "WAIT_OFFER_WALL": "WAIT_ORDERBOOK_OFFER_WALL",
        "WAIT_BID_DEPTH_WEAK": "WAIT_ORDERBOOK_BID_DEPTH_WEAK",
        "WAIT_NEAR_ARA_ARB": "WAIT_ORDERBOOK_NEAR_ARA_ARB",
    }
    if status in {"ORDERBOOK_SUPPORTIVE", "ORDERBOOK_NEUTRAL"}:
        return None
    return mapping.get(str(status), "SKIPPED_NO_ORDERBOOK_DATA")


def validate_pre_plan_gate(result: dict[str, Any], config: TradePlanConfig) -> str | None:
    _inc_funnel("total_inputs")
    if not _bool_value(result.get("is_data_valid")):
        _inc_funnel("pre_gate_is_data_valid_fail")
        return "INVALID_DATA"

    has_bandar_columns = _has_bandarmology_context(result)
    if has_bandar_columns:
        _inc_funnel("pre_gate_is_bandar_path")
        if result.get("liquidity_bucket") not in {"HIGH_LIQUIDITY", "GOOD_LIQUIDITY"}:
            _inc_funnel("bandar_liquidity_bucket_fail")
            return "SKIPPED_NOT_TRADE_CANDIDATE"
        if not _bool_value(result.get("bandar_watch_eligible")):
            _inc_funnel("bandar_watch_eligible_fail")
            return "SKIPPED_NOT_TRADE_CANDIDATE"
        technical_context = result.get("technical_context")
        if technical_context == "INVALID_DATA":
            _inc_funnel("bandar_technical_context_invalid_fail")
            return "INVALID_DATA"
        if technical_context == "TOO_VOLATILE":
            _inc_funnel("bandar_technical_context_too_volatile_fail")
            return "REJECT_TOO_VOLATILE"

        broker_available = _bool_value(result.get("broker_activity_available"))
        signal = result.get("bandarmology_signal")
        score = _value(result, "bandarmology_score")
        if (not broker_available or signal == "NO_BROKER_DATA") and not config.allow_trade_without_broker_data:
            _inc_funnel("bandar_broker_data_unavailable_fail")
            return "SKIPPED_NO_BROKER_DATA"
        if broker_available and signal in {"STRONG_DISTRIBUTION", "MILD_DISTRIBUTION"}:
            _inc_funnel("bandar_distribution_fail")
            return "SKIPPED_NO_BANDAR_CONFIRMATION"
        if broker_available and signal == "SHORT_TERM_ACCUMULATION_AGAINST_MEDIUM_DISTRIBUTION":
            _inc_funnel("bandar_short_term_against_medium_watch")
            return "WATCH_SHORT_TERM_ACCUMULATION_AGAINST_DISTRIBUTION"
        if broker_available and signal == "PULLBACK_WITH_MEDIUM_ACCUMULATION":
            _inc_funnel("bandar_pullback_with_medium_acc_watch")
            return "WATCH_PULLBACK_WITH_MEDIUM_ACCUMULATION"
        if broker_available and signal == "NEUTRAL_FLOW":
            _inc_funnel("bandar_neutral_flow_fail")
            return "SKIPPED_LOW_BANDARMOLOGY_SCORE"
        if broker_available and score < config.bandarmology_min_score:
            _inc_funnel("bandar_low_score_fail")
            return "SKIPPED_LOW_BANDARMOLOGY_SCORE"
        if broker_available and signal not in {"STRONG_ACCUMULATION", "MILD_ACCUMULATION"}:
            _inc_funnel("bandar_no_accumulation_fail")
            return "SKIPPED_NO_BANDAR_CONFIRMATION"
        if not can_afford_minimum_lot(result, config):
            _inc_funnel("bandar_position_too_small_fail")
            return "REJECT_POSITION_TOO_SMALL"
        if technical_context == "TECHNICALLY_WEAK_BUT_LIQUID":
            _inc_funnel("bandar_weak_but_liquid_watch")
            return "WATCH_BANDAR_ACCUMULATION_WAIT_TECHNICAL_TRIGGER"
        if technical_context not in ACTIVE_TECHNICAL_CONTEXTS:
            _inc_funnel("bandar_inactive_technical_context_fail")
            return "SKIPPED_NOT_TRADE_CANDIDATE"
        orderbook_status = _orderbook_trade_status(result, config)
        if orderbook_status is not None:
            _inc_funnel("bandar_orderbook_status_fail")
            return orderbook_status
        _inc_funnel("bandar_pre_gate_pass")
    else:
        setup = result.get("entry_setup")
        if setup not in ACTIONABLE_SETUPS:
            _inc_funnel("non_bandar_entry_setup_fail")
            return "SKIPPED_NOT_TRADE_CANDIDATE"
        if "bandar_watch_eligible" in result and not _bool_value(result.get("bandar_watch_eligible")):
            _inc_funnel("non_bandar_watch_eligible_fail")
            return "SKIPPED_NOT_TRADE_CANDIDATE"
        if result.get("technical_context") in {"TOO_VOLATILE", "TOO_QUIET_ABSOLUTE", "INVALID_DATA"}:
            _inc_funnel("non_bandar_technical_context_fail")
            return "SKIPPED_NOT_TRADE_CANDIDATE"
        if not can_afford_minimum_lot(result, config):
            _inc_funnel("non_bandar_position_too_small_fail")
            return "REJECT_POSITION_TOO_SMALL"
        _inc_funnel("non_bandar_pre_gate_pass")
    return None


def validate_trade_status(result: dict[str, Any], config: TradePlanConfig) -> str:
    pre_plan_status = validate_pre_plan_gate(result, config)
    if pre_plan_status is not None:
        return pre_plan_status

    _inc_funnel("trade_gate_inputs")
    has_bandar_columns = _has_bandarmology_context(result)
    if _value(result, "atr_pct") > 0.07:
        _inc_funnel("trade_gate_atr_pct_fail")
        return "REJECT_TOO_VOLATILE"

    entry_price = _value(result, "entry_price")
    stop_loss = _value(result, "stop_loss")
    if entry_price <= 0 or stop_loss <= 0 or stop_loss >= entry_price:
        _inc_funnel("trade_gate_invalid_stop_fail")
        return "REJECT_INVALID_STOP"

    if _value(result, "risk_pct") > config.max_stop_loss_pct:
        _inc_funnel("trade_gate_stop_too_wide_fail")
        return "REJECT_STOP_TOO_WIDE"

    setup = _plan_setup(result)
    relative_activity = result.get("relative_activity_bucket")
    value_ratio = _value(result, "value_ratio")
    volume_ratio = _value(result, "volume_ratio")
    if not has_bandar_columns:
        if setup == "BREAKOUT_CANDIDATE" and value_ratio < 1.0 and volume_ratio < 1.0:
            _inc_funnel("trade_gate_non_bandar_volume_fail")
            return "WAIT_FOR_VOLUME_CONFIRMATION"
        if setup == "REBOUND_CANDIDATE" and relative_activity not in {"NORMAL", "NORMAL_TO_QUIET", "ACTIVE", "VERY_ACTIVE"}:
            _inc_funnel("trade_gate_non_bandar_rebound_fail")
            return "WAIT_FOR_REBOUND_CONFIRMATION"
        if relative_activity == "QUIET":
            _inc_funnel("trade_gate_non_bandar_activity_fail")
            return "WAIT_FOR_ACTIVITY"
        if setup == "PULLBACK_CANDIDATE" and abs(_value(result, "distance_to_ma20")) > 0.03:
            _inc_funnel("trade_gate_non_bandar_pullback_fail")
            return "WAIT_FOR_PULLBACK"

    min_rr_tp1 = config.rebound_min_rr_tp1 if setup == "REBOUND_CANDIDATE" else config.min_rr_tp1
    min_rr_tp2 = config.rebound_min_rr_tp2 if setup == "REBOUND_CANDIDATE" else config.min_rr_tp2
    if _value(result, "risk_reward_tp1") < min_rr_tp1:
        _inc_funnel("trade_gate_bad_rr_tp1_fail")
        return "REJECT_BAD_RISK_REWARD_TP1"
    if _value(result, "risk_reward_tp2") < min_rr_tp2:
        _inc_funnel("trade_gate_bad_rr_tp2_fail")
        return "REJECT_BAD_RISK_REWARD_TP2"

    if _value(result, "theoretical_position_size_lots") < 1:
        _inc_funnel("trade_gate_position_size_lots_fail")
        return "REJECT_POSITION_TOO_SMALL"

    if _bool_value(result.get("orderbook_confirmation_required")) and result.get("orderbook_status") == "NOT_CHECKED":
        _inc_funnel("trade_gate_pending_orderbook_draft")
        return "DRAFT_PLAN_PENDING_ORDERBOOK"

    _inc_funnel("trade_gate_pass_valid_plan")
    return "VALID_TRADE_PLAN"


def _merge_stage2_bandarmology(stage2_path: str | Path, bandarmology_path: str | Path) -> pd.DataFrame:
    try:
        stage2 = pd.read_csv(stage2_path)
        if stage2.empty:
            raise ValueError("Tidak ada emiten yang lolos screening Stage 2 (Technical). Watchlist kosong.")
    except (pd.errors.EmptyDataError, ValueError):
        raise ValueError("Tidak ada emiten yang lolos screening Stage 2 (Technical). Watchlist kosong.")

    try:
        bandar = pd.read_csv(bandarmology_path)
    except pd.errors.EmptyDataError:
        raise ValueError("Tidak ada data hasil analisis bandarmology dari Stage 3B (Data kosong/tidak ada emiten lolos).")

    # Double check if stage2 is empty
    if len(stage2) == 0:
        raise ValueError("Tidak ada emiten yang lolos screening Stage 2 (Technical). Watchlist kosong.")

    if len(bandar) == 0:
        # If bandar is empty, we return an empty DataFrame with the merged columns structure
        print("Warning: Stage 3B Bandarmology data is empty.")
        # Create empty df with key columns
        bandar = pd.DataFrame(columns=["ticker", "broker_activity_available", "bandarmology_score", "bandarmology_signal"])

    bandar_columns = [
        column
        for column in bandar.columns
        if column == "ticker" or column.startswith("bandarmology_") or column in {
            "broker_activity_available",
            "top_buyer_1_code",
            "top_buyer_1_value",
            "top_seller_1_code",
            "top_seller_1_value",
            "buyer_hhi",
            "seller_hhi",
            "close_vs_top_buyer_avg",
        }
    ]
    return stage2.merge(bandar[bandar_columns], on="ticker", how="left")


def _merge_orderbook(candidates: pd.DataFrame, orderbook_path: str | Path | None) -> pd.DataFrame:
    if not orderbook_path:
        return _mark_orderbook_not_checked(candidates)
    path = Path(orderbook_path)
    if not path.exists():
        return _mark_orderbook_not_checked(candidates)
    try:
        orderbook = pd.read_csv(path)
    except pd.errors.EmptyDataError:
        print("Warning: Orderbook CSV is empty. Skipping orderbook data merge.")
        return _mark_orderbook_not_checked(candidates)
    keep = [
        column
        for column in orderbook.columns
        if column == "ticker"
        or column
        in {
            "orderbook_status",
            "orderbook_score",
            "spread_pct",
            "depth_imbalance_top5",
            "offer_wall_ratio_top5",
            "bid_volume_top5",
            "offer_volume_top5",
            "fnet",
            "foreign_net_ratio",
            "tradable",
            "uma",
            "notation",
            "notation_risky",
            "corp_action",
            "corp_action_active",
            "near_ara",
            "near_arb",
        }
    ]
    merged = candidates.merge(orderbook[keep], on="ticker", how="left")
    merged["orderbook_confirmation_required"] = False
    return merged


def _mark_orderbook_not_checked(candidates: pd.DataFrame) -> pd.DataFrame:
    output = candidates.copy()
    output["orderbook_status"] = "NOT_CHECKED"
    output["orderbook_confirmation_required"] = True
    for column in [
        "orderbook_score",
        "spread_pct",
        "depth_imbalance_top5",
        "offer_wall_ratio_top5",
        "bid_volume_top5",
        "offer_volume_top5",
        "fnet",
        "foreign_net_ratio",
        "tradable",
        "uma",
        "notation",
        "notation_risky",
        "corp_action",
        "corp_action_active",
        "near_ara",
        "near_arb",
    ]:
        if column not in output.columns:
            output[column] = pd.NA
    return output


def build_trade_plan_row(row: dict[str, Any] | pd.Series, config: TradePlanConfig) -> dict[str, Any]:
    result = row.to_dict() if isinstance(row, pd.Series) else dict(row)
    result["capital"] = config.capital
    result["risk_per_trade_pct"] = min(config.risk_per_trade_pct, config.max_risk_per_trade_pct)
    result["risk_amount"] = config.risk_amount
    result["time_stop_days"] = config.time_stop_days
    result["strategy_mode"] = config.strategy_mode
    result["force_exit_same_day"] = config.force_exit_same_day
    result["execution_quality_note"] = build_execution_quality_note(result, config)

    pre_plan_status = validate_pre_plan_gate(result, config)
    if pre_plan_status is not None:
        _nan_plan_fields(result)
        if pre_plan_status == "REJECT_POSITION_TOO_SMALL":
            result["theoretical_position_size_lots"] = 0
            result["theoretical_position_value"] = 0.0
            result["theoretical_max_loss_amount"] = 0.0
        status = pre_plan_status
    else:
        raw_entry_plan = calculate_entry_plan(result)
        raw_entry_price = _value(raw_entry_plan, "entry_price")
        raw_stop_loss = calculate_stop_loss(result, raw_entry_price)

        result["entry_style"] = raw_entry_plan["entry_style"]
        result["raw_entry_trigger_price"] = raw_entry_plan["entry_trigger_price"]
        result["raw_entry_price"] = raw_entry_plan["entry_price"]
        result["raw_entry_zone_low"] = raw_entry_plan["entry_zone_low"]
        result["raw_entry_zone_high"] = raw_entry_plan["entry_zone_high"]
        result["raw_stop_loss"] = raw_stop_loss

        # Compute adaptive TP1: must be at least enough to satisfy min_rr_tp1
        # after tick-rounding, while keeping the configured tp1_pct as a floor.
        fixed_tp1 = raw_entry_price * (1 + config.tp1_pct) if raw_entry_price > 0 else pd.NA
        fixed_tp2 = raw_entry_price * (1 + config.tp2_pct) if raw_entry_price > 0 else pd.NA
        if raw_entry_price > 0 and pd.notna(raw_stop_loss) and raw_stop_loss < raw_entry_price:
            raw_risk = raw_entry_price - raw_stop_loss
            # Minimum TP1 that guarantees R:R >= min_rr_tp1 even after floor-rounding.
            # Add one tick as buffer because both TP (floor) and SL (floor) shift adversely.
            tick = get_idx_tick_size(raw_entry_price)
            setup = _plan_setup(result)
            min_rr = config.rebound_min_rr_tp1 if setup == "REBOUND_CANDIDATE" else config.min_rr_tp1
            minimum_tp1 = raw_entry_price + (raw_risk * min_rr) + tick
            result["raw_take_profit_1"] = max(fixed_tp1, minimum_tp1) if pd.notna(fixed_tp1) else minimum_tp1

            min_rr2 = config.rebound_min_rr_tp2 if setup == "REBOUND_CANDIDATE" else config.min_rr_tp2
            minimum_tp2 = raw_entry_price + (raw_risk * min_rr2) + tick
            result["raw_take_profit_2"] = max(fixed_tp2, minimum_tp2) if pd.notna(fixed_tp2) else minimum_tp2
        else:
            result["raw_take_profit_1"] = fixed_tp1
            result["raw_take_profit_2"] = fixed_tp2

        if raw_entry_price <= 0 or pd.isna(raw_entry_plan["entry_price"]) or pd.isna(raw_stop_loss):
            for column in [
                "entry_trigger_price",
                "entry_price",
                "entry_zone_low",
                "entry_zone_high",
                "stop_loss",
                "take_profit_1",
                "take_profit_2",
                "risk_pct",
                "reward_pct_tp1",
                "reward_pct_tp2",
                "risk_reward_tp1",
                "risk_reward_tp2",
                "risk_per_share",
                "risk_per_lot",
                "theoretical_position_size_lots",
                "theoretical_position_value",
                "theoretical_max_loss_amount",
            ]:
                result[column] = pd.NA
            result["tick_size"] = pd.NA
            result["prices_are_tick_valid"] = False
            result["rounding_applied"] = False
            result["rounding_note"] = "raw_entry_plan_missing_required_price"
            status = "REJECT_INVALID_STOP"
        else:
            result.update(round_trade_plan_prices(result))
            result = recalculate_plan_after_rounding(result, row, config)
            status = validate_trade_status(result, config)

    is_valid = status == "VALID_TRADE_PLAN"
    result["trade_status"] = status
    result["is_plan_valid"] = is_valid
    reason, summary = _status_reason_summary(status)
    result["trade_reason"] = reason
    result["trade_summary"] = summary
    _apply_rounding_reason_summary(result)

    if is_valid:
        result["executable_position_size_lots"] = result["theoretical_position_size_lots"]
        result["position_size_lots"] = result["executable_position_size_lots"]
        result["executable_position_value"] = result["theoretical_position_value"]
        result["executable_max_loss_amount"] = result["theoretical_max_loss_amount"]
    else:
        result["executable_position_size_lots"] = 0
        result["position_size_lots"] = 0
        result["executable_position_value"] = 0.0
        result["executable_max_loss_amount"] = 0.0

    return result


def build_trade_plan_output_frame(results: list[dict[str, Any]]) -> pd.DataFrame:
    output = pd.DataFrame(results)
    for column in STAGE3_OUTPUT_COLUMNS:
        if column not in output.columns:
            output[column] = None

    status_rank = {status: index for index, status in enumerate(TRADE_STATUSES)}
    output["_status_rank"] = output["trade_status"].map(status_rank).fillna(99)
    output = output.sort_values(
        by=["_status_rank", "risk_reward_tp1", "trend_score", "momentum_score"],
        ascending=[True, False, False, False],
        na_position="last",
    )
    return output[STAGE3_OUTPUT_COLUMNS]


def run_stage_3_trade_plan(
    input_path: str | Path,
    output_path: str | Path,
    config: TradePlanConfig | None = None,
) -> pd.DataFrame:
    reset_funnel_counts()
    config = config or TradePlanConfig()
    candidates = load_stage_2_candidates(input_path)
    print(f"Stage 2 rows loaded: {len(candidates)}")
    print(
        "Config: "
        f"capital={config.capital:.0f}, risk_per_trade_pct={min(config.risk_per_trade_pct, config.max_risk_per_trade_pct):.4f}, "
        f"max_stop_loss_pct={config.max_stop_loss_pct:.4f}, tp1_pct={config.tp1_pct:.4f}, tp2_pct={config.tp2_pct:.4f}"
    )

    results = [build_trade_plan_row(row, config) for _, row in candidates.iterrows()]
    output = build_trade_plan_output_frame(results)

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    output.to_csv(path, index=False)

    counts = output["trade_status"].value_counts().to_dict() if not output.empty else {}
    print(f"Total rows input: {len(candidates)}")
    for status in [
        "SKIPPED_NOT_TRADE_CANDIDATE",
        "VALID_TRADE_PLAN",
        "REJECT_STOP_TOO_WIDE",
        "REJECT_BAD_RISK_REWARD_TP1",
        "REJECT_BAD_RISK_REWARD_TP2",
        "WAIT_FOR_VOLUME_CONFIRMATION",
        "WAIT_FOR_REBOUND_CONFIRMATION",
        "WAIT_FOR_ACTIVITY",
        "REJECT_POSITION_TOO_SMALL",
        "INVALID_DATA",
    ]:
        print(f"{status:30s}: {counts.get(status, 0)}")
    print(f"Output saved to: {path}")
    print_funnel_summary_report()
    return output


def run_stage_4_trade_plan(
    stage2_path: str | Path,
    bandarmology_path: str | Path,
    output_path: str | Path,
    config: TradePlanConfig | None = None,
    orderbook_path: str | Path | None = None,
) -> pd.DataFrame:
    reset_funnel_counts()
    config = config or TradePlanConfig()
    candidates = _merge_stage2_bandarmology(stage2_path, bandarmology_path)
    candidates = _merge_orderbook(candidates, orderbook_path)
    print(f"Stage 4 rows loaded: {len(candidates)}")
    print(
        "Config: "
        f"strategy_mode={config.strategy_mode}, "
        f"capital={config.capital:.0f}, risk_per_trade_pct={min(config.risk_per_trade_pct, config.max_risk_per_trade_pct):.4f}, "
        f"tp1_pct={config.tp1_pct:.4f}, tp2_pct={config.tp2_pct:.4f}, max_stop_loss_pct={config.max_stop_loss_pct:.4f}, "
        f"time_stop_days={config.time_stop_days}, force_exit_same_day={config.force_exit_same_day}, "
        f"require_orderbook_confirmation={config.require_orderbook_confirmation}, "
        f"bandarmology_min_score={config.bandarmology_min_score}, allow_trade_without_broker_data={config.allow_trade_without_broker_data}"
    )

    results = [build_trade_plan_row(row, config) for _, row in candidates.iterrows()]
    output = build_trade_plan_output_frame(results)
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    output.to_csv(path, index=False)

    counts = output["trade_status"].value_counts().to_dict() if not output.empty else {}
    broker_confirmed = output["bandarmology_signal"].isin(["STRONG_ACCUMULATION", "MILD_ACCUMULATION"]).sum() if "bandarmology_signal" in output else 0
    rejected_rr = counts.get("REJECT_BAD_RISK_REWARD_TP1", 0) + counts.get("REJECT_BAD_RISK_REWARD_TP2", 0)
    print(f"Total rows: {len(output)}")
    print(f"Rows with broker confirmation: {broker_confirmed}")
    print(f"Valid trade plans: {counts.get('VALID_TRADE_PLAN', 0)}")
    print(f"Draft plans pending orderbook: {counts.get('DRAFT_PLAN_PENDING_ORDERBOOK', 0)}")
    print(f"Skipped no broker data: {counts.get('SKIPPED_NO_BROKER_DATA', 0)}")
    print(f"Skipped low bandarmology score: {counts.get('SKIPPED_LOW_BANDARMOLOGY_SCORE', 0)}")
    print(f"Rejected risk/reward: {rejected_rr}")
    print(f"Output saved to: {path}")
    print_funnel_summary_report()
    return output
