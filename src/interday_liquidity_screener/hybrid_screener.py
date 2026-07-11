from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from .orderbook_filter import is_corp_action_active, is_notation_risky
from .trade_plan import get_idx_tick_size, round_price_to_tick
from .market_data_cache import MarketDataCache, DEFAULT_MARKET_DATA_DB, normalize_ohlcv_frame
from .constants import WatchlistStatus
from .corporate_action_store import CorporateActionStore
from .position_sizing import calculate_position_size
from .scoring import rank_bpjs_candidate
from .strategies import evaluate_strategy
from .hybrid_config import (
    HYBRID_MODES,
    OUTPUT_COLUMNS,
    REQUIRED_STATUSES,
    CapitalProfile,
    FeesConfig,
    HybridScreenerConfig,
    LiquidityConfig,
    OrderbookConfig,
    PriceExtensionConfig,
    RiskPlan,
    RiskConfig,
    SafetyConfig,
    ScoreResult,
    SmartMoneyConfig,
    TechnicalConfig,
    WatchlistConfig,
    config_from_dict,
    load_hybrid_config,
    hybrid_config_hash,
)
from .hybrid_utils import (
    clip_score as _clip,
    first_present as _first,
    safe_bool as _safe_bool,
    safe_float as _safe_float,
    threshold_score as _pct_score,
)
from .enhancements import (
    MarketRegimeFilter,
    MultiBarConfirmation,
    BlackoutFilter,
    AdaptiveTakeProfit,
)


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
    warnings: list[str] = []
    if score is None:
        score = 50.0
        warnings.append("sector_strength_unavailable_neutral_score")
    flags: list[str] = []
    if str(row.get("sector_regime", "")).upper() in {"DOWNTREND", "HARD_DOWNTREND"} or score < 30:
        flags.append("SECTOR_DOWNTREND")
        
    symbol = row.get("symbol")
    if symbol:
        from .commodity_gate import evaluate_commodity_sentiment
        try:
            is_headwind, change_pct, comm_name = evaluate_commodity_sentiment(symbol)
            if is_headwind:
                score -= 20.0
                flags.append("COMMODITY_HEADWIND")
        except Exception:
            pass
            
    return ScoreResult(_clip(score), warnings=tuple(warnings), flags=tuple(flags))


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
        planned_tp1 = _safe_float(_first(row, ["take_profit_1", "tp1_price", "planned_take_profit_1"]))
        planned_tp2 = _safe_float(_first(row, ["take_profit_2", "tp2_price", "planned_take_profit_2"]))
        planned_stop = _safe_float(_first(row, ["stop_loss", "stop_loss_price", "planned_stop"]))
        
        # Reuse Stage 4's executable price plan when available so the hybrid
        # layer scores the same trade instead of inventing a second TP/SL.
        if planned_tp1 is not None and planned_tp1 > entry and planned_stop is not None and 0 < planned_stop < entry:
            tp1 = planned_tp1
            tp2 = planned_tp2 if planned_tp2 is not None and planned_tp2 > tp1 else planned_tp1
            stop_loss = planned_stop
            target_tp_pct = (tp1 - entry) / entry
            stop_loss_pct = (entry - stop_loss) / entry
        elif getattr(config.adaptive_tp, "mode", "adaptive") == "adaptive":
            atr_pct = _safe_float(row.get("atr_pct"), 0.02)
            atr14 = atr_pct * entry
            high_20d = _safe_float(row.get("high_20d"))
            high_60d = _safe_float(row.get("high_60d"))
            atp = AdaptiveTakeProfit(config.adaptive_tp)
            tp1, tp2 = atp.calculate(entry, atr14, high_20d, high_60d)
        else:
            try:
                entry = round_price_to_tick(entry, "nearest")
                tp1 = round_price_to_tick(entry * (1 + target_tp_pct), "floor")
                tp2 = round_price_to_tick(entry * (1 + max(target_tp_pct * 1.5, target_tp_pct + 0.01)), "floor")
            except ValueError:
                tp1 = entry * (1 + target_tp_pct)
                tp2 = entry * (1 + max(target_tp_pct * 1.5, target_tp_pct + 0.01))
                
        if planned_stop is None or not (0 < planned_stop < entry) or planned_tp1 is None or planned_tp1 <= entry:
            try:
                stop_loss = round_price_to_tick(entry * (1 - stop_loss_pct), "floor")
            except ValueError:
                stop_loss = entry * (1 - stop_loss_pct)
            
        # 2. Reconcile cash, capital, stop-risk and liquidity limits before and
        # after IDX lot rounding. Risk is never disabled with the liquidity
        # toggle; the toggle controls only the liquidity constraint.
        avg_value_20d = _safe_float(row.get("avg_value_20d"))
        sizing = calculate_position_size(
            capital=float(profile.capital),
            available_cash=_safe_float(row.get("available_cash"), float(profile.capital)),
            entry_price=entry,
            stop_price=float(stop_loss),
            risk_per_trade_pct=float(config.risk.risk_per_trade_pct),
            max_risk_per_trade_pct=float(config.risk.max_risk_per_trade_pct),
            max_position_pct=float(profile.max_position_pct),
            avg_value_20d=avg_value_20d,
            liquidity_participation_limit_pct=float(config.liquidity_sizer.max_pct_of_avg_value_20d),
            liquidity_sizer_enabled=bool(config.liquidity_sizer.enabled),
            buy_fee_pct=float(fees.buy_fee_pct),
            slippage_pct=float(fees.slippage_pct_default),
            lot_size=int(config.risk.lot_size),
        )
        lot = sizing.planned_lots
        position_value = sizing.actual_position_value
        if sizing.binding_constraint == "LIQUIDITY":
            warnings.append("position_size_capped_by_liquidity")
        if sizing.rejection_reason == "INVALID_STOP_DISTANCE":
            skip_reasons.append("SKIP_INVALID_STOP")
        elif sizing.rejection_reason == "ONE_LOT_RISK_EXCEEDS_MAX":
            skip_reasons.append("SKIP_RISK_LIMIT")
        elif sizing.rejection_reason:
            skip_reasons.append("TOO_EXPENSIVE_FOR_CAPITAL")
        affordable_lot = lot >= 1
        if not affordable_lot:
            skip_reasons.append("TOO_EXPENSIVE_FOR_CAPITAL")
        if entry > float(profile.max_stock_price):
            skip_reasons.append("TOO_EXPENSIVE_FOR_CAPITAL")
        
        estimated_buy_fee = max(position_value * float(fees.buy_fee_pct), float(fees.minimum_buy_fee) if position_value else 0)
        sale_value = lot * float(config.risk.lot_size) * float(tp1)
        estimated_sell_fee = max(sale_value * (float(fees.sell_fee_pct) + float(fees.sell_tax_pct)), float(fees.minimum_sell_fee) if position_value else 0)
        spread_pct = _safe_float(row.get("spread_pct"), float(fees.estimated_spread_pct_default))
        estimated_slippage = (
            position_value * (float(fees.slippage_pct_default) + spread_pct)
            + sale_value * float(fees.slippage_pct_default)
        )
        gross_profit = max(0.0, (float(tp1) - entry) * lot * float(config.risk.lot_size))
        net_profit = gross_profit - estimated_buy_fee - estimated_sell_fee - estimated_slippage
        risk_amount = max(0.0, (entry - float(stop_loss)) * lot * float(config.risk.lot_size))
        reward_amount = gross_profit
        expected_net_return_pct = net_profit / position_value if position_value > 0 else 0.0
        risk_reward_ratio = net_profit / risk_amount if risk_amount > 0 else 0.0
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
            expected_net_return_pct,
            risk_reward_ratio,
            sizing.risk_budget_amount,
            sizing.risk_based_limit,
            sizing.capital_based_limit,
            sizing.liquidity_based_limit,
            sizing.available_cash_limit,
            sizing.binding_constraint,
            sizing.actual_cash_required,
            sizing.actual_risk_pct,
            sizing.capital_utilization_pct,
            sizing.liquidity_participation_pct,
            sizing.estimated_transaction_cost,
            sizing.rejection_reason,
        )
    except Exception as e:
        print(f"Warning: build_risk_plan error for entry={entry}: {e}")
        return RiskPlan(None, None, None, None, target_tp_pct, stop_loss_pct, 0, 0, 0, 0, -1, 0, 0, 0, False, 0, 0, 0, 0, (f"risk_calc_error:{e}",), ("DATA_INSUFFICIENT",))


def stage0_safety(row: dict[str, Any], scores: dict[str, ScoreResult], risk: RiskPlan, config: HybridScreenerConfig, is_blackout: bool = False) -> tuple[list[str], list[str]]:
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
    tradable_val = row.get("tradable")
    is_tradable = True
    if tradable_val is not None and not pd.isna(tradable_val):
        is_tradable = _safe_bool(tradable_val)
    if _safe_bool(row.get("suspended")) or "suspend" in status_text or not is_tradable:
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
    if is_blackout:
        skip_reasons.append("SKIP_BLACKOUT_WINDOW")
    if "DANGER_CHASING" in scores["price_extension"].flags:
        warnings.append("danger_chasing_soft_penalty")
    if "STRONG_DISTRIBUTION" in scores["smart_money"].flags:
        warnings.append("strong_distribution_soft_penalty")
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
    multibar_status: str = "CONFIRMED",
) -> WatchlistStatus:
    if multibar_status == "PENDING_CONFIRMATION":
        return WatchlistStatus.SKIP
    if not row.get("symbol"):
        return WatchlistStatus.DATA_INSUFFICIENT
    if WatchlistStatus.LOW_LIQUIDITY.value in skip_reasons:
        return WatchlistStatus.LOW_LIQUIDITY
    if WatchlistStatus.TOO_EXPENSIVE_FOR_CAPITAL.value in skip_reasons:
        return WatchlistStatus.TOO_EXPENSIVE_FOR_CAPITAL
    if WatchlistStatus.DANGER_CHASING.value in skip_reasons:
        return WatchlistStatus.DANGER_CHASING
    if WatchlistStatus.DISTRIBUTION_WARNING.value in skip_reasons:
        return WatchlistStatus.DISTRIBUTION_WARNING
    # Smart Money Watch Path: strong accumulation but no technical trigger
    if scores["smart_money"].score >= 70 and scores["technical"].score < 60:
        if scores["technical"].score >= 45:
            return WatchlistStatus.READY_SOON
        return WatchlistStatus.EARLY_WATCH

    hard_safety = [reason for reason in skip_reasons if reason.startswith("SKIP_")]
    if hard_safety:
        return WatchlistStatus.SKIP
    has_orderbook = orderbook_available(row)
    orderbook_flags = set(scores["orderbook"].flags)
    risk_flags = set(risk.skip_reasons)
    if mode == "smart_money_first":
        if scores["smart_money"].score >= 70 and scores["price_extension"].score >= 70 and scores["technical"].score >= 55:
            return WatchlistStatus.READY_SOON
        if scores["smart_money"].score >= 60 and scores["price_extension"].score >= 65:
            return WatchlistStatus.EARLY_WATCH
        return WatchlistStatus.SKIP
    if mode == "weekend_preparation":
        if scores["smart_money"].score >= 70 and scores["technical"].score >= 60 and risk.risk_plan_score >= 55:
            return WatchlistStatus.READY_SOON
        if scores["smart_money"].score >= 60 or flow_source in {"safe_execution", "smart_money_discovery", "both"}:
            return WatchlistStatus.EARLY_WATCH
        return WatchlistStatus.SKIP
    if flow_source == "none":
        return WatchlistStatus.SKIP
    if WatchlistStatus.NET_PROFIT_NOT_WORTH_IT.value in risk_flags:
        return WatchlistStatus.NET_PROFIT_NOT_WORTH_IT
    if WatchlistStatus.RISK_REWARD_BAD.value in risk_flags:
        return WatchlistStatus.RISK_REWARD_BAD
    if mode == "bpjs_live":
        if not has_orderbook:
            return WatchlistStatus.NEED_ORDERBOOK
        if WatchlistStatus.ORDERBOOK_REJECT.value in orderbook_flags:
            return WatchlistStatus.ORDERBOOK_REJECT
        if WatchlistStatus.ORDERBOOK_WEAK.value in orderbook_flags or scores["orderbook"].score < 55:
            return WatchlistStatus.ORDERBOOK_WEAK
        return WatchlistStatus.EXECUTION_READY
    if has_orderbook:
        if WatchlistStatus.ORDERBOOK_REJECT.value in orderbook_flags:
            return WatchlistStatus.ORDERBOOK_REJECT
        if WatchlistStatus.ORDERBOOK_WEAK.value in orderbook_flags or scores["orderbook"].score < 45:
            return WatchlistStatus.ORDERBOOK_WEAK
        return WatchlistStatus.EXECUTION_READY
    if mode == "normal_execution":
        return WatchlistStatus.EXECUTION_DRAFT
    return WatchlistStatus.EXECUTION_CANDIDATE


def build_explanation(status: str, scores: dict[str, ScoreResult], risk: RiskPlan, flow_source: str, warnings: list[str], skip_reasons: list[str]) -> str:
    if status == WatchlistStatus.READY_SOON:
        return "READY_SOON because smart money and technical structure are improving, price is not extended, but execution still needs live validation."
    if status == WatchlistStatus.EARLY_WATCH:
        return "EARLY_WATCH because the stock is worth monitoring, but the setup is not yet an execution signal."
    if status == WatchlistStatus.NEED_ORDERBOOK:
        return "NEED_ORDERBOOK because BPJS live mode requires a live orderbook before any execution-ready status is allowed."
    if status == WatchlistStatus.EXECUTION_DRAFT:
        return "EXECUTION_DRAFT because pre-market scores are acceptable, but live orderbook validation has not been supplied."
    if status == WatchlistStatus.EXECUTION_CANDIDATE:
        return "EXECUTION_CANDIDATE because liquidity, setup, smart money, extension, and risk gates are acceptable before final live validation."
    if status == WatchlistStatus.EXECUTION_READY:
        return "EXECUTION_READY because the hybrid candidate passed scoring, risk, net-profit, and live orderbook gates. This is not an order instruction."
    if status == WatchlistStatus.DANGER_CHASING:
        return "DANGER_CHASING because price extension is above configured safety thresholds."
    if status == WatchlistStatus.DISTRIBUTION_WARNING:
        return "DISTRIBUTION_WARNING because broker-flow distribution risk is too strong for a clean watchlist candidate."
    if status == WatchlistStatus.ORDERBOOK_REJECT:
        return "ORDERBOOK_REJECT because spread, offer wall, tradability, or other orderbook safety gates failed."
    if status == WatchlistStatus.ORDERBOOK_WEAK:
        return "ORDERBOOK_WEAK because live depth, spread, or frequency is not supportive enough for micro execution."
    if status == WatchlistStatus.NET_PROFIT_NOT_WORTH_IT:
        return "NET_PROFIT_NOT_WORTH_IT because expected TP is too small after estimated fees and slippage."
    if status == WatchlistStatus.RISK_REWARD_BAD:
        return "RISK_REWARD_BAD because the configured stop and target do not meet minimum R:R."
    if status == WatchlistStatus.TOO_EXPENSIVE_FOR_CAPITAL:
        return "TOO_EXPENSIVE_FOR_CAPITAL because one lot or the stock price exceeds the selected capital profile."
    if status == WatchlistStatus.LOW_LIQUIDITY:
        return "LOW_LIQUIDITY because average value or frequency is below configured execution thresholds."
    if status == WatchlistStatus.DATA_INSUFFICIENT:
        return "DATA_INSUFFICIENT because required symbol or price data is missing."
    if status == WatchlistStatus.COMMODITY_HEADWIND:
        return "COMMODITY_HEADWIND because the underlying global commodity price is down heavily, indicating negative sector sentiment."
    reason_text = ", ".join(skip_reasons[:3]) if skip_reasons else "scores did not meet the watchlist gates"
    warning_text = f" Warnings: {', '.join(warnings[:4])}." if warnings else ""
    return f"SKIP because {reason_text}.{warning_text}"


def assess_data_quality(row: dict[str, Any]) -> tuple[float, list[str], list[str], float, str]:
    """Return coverage and confidence without treating optional data as a gate."""

    required = {
        "symbol": bool(row.get("symbol")),
        "close": _safe_float(row.get("close")) is not None,
        "avg_value_20d": _safe_float(row.get("avg_value_20d")) is not None,
    }
    optional = {
        "broker_flow": _safe_bool(row.get("broker_activity_available"))
        or _safe_float(row.get("accumulation_window_count")) is not None,
        "sector_strength": _safe_float(row.get("sector_strength_score")) is not None,
        "orderbook": orderbook_available(row),
        "market_breadth": _safe_float(row.get("market_breadth_score")) is not None,
        "tp_probability_estimate": _safe_float(row.get("estimated_tp_probability")) is not None,
    }
    missing_required = [name for name, available in required.items() if not available]
    missing_optional = [name for name, available in optional.items() if not available]
    available_count = sum(required.values()) + sum(optional.values())
    coverage = 100.0 * available_count / (len(required) + len(optional))
    data_quality = max(0.0, coverage - 20.0 * len(missing_required))
    confidence = "HIGH" if data_quality >= 85 else "MEDIUM" if data_quality >= 65 else "LOW"
    return coverage, missing_required, missing_optional, data_quality, confidence


def to_funnel_status(status: WatchlistStatus) -> WatchlistStatus:
    """Map granular compatibility statuses to the canonical BPJS funnel."""

    if status == WatchlistStatus.EXECUTION_READY:
        return WatchlistStatus.EXECUTION_READY
    if status in {WatchlistStatus.READY_SOON, WatchlistStatus.NEED_ORDERBOOK, WatchlistStatus.EXECUTION_DRAFT, WatchlistStatus.EXECUTION_CANDIDATE}:
        return WatchlistStatus.READY_SOON
    if status in {WatchlistStatus.EARLY_WATCH, WatchlistStatus.ORDERBOOK_WEAK}:
        return WatchlistStatus.WATCHLIST
    return WatchlistStatus.REJECT


def build_output_row(
    row: dict[str, Any],
    mode: str,
    capital_profile: str,
    config: HybridScreenerConfig,
    ticker_history: pd.DataFrame | None = None,
    blackout_events: dict[str, list[pd.Timestamp]] | None = None,
    corporate_action_store: CorporateActionStore | None = None,
) -> dict[str, Any]:
    normalized = normalize_candidate_row(row)
    
    # 1. Evaluate Blackout Filter
    is_blackout = False
    if config.blackout.enabled and (blackout_events is not None or corporate_action_store is not None):
        ticker = str(normalized.get("symbol", row.get("ticker", ""))).replace(".JK", "")
        decision_date = pd.Timestamp(normalized.get("date")) if normalized.get("date") else None
        if ticker and decision_date:
            flt = BlackoutFilter(config.blackout)
            known_events = dict(blackout_events or {})
            if corporate_action_store is not None:
                known_events[ticker] = corporate_action_store.blackout_dates_as_of(decision_date, ticker)
            is_blackout = flt.is_in_blackout(ticker, decision_date, known_events)
            
    # 2. Evaluate Multi-Bar Confirmation
    multibar_status = "CONFIRMED"
    is_swing = mode in {"normal_execution", "interday_swing", "hybrid_dual_flow", "weekend_preparation", "smart_money_first"}
    is_bpjs = mode == "bpjs_live"
    multibar_enabled = (
        (is_swing and config.multibar_enabled_for_swing)
        or (is_bpjs and config.multibar_enabled_for_bpjs)
    )
    if multibar_enabled and ticker_history is not None:
        setup = normalized.get("entry_setup", normalized.get("technical_context", ""))
        if setup:
            confirm = MultiBarConfirmation(config.multibar_confirm)
            decision_date = pd.Timestamp(normalized.get("date")) if normalized.get("date") else None
            multibar_status = confirm.get_confirmation_status(setup, ticker_history, decision_date)

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
    strategy = evaluate_strategy(normalized)
    flow_source = determine_flow_source(scores, risk)
    safety_skip, safety_warnings = stage0_safety(normalized, scores, risk, config, is_blackout=is_blackout)
    warnings = list(dict.fromkeys([*safety_warnings, *risk.warnings, *[warning for score in scores.values() for warning in score.warnings]]))
    if is_blackout:
        warnings.append("inside_corporate_action_blackout_window")
    skip_reasons = list(dict.fromkeys([*safety_skip, *risk.skip_reasons]))
    status = determine_status(normalized, scores, risk, skip_reasons, flow_source, mode, multibar_status=multibar_status)
    coverage, missing_required, missing_optional, data_quality, confidence = assess_data_quality(normalized)
    if missing_required:
        status = WatchlistStatus.DATA_INSUFFICIENT
        skip_reasons.append("SKIP_REQUIRED_DATA")
    market_context_score = _combined_market_sector(float(scores["market_regime"].score), float(scores["sector_strength"].score))
    ranking = rank_bpjs_candidate(
        technical=float(scores["technical"].score), smart_money=float(scores["smart_money"].score),
        price_extension=float(scores["price_extension"].score), market_context=market_context_score,
        liquidity=float(scores["liquidity"].score), orderbook=float(scores["orderbook"].score),
        net_profit_feasibility=float(risk.net_profit_feasibility_score),
        risk_feasibility=float(risk.risk_plan_score), data_quality=data_quality,
        estimated_tp_probability=_safe_float(normalized.get("estimated_tp_probability")),
    )
    if mode == "bpjs_live":
        final_score = ranking.ranking_score
    else:
        confidence_multiplier = 0.70 + (0.30 * coverage / 100.0)
        final_score = round(calculate_final_score(scores, risk, mode, config) * confidence_multiplier, 2)

    # P11 Insider activity score adjustment
    insider_adj = normalized.get("_insider_score_adjustment", 0)
    if insider_adj:
        final_score = round(final_score + float(insider_adj), 2)

    # P12 Ex-date blackout: force SKIP if ticker is on/near ex-date
    if normalized.get("_exdate_blocked"):
        status = WatchlistStatus.SKIP
        final_score = max(0, final_score - 30)

    if strategy.status_cap == WatchlistStatus.READY_SOON and status == WatchlistStatus.EXECUTION_READY:
        status = WatchlistStatus.READY_SOON
    elif strategy.status_cap == WatchlistStatus.WATCHLIST and status in {
        WatchlistStatus.EXECUTION_READY, WatchlistStatus.EXECUTION_CANDIDATE,
        WatchlistStatus.EXECUTION_DRAFT, WatchlistStatus.READY_SOON,
    }:
        status = WatchlistStatus.EARLY_WATCH
    funnel_status = to_funnel_status(status)
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
    explanation = build_explanation(status, scores, risk, flow_source, warnings, skip_reasons)
    decision_timestamp = normalized.get("decision_timestamp", normalized.get("date"))
    data_cutoff_timestamp = normalized.get("data_cutoff_timestamp", decision_timestamp)
    output = {
        "symbol": normalized.get("symbol"),
        "name": normalized.get("name"),
        "date": normalized.get("date"),
        "mode": mode,
        "decision_timestamp": decision_timestamp,
        "data_cutoff_timestamp": data_cutoff_timestamp,
        "feature_version": normalized.get("feature_version", "technical-prior-v1"),
        "strategy_version": normalized.get("strategy_version", "hybrid-p2-v1"),
        "config_hash": normalized.get("config_hash", hybrid_config_hash(config)),
        "code_commit_hash": normalized.get("code_commit_hash", "UNKNOWN"),
        "universe_version": normalized.get("universe_version", "UNKNOWN"),
        "raw_input_refs": normalized.get("raw_input_refs", ""),
        "broker_snapshot_timestamp": normalized.get("broker_snapshot_timestamp"),
        "orderbook_snapshot_timestamp": normalized.get("orderbook_snapshot_timestamp"),
        "final_status": status,
        "funnel_status": funnel_status,
        "is_primary_candidate": False,
        "daily_decision": WatchlistStatus.NO_TRADE,
        "final_score": final_score,
        "ranking_score": ranking.ranking_score,
        "alpha_score": ranking.alpha_score,
        "execution_quality_score": ranking.execution_quality_score,
        "risk_feasibility_score": ranking.risk_feasibility_score,
        "confidence_score": ranking.confidence_score,
        "rank": None,
        "flow_source": flow_source,
        "strategy_name": strategy.definition.name,
        "strategy_eligible": strategy.eligible,
        "entry_trigger_touched": strategy.trigger_touched,
        "strategy_status_cap": strategy.status_cap,
        "strategy_reasons": ";".join(strategy.reasons),
        "estimated_tp_probability": normalized.get("estimated_tp_probability"),
        "liquidity_score": round(float(scores["liquidity"].score), 2),
        "technical_score": round(float(scores["technical"].score), 2),
        "smart_money_score": round(float(scores["smart_money"].score), 2),
        "price_extension_score": round(float(scores["price_extension"].score), 2),
        "market_regime_score": round(float(scores["market_regime"].score), 2),
        "ihsg_trend_regime": normalized.get("ihsg_trend_regime", normalized.get("market_regime")),
        "market_regime_source": normalized.get("market_regime_source", "IHSG_TREND_FALLBACK"),
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
        "planned_entry": risk.entry_price,
        "actual_entry": normalized.get("actual_entry"),
        "tp1_price": risk.tp1_price,
        "tp2_price": risk.tp2_price,
        "stop_loss_price": risk.stop_loss_price,
        "planned_stop": risk.stop_loss_price,
        "actual_stop": normalized.get("actual_stop"),
        "planned_target": risk.tp1_price,
        "actual_lots": normalized.get("actual_lots", 0),
        "target_tp_pct": risk.target_tp_pct,
        "stop_loss_pct": risk.stop_loss_pct,
        "estimated_buy_fee": risk.estimated_buy_fee,
        "estimated_sell_fee": risk.estimated_sell_fee,
        "estimated_slippage": risk.estimated_slippage,
        "gross_profit": risk.gross_profit,
        "net_profit_after_fee": risk.net_profit_after_fee,
        "expected_net_return_pct": risk.expected_net_return_pct,
        "net_risk_reward_ratio": risk.net_risk_reward_ratio,
        "risk_amount": risk.risk_amount,
        "reward_amount": risk.reward_amount,
        "risk_reward_ratio": risk.risk_reward_ratio,
        "affordable_lot": risk.affordable_lot,
        "position_value": risk.position_value,
        "risk_budget_amount": risk.risk_budget_amount,
        "risk_based_limit": risk.risk_based_limit,
        "capital_based_limit": risk.capital_based_limit,
        "liquidity_based_limit": risk.liquidity_based_limit,
        "available_cash_limit": risk.available_cash_limit,
        "binding_constraint": risk.binding_constraint,
        "planned_lots": risk.lot,
        "actual_position_value": risk.position_value,
        "actual_cash_required": risk.actual_cash_required,
        "actual_risk_amount": risk.risk_amount,
        "actual_risk_pct": risk.actual_risk_pct,
        "capital_utilization_pct": risk.capital_utilization_pct,
        "liquidity_participation_pct": risk.liquidity_participation_pct,
        "estimated_transaction_cost": risk.estimated_transaction_cost,
        "rejection_reason": risk.rejection_reason,
        "signal_reason": explanation,
        "status_transition": f"DISCOVERED->{status.value}",
        "score_coverage_pct": round(coverage, 2),
        "missing_required_features": ";".join(missing_required),
        "missing_optional_features": ";".join(missing_optional),
        "data_quality_score": round(data_quality, 2),
        "confidence_level": confidence,
        "capital_profile": capital_profile,
        "warnings": ";".join(warnings),
        "skip_reasons": ";".join(skip_reasons),
        "explanation": explanation,
    }
    for window in [1, 3, 5, 10, 20]:
        output[f"broker_net_buy_{window}d"] = normalized.get(f"broker_net_buy_{window}d")
    return output


def load_ihsg_data(cache_db: Path) -> pd.DataFrame | None:
    try:
        cache = MarketDataCache(cache_db)
        df = cache.load_ohlcv("^JKSE")
        if df.empty:
            import yfinance as yf
            ticker = yf.Ticker("^JKSE")
            df = ticker.history(period="1y")
            df = normalize_ohlcv_frame(df, "^JKSE")
            if not df.empty:
                cache.save_ohlcv("^JKSE", df)
        return df
    except Exception as e:
        print(f"Warning: Failed to load IHSG data: {e}")
        return None


def detect_corporate_action_dates(df: pd.DataFrame) -> list[pd.Timestamp]:
    if df is None or df.empty or "adjusted_close" not in df.columns or "close" not in df.columns:
        return []
    close = pd.to_numeric(df["close"], errors="coerce")
    adjusted = pd.to_numeric(df["adjusted_close"], errors="coerce")
    valid = close.notna() & adjusted.notna() & (close > 0)
    if not valid.any():
        return []
    ratio = adjusted / close
    ratio_diff = ratio.diff().abs()
    event_dates = ratio_diff[ratio_diff > 0.01].index.tolist()
    return [pd.Timestamp(d) for d in event_dates]


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

    decision_date = pd.Timestamp(date) if date else None
    db_path = config.market_data_db or DEFAULT_MARKET_DATA_DB

    # P11 Insider activity: fetch once per run, inject adjustments into candidates
    insider_activity: dict[str, Any] = {}
    try:
        from .insider_tracker import fetch_insider_transactions, analyze_insider_activity
        insider_txs = fetch_insider_transactions(limit=50, use_cache=True)
        if insider_txs:
            insider_activity = analyze_insider_activity(insider_txs, lookback_days=7)
            # Inject _insider_score_adjustment into candidate rows
            if "symbol" in candidates.columns or "ticker" in candidates.columns:
                tkr_col = "symbol" if "symbol" in candidates.columns else "ticker"
                candidates = candidates.copy()
                candidates["_insider_score_adjustment"] = candidates[tkr_col].apply(
                    lambda t: insider_activity.get(str(t).replace(".JK", "").upper(), {}).get("score_adjustment", 0)
                )
    except Exception:
        pass  # Non-critical — insider data is a boost, not a gate

    # P12 Dividend ex-date blackout: block tickers on/near ex-date
    exdate_blocked_tickers: set[str] = set()
    try:
        from .dividend_tracker import fetch_upcoming_dividends, get_exdate_tickers
        from datetime import date as _date_type
        dividend_events = fetch_upcoming_dividends(use_cache=True)
        today_date = _date_type.today()
        # Block tickers whose ex-date is today or tomorrow
        exdate_blocked_tickers = set(get_exdate_tickers(dividend_events, today_date))
        tomorrow = today_date + timedelta(days=1)
        exdate_blocked_tickers.update(get_exdate_tickers(dividend_events, tomorrow))
        if exdate_blocked_tickers:
            if "symbol" in candidates.columns or "ticker" in candidates.columns:
                tkr_col = "symbol" if "symbol" in candidates.columns else "ticker"
                candidates["_exdate_blocked"] = candidates[tkr_col].apply(
                    lambda t: str(t).replace(".JK", "").upper() in exdate_blocked_tickers
                )
    except Exception:
        pass  # Non-critical

    # 1. Evaluate Market Regime once per run
    regime = "RISK_ON"
    regime_score = 50.0
    if config.market_regime.enabled or config.safety.hard_market_regime_risk_off:
        ihsg_df = load_ihsg_data(db_path)
        flt = MarketRegimeFilter(config.market_regime)
        res = flt.evaluate(ihsg_df, decision_date=decision_date)
        regime = res.regime
        if regime == "RISK_ON":
            regime_score = 80.0
        elif regime == "RISK_OFF":
            regime_score = 20.0
        else:
            regime_score = 50.0

    # 2. Preload Ticker Histories & Blackout Events for fast processing
    ticker_histories = {}
    blackout_events = {}
    corporate_action_store = None
    corporate_action_path = Path(config.corporate_action_db)
    if corporate_action_path.exists():
        corporate_action_store = CorporateActionStore(db_path=corporate_action_path)
    cache = MarketDataCache(db_path)
    from .technical import calculate_technical_features

    for _, row in candidates.iterrows():
        ticker = str(row.get("symbol", row.get("ticker", ""))).replace(".JK", "")
        if not ticker:
            continue
        try:
            df = cache.load_ohlcv(ticker + ".JK")
            if df.empty:
                df = cache.load_ohlcv(ticker)
            if not df.empty:
                features = calculate_technical_features(df)
                ticker_histories[ticker] = features
                # Do not infer historical knowledge from adjusted/raw ratios.
                # Blackout events must come from an announcement-timestamped
                # CorporateActionStore query performed as-of the decision time.
        except Exception as e:
            print(f"Warning: Failed preloading cache for {ticker}: {e}")

    rows = []
    for _, row in candidates.iterrows():
        try:
            ticker = str(row.get("symbol", row.get("ticker", ""))).replace(".JK", "")
            history = ticker_histories.get(ticker)
            
            # Inject evaluated market regime to candidates dictionary representation
            row_dict = row.to_dict()
            row_dict["market_regime"] = regime
            row_dict["market_regime_score"] = regime_score
            row_dict["ihsg_trend_regime"] = regime
            row_dict["market_regime_source"] = "IHSG_TREND_FALLBACK"

            output = build_output_row(
                row_dict,
                mode,
                capital_profile,
                config,
                ticker_history=history,
                blackout_events=blackout_events,
                corporate_action_store=corporate_action_store,
            )
            if date:
                output["date"] = date
            rows.append(output)
        except Exception as e:
            ticker = row.get("ticker", row.get("symbol", "unknown"))
            print(f"Warning: Skipping ticker {ticker} in hybrid watchlist due to error: {e}")
            continue

    if not rows:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)

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
    if mode == "bpjs_live":
        caps = {
            WatchlistStatus.WATCHLIST.value: config.watchlist.max_watchlist,
            WatchlistStatus.READY_SOON.value: config.watchlist.max_ready_soon,
            WatchlistStatus.EXECUTION_READY.value: config.watchlist.max_execution_ready,
        }
        keep_indices: list[int] = []
        for funnel, group in output_df.groupby("funnel_status", sort=False):
            cap = caps.get(str(funnel), len(group))
            keep_indices.extend(group.head(cap).index.tolist())
        output_df = output_df.loc[output_df.index.isin(keep_indices)].copy()
        execution_ready = output_df[output_df["funnel_status"] == WatchlistStatus.EXECUTION_READY]
        if not execution_ready.empty:
            output_df["daily_decision"] = WatchlistStatus.EXECUTION_READY
            output_df.loc[execution_ready.index[0], "is_primary_candidate"] = True
        else:
            output_df["daily_decision"] = WatchlistStatus.NO_TRADE
    if max_candidates is None:
        max_candidates = config.watchlist.max_candidates_bpjs if mode == "bpjs_live" else config.watchlist.max_candidates_default

    # P9 Sector diversification guard: iteratively demote over-concentrated sectors
    from .enhancements.sector_correlation import SectorCorrelationGuard, prefetch_sectors
    sector_guard = SectorCorrelationGuard(enabled=True)
    if not output_df.empty and "symbol" in output_df.columns:
        # Prefetch sectors for all candidates ONCE before iterative loop
        all_symbols = output_df["symbol"].tolist()
        prefetch_sectors(all_symbols)

        # Iterate up to 3 times to ensure diversification converges
        for _pass in range(3):
            top_symbols = output_df["symbol"].tolist()[:max_candidates * 2] if max_candidates else output_df["symbol"].tolist()
            sector_result = sector_guard.sector_check(top_symbols)
            if sector_result["diversified"]:
                break
            # Demote excess tickers from over-represented sectors
            for violation in sector_result["violations"]:
                for remove_ticker in violation.get("remove_suggestion", []):
                    mask = output_df["symbol"] == remove_ticker
                    if mask.any():
                        output_df.loc[mask, "final_score"] = output_df.loc[mask, "final_score"] - 5.0
            # Re-sort after demotion
            output_df = output_df.sort_values("final_score", ascending=False).copy()

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
    enable_market_regime: bool | None = None,
    enable_multibar_confirm: bool | None = None,
    enable_adaptive_tp: bool | None = None,
    enable_liquidity_sizer: bool | None = None,
    enable_blackout: bool | None = None,
    capital: float | None = None,
    risk_per_trade_pct: float | None = None,
    max_position_pct: float | None = None,
) -> pd.DataFrame:
    config = load_hybrid_config(config_path)
    
    # Apply runtime overrides if passed
    from dataclasses import replace
    if capital is not None or max_position_pct is not None:
        profile = config.capital_profiles[capital_profile]
        profile = replace(
            profile,
            capital=float(capital) if capital is not None else profile.capital,
            max_position_pct=float(max_position_pct) if max_position_pct is not None else profile.max_position_pct,
            max_stock_price=float(capital) / 100.0 if capital is not None else profile.max_stock_price,
        )
        profiles = dict(config.capital_profiles)
        profiles[capital_profile] = profile
        config = replace(config, capital_profiles=profiles)
    if risk_per_trade_pct is not None:
        config = replace(
            config,
            risk=replace(
                config.risk,
                risk_per_trade_pct=float(risk_per_trade_pct),
                max_risk_per_trade_pct=float(risk_per_trade_pct),
            ),
        )
    if enable_market_regime is not None:
        config = replace(
            config,
            market_regime=replace(config.market_regime, enabled=enable_market_regime),
        )
    if enable_multibar_confirm is not None:
        config = replace(
            config,
            multibar_enabled_for_swing=enable_multibar_confirm,
            multibar_enabled_for_bpjs=enable_multibar_confirm,
        )
    if enable_adaptive_tp is not None:
        tp_mode = "adaptive" if enable_adaptive_tp else "fixed"
        config = replace(config, adaptive_tp=replace(config.adaptive_tp, mode=tp_mode))
    if enable_liquidity_sizer is not None:
        config = replace(
            config,
            liquidity_sizer=replace(config.liquidity_sizer, enabled=enable_liquidity_sizer),
        )
    if enable_blackout is not None:
        config = replace(config, blackout=replace(config.blackout, enabled=enable_blackout))

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
