from __future__ import annotations

from typing import Any

from .config import ScreenerConfig

HIGH_LIQUIDITY = "HIGH_LIQUIDITY"
GOOD_LIQUIDITY = "GOOD_LIQUIDITY"
MEDIUM_LIQUIDITY = "MEDIUM_LIQUIDITY"
LOW_LIQUIDITY = "LOW_LIQUIDITY"
ILLIQUID = "ILLIQUID"

VERY_ACTIVE = "VERY_ACTIVE"
ACTIVE = "ACTIVE"
NORMAL_TO_QUIET = "NORMAL_TO_QUIET"
QUIET = "QUIET"

STRONG_WATCH = "STRONG_WATCH"
WATCH = "WATCH"
AVOID_FOR_NOW = "AVOID_FOR_NOW"
INVALID_DATA = "INVALID_DATA"


def _value(row: dict[str, Any], key: str, default: float = 0.0) -> float:
    value = row.get(key)
    return float(value) if value is not None else default


def calculate_liquidity_score(row: dict[str, Any], config: ScreenerConfig) -> int:
    """Score absolute liquidity only, independent from today's trading setup."""
    if not row.get("is_data_valid") or _value(row, "data_points") < 20:
        return 0

    avg_value_20d = _value(row, "avg_value_20d")
    median_value_20d = _value(row, "median_value_20d")
    active_days_20d = _value(row, "active_days_20d")
    zero_volume_days_20d = _value(row, "zero_volume_days_20d")
    consistency = _value(row, "value_consistency_ratio")

    avg_value_score = min(avg_value_20d / config.min_avg_value_20d, 1.0) * 35
    median_value_score = min(median_value_20d / config.min_median_value_20d, 1.0) * 30
    active_days_score = min(active_days_20d / 20, 1.0) * 20
    zero_volume_score = max(0.0, 1.0 - zero_volume_days_20d / max(config.max_zero_volume_days_20d + 1, 1)) * 10
    consistency_score = min(consistency / 0.60, 1.0) * 5

    total = avg_value_score + median_value_score + active_days_score + zero_volume_score + consistency_score
    return max(0, min(100, int(round(total))))


def classify_liquidity_bucket(score: int) -> str:
    if score >= 85:
        return HIGH_LIQUIDITY
    if score >= 65:
        return GOOD_LIQUIDITY
    if score >= 45:
        return MEDIUM_LIQUIDITY
    if score >= 25:
        return LOW_LIQUIDITY
    return ILLIQUID


def classify_relative_activity(row: dict[str, Any]) -> str:
    value_ratio = _value(row, "value_ratio")
    volume_ratio = _value(row, "volume_ratio")

    if value_ratio >= 1.5 and volume_ratio >= 1.5:
        return VERY_ACTIVE
    if value_ratio >= 1.0 and volume_ratio >= 1.0:
        return ACTIVE
    if value_ratio >= 0.6 or volume_ratio >= 0.6:
        return NORMAL_TO_QUIET
    return QUIET


def _check_daily_gates(row: dict[str, Any], config: ScreenerConfig) -> list[str]:
    """Check daily activity gates that determine trade candidacy but not absolute liquidity.

    Returns a list of gate failure reasons, or empty list if all gates pass.
    """
    failures: list[str] = []

    value_est = row.get("value_est")
    if value_est is not None and value_est < config.min_value:
        failures.append("latest_value_below_min_value")

    volume_ratio = row.get("volume_ratio")
    if volume_ratio is not None and volume_ratio < config.min_volume_ratio:
        failures.append("volume_ratio_below_min_volume_ratio")

    return_5d = row.get("return_5d")
    if return_5d is not None and return_5d > config.max_return_5d:
        failures.append("return_5d_above_max_return_5d")

    return failures


def classify_trade_candidate(row: dict[str, Any], config: ScreenerConfig | None = None) -> str:
    if not row.get("is_data_valid") or _value(row, "data_points") < 20:
        return INVALID_DATA

    liquidity_bucket = row.get("liquidity_bucket")
    is_liquid = liquidity_bucket in {HIGH_LIQUIDITY, GOOD_LIQUIDITY}
    if not is_liquid:
        return AVOID_FOR_NOW

    # Check config-based daily gates
    if config is not None:
        gate_failures = _check_daily_gates(row, config)
        if gate_failures:
            return AVOID_FOR_NOW

    return_1d = row.get("return_1d")
    return_3d = row.get("return_3d")
    return_5d = row.get("return_5d")
    return_20d = row.get("return_20d")
    close_location = _value(row, "close_location", 0.5)
    value_ratio = _value(row, "value_ratio")
    volume_ratio = _value(row, "volume_ratio")
    distance_to_high = row.get("distance_to_20d_high")
    distance_from_low = row.get("distance_from_20d_low")

    positive_1d = return_1d is not None and return_1d > 0
    confirmed_activity = value_ratio >= 1.0 or volume_ratio >= 1.0
    near_low_rebound_area = distance_from_low is not None and distance_from_low <= 0.08
    too_extended = distance_to_high is not None and distance_to_high < 0.005
    weak_multi_day = any(
        value is not None and value < -0.03 for value in [return_3d, return_5d, return_20d]
    )

    if close_location < 0.4:
        return AVOID_FOR_NOW

    if positive_1d and close_location >= 0.6 and value_ratio >= 1.0 and not too_extended:
        return STRONG_WATCH

    if is_liquid and positive_1d and close_location >= 0.6 and confirmed_activity:
        return STRONG_WATCH

    if positive_1d or near_low_rebound_area:
        return WATCH

    if weak_multi_day:
        return AVOID_FOR_NOW

    return AVOID_FOR_NOW


def build_reason(row: dict[str, Any], config: ScreenerConfig | None = None) -> str:
    if not row.get("is_data_valid") or _value(row, "data_points") < 20:
        source_reason = row.get("reason")
        if source_reason and source_reason not in {"", "invalid_data"}:
            normalized = str(source_reason).replace(" ", "_").replace(":", "").lower()
            return f"invalid_data_{normalized}"
        return "invalid_data_insufficient_history"

    liquidity_bucket = row.get("liquidity_bucket")
    activity_bucket = row.get("relative_activity_bucket")
    trade_bucket = row.get("trade_candidate_bucket")
    return_1d = row.get("return_1d")
    return_3d = row.get("return_3d")
    return_5d = row.get("return_5d")
    close_location = _value(row, "close_location", 0.5)

    high_liquidity = liquidity_bucket in {HIGH_LIQUIDITY, GOOD_LIQUIDITY}
    quiet = activity_bucket in {NORMAL_TO_QUIET, QUIET}
    positive_rebound = return_1d is not None and return_1d > 0
    weak_momentum = any(value is not None and value < 0 for value in [return_3d, return_5d])

    if not high_liquidity:
        return "low_liquidity_or_inconsistent_trading"

    # Check config-based daily gates and return specific reasons
    if config is not None and high_liquidity:
        gate_failures = _check_daily_gates(row, config)
        if gate_failures:
            return gate_failures[0]

    if trade_bucket == STRONG_WATCH and positive_rebound:
        return "high_liquidity_with_positive_rebound"
    if close_location < 0.4:
        return "high_liquidity_but_closing_near_daily_low"
    if quiet:
        return "high_absolute_liquidity_but_quiet_today"
    if weak_momentum:
        return "high_liquidity_but_weak_momentum"
    return "high_liquidity_neutral_setup"


def build_signal_summary(row: dict[str, Any], config: ScreenerConfig | None = None) -> str:
    if not row.get("is_data_valid") or _value(row, "data_points") < 20:
        return "Invalid or insufficient data. Skip this ticker until a full 20-day history is available."

    liquidity_bucket = row.get("liquidity_bucket")
    activity_bucket = row.get("relative_activity_bucket")
    trade_bucket = row.get("trade_candidate_bucket")
    return_1d = row.get("return_1d")
    return_3d = row.get("return_3d")
    return_5d = row.get("return_5d")
    close_location = _value(row, "close_location", 0.5)

    liquid_text = "Very liquid stock" if liquidity_bucket == HIGH_LIQUIDITY else "Liquid stock"

    # Check config-based daily gates and return descriptive summaries
    if config is not None and liquidity_bucket in {HIGH_LIQUIDITY, GOOD_LIQUIDITY}:
        gate_failures = _check_daily_gates(row, config)
        if gate_failures:
            parts = []
            if "latest_value_below_min_value" in gate_failures:
                parts.append("today's transaction value is below the minimum threshold")
            if "volume_ratio_below_min_volume_ratio" in gate_failures:
                parts.append("today's volume ratio is below the minimum activity threshold")
            if "return_5d_above_max_return_5d" in gate_failures:
                parts.append("5-day return is too high (avoid chasing)")
            return f"{liquid_text}, but {'; '.join(parts)}. Not eligible as trade candidate today."

    if trade_bucket == STRONG_WATCH:
        if any(value is not None and value < 0 for value in [return_3d, return_5d]):
            return f"{liquid_text} with positive daily rebound, but still weak over 3-5 days."
        return f"{liquid_text} with positive daily rebound and confirmed activity. Watch for a valid entry setup."

    if close_location < 0.4:
        return f"{liquid_text} but closing near daily low; avoid entry for now."

    if activity_bucket in {NORMAL_TO_QUIET, QUIET}:
        return f"{liquid_text}, but today's activity is below its 20-day average. Not a confirmed breakout yet."

    if return_1d is not None and return_1d > 0:
        return f"{liquid_text} with positive daily rebound, but activity confirmation is still incomplete."

    return f"{liquid_text} but momentum is not confirmed. Avoid entry for now."
