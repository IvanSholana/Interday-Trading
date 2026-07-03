from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

LIQUID_BUCKETS = {"HIGH_LIQUIDITY", "GOOD_LIQUIDITY"}

ENTRY_SETUPS = [
    "WATCH_ENTRY",
    "BREAKOUT_CANDIDATE",
    "PULLBACK_CANDIDATE",
    "REBOUND_CANDIDATE",
    "LIQUID_BUT_WEAK_TREND_AND_MOMENTUM",
    "LIQUID_BUT_WEAK_TREND",
    "LIQUID_BUT_WEAK_MOMENTUM",
    "LIQUID_BUT_TOO_VOLATILE",
    "LIQUID_BUT_TOO_QUIET",
    "AVOID_FOR_NOW",
    "INVALID_DATA",
]

TECHNICAL_OUTPUT_COLUMNS = [
    "ticker",
    "yahoo_ticker",
    "last_date",
    "close",
    "volume",
    "value_est",
    "liquidity_bucket",
    "trend_score",
    "momentum_score",
    "volatility_score",
    "relative_activity_bucket",
    "entry_setup",
    "technical_context",
    "bandar_watch_eligible",
    "technical_context_reason",
    "technical_context_summary",
    "technical_reason",
    "signal_summary",
    "ma20",
    "ma50",
    "ma100",
    "ma200",
    "rsi14",
    "atr14",
    "atr_pct",
    "volatility_20d",
    "avg_volume_20d",
    "avg_value_20d",
    "volume_ratio",
    "value_ratio",
    "return_1d",
    "return_3d",
    "return_5d",
    "return_10d",
    "return_20d",
    "high_20d",
    "low_20d",
    "high_60d",
    "low_60d",
    "distance_to_20d_high",
    "distance_from_20d_low",
    "distance_to_60d_high",
    "distance_from_60d_low",
    "distance_to_ma20",
    "distance_to_ma50",
    "close_location",
    "data_points",
    "is_data_valid",
]

BANDAR_CONTEXTS = {
    "BREAKOUT_NEAR",
    "REBOUND_NEAR_LOW",
    "PULLBACK_TO_MA",
    "VOLUME_SPIKE",
    "SIDEWAYS_COMPRESSION",
    "UPTREND_CONTINUATION",
    "EARLY_REVERSAL_ATTEMPT",
    "TECHNICALLY_WEAK_BUT_LIQUID",
}


def _value(row: dict[str, Any] | pd.Series, key: str, default: float = 0.0) -> float:
    value = row.get(key, default)
    return float(value) if pd.notna(value) and value is not None else default


def _bool_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "y"}
    return bool(value)


def _safe_div(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or denominator == 0 or pd.isna(denominator):
        return None
    return float(numerator) / float(denominator)


def load_stage_1_candidates(input_path: str | Path) -> pd.DataFrame:
    path = Path(input_path)
    if not path.exists():
        raise FileNotFoundError(f"Stage 1 input file not found: {path}")

    df = pd.read_csv(path)
    required = {
        "ticker",
        "yahoo_ticker",
        "close",
        "volume",
        "value_est",
        "avg_value_20d",
        "liquidity_score",
        "liquidity_bucket",
        "is_data_valid",
    }
    missing = required.difference(df.columns)
    if missing:
        raise ValueError(f"Stage 1 input is missing columns: {', '.join(sorted(missing))}")

    valid_mask = df["is_data_valid"].map(_bool_value)
    liquid_mask = df["liquidity_bucket"].isin(LIQUID_BUCKETS)
    return df[valid_mask & liquid_mask].copy()


def fetch_ohlcv_history(yahoo_ticker: str, period: str = "1y") -> pd.DataFrame:
    import yfinance as yf

    data = yf.download(
        tickers=yahoo_ticker,
        period=period,
        interval="1d",
        auto_adjust=False,
        progress=False,
        threads=False,
    )
    if data is None or data.empty:
        return pd.DataFrame()

    if isinstance(data.columns, pd.MultiIndex):
        if yahoo_ticker in data.columns.get_level_values(-1):
            data = data.xs(yahoo_ticker, axis=1, level=-1)
        elif yahoo_ticker in data.columns.get_level_values(0):
            data = data.xs(yahoo_ticker, axis=1, level=0)
        else:
            data.columns = data.columns.get_level_values(0)

    rename_map = {
        "Open": "open",
        "High": "high",
        "Low": "low",
        "Close": "close",
        "Adj Close": "adjusted_close",
        "Volume": "volume",
    }
    data = data.rename(columns=rename_map)
    columns = [column for column in ["open", "high", "low", "close", "adjusted_close", "volume"] if column in data.columns]
    data = data[columns].copy()
    data.index.name = "date"
    return data


def calculate_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.where(avg_loss != 0)
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50)


def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high = df["high"]
    low = df["low"]
    close = df["close"]
    previous_close = close.shift(1)
    true_range = pd.concat(
        [
            high - low,
            (high - previous_close).abs(),
            (low - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return true_range.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()


def calculate_technical_features(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()

    features = df.copy()
    required = {"open", "high", "low", "close", "volume"}
    missing = required.difference(features.columns)
    if missing:
        raise ValueError(f"OHLCV data is missing columns: {', '.join(sorted(missing))}")

    features = features.dropna(subset=["close"]).copy()
    features["volume"] = features["volume"].fillna(0)
    features["value_est"] = features["close"] * features["volume"]

    for window in [20, 50, 100, 200]:
        features[f"ma{window}"] = features["close"].rolling(window, min_periods=window).mean()

    features["rsi14"] = calculate_rsi(features["close"], 14)
    features["atr14"] = calculate_atr(features, 14)
    features["atr_pct"] = features["atr14"] / features["close"]
    features["volatility_20d"] = features["close"].pct_change().rolling(20, min_periods=20).std()
    features["avg_volume_20d"] = features["volume"].rolling(20, min_periods=20).mean()
    features["avg_value_20d"] = features["value_est"].rolling(20, min_periods=20).mean()
    features["volume_ratio"] = features["volume"] / features["avg_volume_20d"]
    features["value_ratio"] = features["value_est"] / features["avg_value_20d"]

    for period in [1, 3, 5, 10, 20]:
        features[f"return_{period}d"] = features["close"].pct_change(period)

    features["high_20d"] = features["high"].rolling(20, min_periods=20).max()
    features["low_20d"] = features["low"].rolling(20, min_periods=20).min()
    features["high_60d"] = features["high"].rolling(60, min_periods=60).max()
    features["low_60d"] = features["low"].rolling(60, min_periods=60).min()

    features["distance_to_20d_high"] = (features["high_20d"] - features["close"]) / features["close"]
    features["distance_from_20d_low"] = (features["close"] - features["low_20d"]) / features["close"]
    features["distance_to_60d_high"] = (features["high_60d"] - features["close"]) / features["close"]
    features["distance_from_60d_low"] = (features["close"] - features["low_60d"]) / features["close"]
    features["distance_to_ma20"] = (features["close"] - features["ma20"]) / features["ma20"]
    features["distance_to_ma50"] = (features["close"] - features["ma50"]) / features["ma50"]

    day_range = features["high"] - features["low"]
    features["close_location"] = (features["close"] - features["low"]) / day_range
    features.loc[day_range == 0, "close_location"] = 0.5
    return features.replace([float("inf"), -float("inf")], pd.NA)


def calculate_trend_score(row: dict[str, Any] | pd.Series) -> int:
    score = 0
    close = _value(row, "close")
    ma20 = row.get("ma20")
    ma50 = row.get("ma50")
    ma200 = row.get("ma200")
    return_20d = row.get("return_20d")

    if pd.notna(ma20) and close > ma20:
        score += 20
    if pd.notna(ma20) and pd.notna(ma50) and ma20 > ma50:
        score += 25
    if pd.notna(ma50) and close > ma50:
        score += 25
    if pd.notna(ma200) and close > ma200:
        score += 20
    if return_20d is not None and pd.notna(return_20d) and return_20d > 0:
        score += 10
    return min(score, 100)


def calculate_momentum_score(row: dict[str, Any] | pd.Series) -> int:
    score = 0
    rsi14 = row.get("rsi14")
    close_location = _value(row, "close_location", 0.5)

    if row.get("return_1d") is not None and pd.notna(row.get("return_1d")) and row.get("return_1d") > 0:
        score += 20
    if row.get("return_3d") is not None and pd.notna(row.get("return_3d")) and row.get("return_3d") > 0:
        score += 15
    if row.get("return_5d") is not None and pd.notna(row.get("return_5d")) and row.get("return_5d") > 0:
        score += 15
    if rsi14 is not None and pd.notna(rsi14) and 45 <= rsi14 <= 70:
        score += 25
    if close_location >= 0.6:
        score += 25
    return min(score, 100)


def calculate_volatility_score(row: dict[str, Any] | pd.Series) -> int:
    score = 0
    atr_pct = row.get("atr_pct")
    volatility_20d = row.get("volatility_20d")
    distance_to_ma20 = row.get("distance_to_ma20")

    if atr_pct is not None and pd.notna(atr_pct) and 0.015 <= atr_pct <= 0.05:
        score += 50
    if volatility_20d is not None and pd.notna(volatility_20d) and volatility_20d <= 0.04:
        score += 25
    if distance_to_ma20 is not None and pd.notna(distance_to_ma20) and -0.05 <= distance_to_ma20 <= 0.08:
        score += 25
    return min(score, 100)


def classify_relative_activity(row: dict[str, Any] | pd.Series) -> str:
    value_ratio = _value(row, "value_ratio")
    volume_ratio = _value(row, "volume_ratio")

    if value_ratio >= 1.5 and volume_ratio >= 1.5:
        return "VERY_ACTIVE"
    if value_ratio >= 1.0 and volume_ratio >= 1.0:
        return "ACTIVE"
    if value_ratio >= 0.75 or volume_ratio >= 0.75:
        return "NORMAL"
    if value_ratio >= 0.5 or volume_ratio >= 0.5:
        return "BELOW_AVERAGE"
    return "QUIET"


def _has_invalid_core_data(row: dict[str, Any] | pd.Series) -> bool:
    required = [
        "close",
        "value_est",
        "ma20",
        "ma50",
        "rsi14",
        "atr_pct",
        "volume_ratio",
        "value_ratio",
        "return_1d",
        "high_20d",
        "low_20d",
        "distance_from_20d_low",
        "close_location",
        "trend_score",
        "momentum_score",
        "volatility_score",
    ]
    return any(row.get(column) is None or pd.isna(row.get(column)) for column in required)


def classify_entry_setup(row: dict[str, Any] | pd.Series) -> str:
    if not row.get("is_data_valid", False) or _value(row, "data_points") < 120 or _has_invalid_core_data(row):
        return "INVALID_DATA"

    liquidity_bucket = row.get("liquidity_bucket")
    if liquidity_bucket not in LIQUID_BUCKETS:
        return "INVALID_DATA"

    close = _value(row, "close")
    ma20 = row.get("ma20")
    ma50 = row.get("ma50")
    high_20d = row.get("high_20d")
    rsi14 = row.get("rsi14")
    return_1d = row.get("return_1d")
    close_location = _value(row, "close_location", 0.5)
    value_ratio = _value(row, "value_ratio")
    volume_ratio = _value(row, "volume_ratio")
    value_est = _value(row, "value_est")
    distance_to_ma20 = row.get("distance_to_ma20")
    distance_from_20d_low = row.get("distance_from_20d_low")
    trend_score = _value(row, "trend_score")
    momentum_score = _value(row, "momentum_score")
    volatility_score = _value(row, "volatility_score")
    atr_pct = row.get("atr_pct")

    if atr_pct is not None and pd.notna(atr_pct) and atr_pct > 0.06:
        return "LIQUID_BUT_TOO_VOLATILE"

    positive_1d = return_1d is not None and pd.notna(return_1d) and return_1d > 0
    confirmed_activity = value_ratio >= 1.0 or volume_ratio >= 1.0

    breakout = (
        pd.notna(ma50)
        and pd.notna(high_20d)
        and pd.notna(rsi14)
        and close > ma50
        and close >= high_20d * 0.98
        and close_location >= 0.6
        and positive_1d
        and confirmed_activity
        and rsi14 <= 75
    )
    if breakout:
        return "BREAKOUT_CANDIDATE"

    pullback = (
        pd.notna(ma20)
        and pd.notna(ma50)
        and pd.notna(distance_to_ma20)
        and pd.notna(rsi14)
        and close > ma50
        and ma20 >= ma50
        and -0.03 <= distance_to_ma20 <= 0.03
        and 45 <= rsi14 <= 65
        and close_location >= 0.5
        and positive_1d
    )
    if pullback:
        return "PULLBACK_CANDIDATE"

    rebound = (
        pd.notna(distance_from_20d_low)
        and pd.notna(rsi14)
        and distance_from_20d_low <= 0.08
        and positive_1d
        and close_location >= 0.6
        and rsi14 < 55
        and (value_ratio >= 0.75 or volume_ratio >= 0.75)
    )
    if rebound:
        return "REBOUND_CANDIDATE"

    if trend_score < 40 and momentum_score < 40:
        return "LIQUID_BUT_WEAK_TREND_AND_MOMENTUM"
    if trend_score < 40:
        return "LIQUID_BUT_WEAK_TREND"
    if momentum_score < 50:
        return "LIQUID_BUT_WEAK_MOMENTUM"
    if value_ratio < 0.5 and volume_ratio < 0.5 and value_est < 50_000_000_000:
        return "LIQUID_BUT_TOO_QUIET"

    if (
        trend_score >= 65
        and momentum_score >= 60
        and volatility_score >= 60
        and close_location >= 0.6
        and positive_1d
    ):
        return "WATCH_ENTRY"

    return "AVOID_FOR_NOW"


def classify_technical_context(row: dict[str, Any] | pd.Series) -> str:
    if not row.get("is_data_valid", False) or _value(row, "data_points") < 120 or _has_invalid_core_data(row):
        return "INVALID_DATA"

    liquidity_bucket = row.get("liquidity_bucket")
    is_liquid = liquidity_bucket in LIQUID_BUCKETS
    close = _value(row, "close")
    ma20 = row.get("ma20")
    ma50 = row.get("ma50")
    high_20d = row.get("high_20d")
    low_20d = row.get("low_20d")
    rsi14 = row.get("rsi14")
    atr_pct = row.get("atr_pct")
    return_1d = row.get("return_1d")
    close_location = _value(row, "close_location", 0.5)
    value_ratio = _value(row, "value_ratio")
    volume_ratio = _value(row, "volume_ratio")
    value_est = _value(row, "value_est")
    volatility_20d = row.get("volatility_20d")
    distance_to_ma20 = row.get("distance_to_ma20")
    distance_to_ma50 = row.get("distance_to_ma50")
    distance_from_20d_low = row.get("distance_from_20d_low")
    trend_score = _value(row, "trend_score")
    momentum_score = _value(row, "momentum_score")
    positive_1d = return_1d is not None and pd.notna(return_1d) and return_1d > 0

    if atr_pct is not None and pd.notna(atr_pct) and atr_pct > 0.07:
        return "TOO_VOLATILE"
    if value_ratio < 0.5 and volume_ratio < 0.5 and value_est < 50_000_000_000:
        return "TOO_QUIET_ABSOLUTE"
    if is_liquid and pd.notna(high_20d) and close >= high_20d * 0.97 and positive_1d and close_location >= 0.55:
        return "BREAKOUT_NEAR"
    if (
        is_liquid
        and pd.notna(distance_from_20d_low)
        and pd.notna(rsi14)
        and distance_from_20d_low <= 0.10
        and (positive_1d or close_location >= 0.55)
        and rsi14 < 55
    ):
        return "REBOUND_NEAR_LOW"
    if pd.notna(ma50) and pd.notna(distance_to_ma20) and pd.notna(rsi14) and close > ma50 and -0.04 <= distance_to_ma20 <= 0.04 and 40 <= rsi14 <= 70:
        return "PULLBACK_TO_MA"
    if (value_ratio >= 1.5 or volume_ratio >= 1.5) and close_location >= 0.5:
        return "VOLUME_SPIKE"
    if (
        is_liquid
        and pd.notna(volatility_20d)
        and pd.notna(high_20d)
        and pd.notna(low_20d)
        and pd.notna(distance_to_ma20)
        and pd.notna(distance_to_ma50)
        and volatility_20d <= 0.025
        and close > 0
        and (high_20d - low_20d) / close <= 0.15
        and abs(distance_to_ma20) <= 0.04
        and abs(distance_to_ma50) <= 0.06
    ):
        return "SIDEWAYS_COMPRESSION"
    if pd.notna(ma20) and pd.notna(ma50) and close > ma20 and ma20 > ma50 and trend_score >= 65 and momentum_score >= 50:
        return "UPTREND_CONTINUATION"
    if pd.notna(ma50) and pd.notna(rsi14) and pd.notna(distance_from_20d_low) and close < ma50 and positive_1d and close_location >= 0.6 and rsi14 < 50 and distance_from_20d_low <= 0.15:
        return "EARLY_REVERSAL_ATTEMPT"
    if is_liquid:
        return "TECHNICALLY_WEAK_BUT_LIQUID"
    return "INVALID_DATA"


def is_bandar_watch_eligible(row: dict[str, Any] | pd.Series, min_value_est: float = 20_000_000_000) -> bool:
    return (
        bool(row.get("is_data_valid"))
        and row.get("liquidity_bucket") in LIQUID_BUCKETS
        and row.get("technical_context") in BANDAR_CONTEXTS
        and _value(row, "value_est") >= min_value_est
    )


def build_technical_context_reason(row: dict[str, Any] | pd.Series) -> str:
    context = row.get("technical_context")
    mapping = {
        "BREAKOUT_NEAR": "price_near_20d_high_with_positive_close",
        "REBOUND_NEAR_LOW": "price_near_20d_low_with_rebound_attempt",
        "PULLBACK_TO_MA": "pullback_near_ma20_with_trend_structure",
        "VOLUME_SPIKE": "relative_volume_or_value_spike_detected",
        "SIDEWAYS_COMPRESSION": "low_volatility_compression_near_moving_averages",
        "UPTREND_CONTINUATION": "trend_continuation_context",
        "EARLY_REVERSAL_ATTEMPT": "early_reversal_attempt_from_weak_trend",
        "TECHNICALLY_WEAK_BUT_LIQUID": "liquid_stock_with_weak_chart_still_allowed_for_bandar_check",
        "TOO_VOLATILE": "too_volatile_for_broad_watchlist",
        "TOO_QUIET_ABSOLUTE": "absolute_activity_too_quiet_for_bandar_watch",
        "INVALID_DATA": "invalid_or_insufficient_technical_data",
    }
    return mapping.get(str(context), "technical_context_not_classified")


def build_technical_context_summary(row: dict[str, Any] | pd.Series) -> str:
    context = row.get("technical_context")
    if context == "TECHNICALLY_WEAK_BUT_LIQUID":
        return "Liquid stock with weak technical structure; keep it eligible for broker-flow review because accumulation can appear before the chart improves."
    if context in BANDAR_CONTEXTS:
        return f"Broad technical context is {context}. This is a watchlist context for bandarmology, not a buy signal."
    if context == "TOO_VOLATILE":
        return "Volatility is too high for the broad broker-flow watchlist."
    if context == "TOO_QUIET_ABSOLUTE":
        return "Absolute transaction value is too quiet for reliable broker-flow analysis."
    return "Invalid or insufficient data for broad technical context."


def build_technical_reason(row: dict[str, Any] | pd.Series) -> str:
    setup = row.get("entry_setup")
    value_ratio = _value(row, "value_ratio")
    volume_ratio = _value(row, "volume_ratio")
    relative_activity = row.get("relative_activity_bucket")

    if setup == "INVALID_DATA":
        return "invalid_data_insufficient_history"
    if setup == "BREAKOUT_CANDIDATE":
        return "breakout_candidate_with_volume_confirmation"
    if setup == "PULLBACK_CANDIDATE":
        return "pullback_candidate_in_healthy_uptrend"
    if setup == "REBOUND_CANDIDATE":
        if value_ratio >= 1.0 or volume_ratio >= 1.0:
            return "positive_rebound_near_20d_low_with_strong_activity_confirmation"
        return "positive_rebound_near_20d_low_with_mild_activity_support"
    if setup == "WATCH_ENTRY":
        return "trend_momentum_and_volatility_are_tradeable"
    if setup == "LIQUID_BUT_TOO_VOLATILE":
        return "too_volatile_for_clean_5_to_10_percent_tp"
    if setup == "LIQUID_BUT_TOO_QUIET":
        return "liquid_stock_but_activity_is_absolutely_quiet"
    if setup == "LIQUID_BUT_WEAK_TREND_AND_MOMENTUM":
        return "high_liquidity_but_weak_trend_and_momentum"
    if setup == "LIQUID_BUT_WEAK_TREND":
        if relative_activity in {"BELOW_AVERAGE", "QUIET"}:
            return "high_liquidity_but_weak_trend_with_below_average_relative_activity"
        return "high_liquidity_but_weak_trend"
    if setup == "LIQUID_BUT_WEAK_MOMENTUM":
        return "high_liquidity_but_weak_momentum"
    if relative_activity in {"BELOW_AVERAGE", "QUIET"}:
        return "high_liquidity_with_below_average_relative_activity"
    return "no_healthy_entry_setup_detected"


def build_signal_summary(row: dict[str, Any] | pd.Series) -> str:
    setup = row.get("entry_setup")
    relative_activity = row.get("relative_activity_bucket")
    value_est = _value(row, "value_est")
    below_ma20 = _value(row, "close") < _value(row, "ma20")
    below_ma50 = _value(row, "close") < _value(row, "ma50")
    below_ma100 = _value(row, "close") < _value(row, "ma100")
    below_ma200 = _value(row, "close") < _value(row, "ma200")
    closing_low = _value(row, "close_location", 0.5) < 0.4
    activity_note = ""
    if relative_activity in {"BELOW_AVERAGE", "QUIET"} and value_est >= 50_000_000_000:
        activity_note = " Today's activity is below its 20-day average, but absolute transaction value remains high."

    if setup == "INVALID_DATA":
        return "Invalid or insufficient OHLCV history. Skip this ticker for stage 2."
    if setup == "BREAKOUT_CANDIDATE":
        return "Liquid stock trading near its 20-day high with positive activity confirmation. Watch for breakout entry."
    if setup == "PULLBACK_CANDIDATE":
        return "Liquid stock in an uptrend and pulling back near MA20. Watch for continuation confirmation."
    if setup == "REBOUND_CANDIDATE":
        if _value(row, "value_ratio") >= 1.0 or _value(row, "volume_ratio") >= 1.0:
            return "Liquid stock showing a positive rebound near its 20-day low with strong activity confirmation. Treat as rebound watch, not automatic buy."
        return "Liquid stock showing a positive rebound near its 20-day low. Activity is mildly supportive but not yet a strong confirmation. Treat as rebound watch, not automatic buy."
    if setup == "WATCH_ENTRY":
        return "Liquid stock with healthy trend, momentum, and volatility. Watch for execution rules before entry."
    if setup == "LIQUID_BUT_TOO_VOLATILE":
        if below_ma20 and below_ma50:
            return "Liquid stock, but price remains far below key moving averages and volatility is elevated. Avoid entry until reversal is clearer."
        return "Liquid stock, but ATR is too high for a controlled 5-10% take-profit setup."
    if setup == "LIQUID_BUT_TOO_QUIET":
        return "Liquid stock, but today's value and volume are far below normal. Avoid entry until activity returns."
    if setup == "LIQUID_BUT_WEAK_TREND_AND_MOMENTUM":
        if closing_low:
            return "Liquid stock, but trend and momentum are both weak. Closing near the daily low makes entry unattractive for now."
        return f"Liquid stock, but trend and momentum are both weak.{activity_note} Avoid entry until both improve."
    if setup == "LIQUID_BUT_WEAK_TREND":
        if below_ma20 and below_ma50 and below_ma100 and below_ma200:
            return f"Very liquid stock, but price is still below key moving averages.{activity_note} Avoid entry until trend improves."
        return f"Very liquid stock, but trend structure is weak.{activity_note} Avoid entry until trend improves."
    if setup == "LIQUID_BUT_WEAK_MOMENTUM":
        if closing_low:
            return "Liquid stock, but momentum is weak and it is closing near the daily low. Avoid entry for now."
        return f"Liquid stock, but momentum is still weak.{activity_note} Avoid entry for now."
    return "No healthy technical setup. Avoid entry for now."


def _invalid_result(stage_1_row: dict[str, Any] | pd.Series, reason: str) -> dict[str, Any]:
    return {
        "ticker": stage_1_row.get("ticker"),
        "yahoo_ticker": stage_1_row.get("yahoo_ticker"),
        "last_date": None,
        "close": None,
        "volume": None,
        "value_est": None,
        "liquidity_bucket": stage_1_row.get("liquidity_bucket"),
        "trend_score": 0,
        "momentum_score": 0,
        "volatility_score": 0,
        "relative_activity_bucket": "QUIET",
        "entry_setup": "INVALID_DATA",
        "technical_context": "INVALID_DATA",
        "bandar_watch_eligible": False,
        "technical_context_reason": reason,
        "technical_context_summary": "Invalid or insufficient data for broad technical context.",
        "technical_reason": reason,
        "signal_summary": "Invalid or insufficient OHLCV history. Skip this ticker for stage 2.",
        "data_points": 0,
        "is_data_valid": False,
    }


def build_latest_technical_row(stage_1_row: dict[str, Any] | pd.Series, history: pd.DataFrame) -> dict[str, Any]:
    if history is None or history.empty:
        return _invalid_result(stage_1_row, "invalid_data_download_failed")

    features = calculate_technical_features(history)
    data_points = len(features)
    if data_points < 120:
        result = _invalid_result(stage_1_row, "invalid_data_insufficient_history")
        result["data_points"] = data_points
        return result

    latest = features.iloc[-1].copy()
    result = latest.to_dict()
    result["ticker"] = stage_1_row.get("ticker")
    result["yahoo_ticker"] = stage_1_row.get("yahoo_ticker")
    result["last_date"] = str(features.index[-1].date())
    result["liquidity_bucket"] = stage_1_row.get("liquidity_bucket")
    result["data_points"] = data_points
    result["is_data_valid"] = True
    result["trend_score"] = calculate_trend_score(result)
    result["momentum_score"] = calculate_momentum_score(result)
    result["volatility_score"] = calculate_volatility_score(result)
    result["relative_activity_bucket"] = classify_relative_activity(result)
    result["entry_setup"] = classify_entry_setup(result)
    result["technical_context"] = classify_technical_context(result)
    result["bandar_watch_eligible"] = is_bandar_watch_eligible(result)
    result["technical_context_reason"] = build_technical_context_reason(result)
    result["technical_context_summary"] = build_technical_context_summary(result)
    result["technical_reason"] = build_technical_reason(result)
    result["signal_summary"] = build_signal_summary(result)
    return result


def build_technical_output_frame(results: list[dict[str, Any]]) -> pd.DataFrame:
    output = pd.DataFrame(results)
    for column in TECHNICAL_OUTPUT_COLUMNS:
        if column not in output.columns:
            output[column] = None

    return output[TECHNICAL_OUTPUT_COLUMNS].sort_values(
        by=["entry_setup", "trend_score", "momentum_score", "volatility_score"],
        ascending=[True, False, False, False],
        na_position="last",
    )


def run_stage_2_technical_screening(
    input_path: str | Path,
    output_path: str | Path,
    period: str = "1y",
) -> pd.DataFrame:
    candidates = load_stage_1_candidates(input_path)
    print(f"Stage 1 candidates loaded: {len(candidates)}")

    results: list[dict[str, Any]] = []
    failed_downloads = 0
    for _, candidate in candidates.iterrows():
        yahoo_ticker = candidate["yahoo_ticker"]
        try:
            history = fetch_ohlcv_history(yahoo_ticker, period=period)
            if history.empty:
                failed_downloads += 1
            results.append(build_latest_technical_row(candidate, history))
        except Exception as exc:
            failed_downloads += 1
            invalid = _invalid_result(candidate, f"invalid_data_error_{exc}")
            results.append(invalid)

    output = build_technical_output_frame(results)
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    output.to_csv(path, index=False)

    counts = output["entry_setup"].value_counts().to_dict() if not output.empty else {}
    context_counts = output["technical_context"].value_counts().to_dict() if not output.empty else {}
    print(f"Tickers processed: {len(output)}")
    print(f"Failed downloads: {failed_downloads}")
    print(f"Valid rows: {int(output['is_data_valid'].sum()) if not output.empty else 0}")
    print(f"Bandar watch eligible: {int(output['bandar_watch_eligible'].sum()) if not output.empty else 0}")
    print("=== Technical Context Distribution ===")
    for context, count in sorted(context_counts.items()):
        print(f"{context:28s}: {count}")
    for setup in ENTRY_SETUPS:
        print(f"{setup:20s}: {counts.get(setup, 0)}")
    print(f"Output saved to: {path}")
    return output
