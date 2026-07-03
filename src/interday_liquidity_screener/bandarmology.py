from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

SUPPORTIVE_CONTEXTS = {
    "BREAKOUT_NEAR",
    "REBOUND_NEAR_LOW",
    "PULLBACK_TO_MA",
    "UPTREND_CONTINUATION",
    "VOLUME_SPIKE",
    "EARLY_REVERSAL_ATTEMPT",
}

WINDOW_WEIGHTS = {
    "1D": 0.15,
    "3D": 0.20,
    "5D": 0.25,
    "10D": 0.20,
    "20D": 0.20,
}

WINDOW_LABELS = ["1D", "3D", "5D", "10D", "20D"]
ACC_SIGNALS = {"STRONG_ACCUMULATION", "MILD_ACCUMULATION"}
DIST_SIGNALS = {"STRONG_DISTRIBUTION", "MILD_DISTRIBUTION"}


def _value(row: dict[str, Any] | pd.Series, key: str, default: float = 0.0) -> float:
    value = row.get(key, default)
    return float(value) if value is not None and pd.notna(value) else default


def _normalize_window_label(value: Any) -> str:
    text = str(value or "CUSTOM").strip().upper()
    return text


def load_stage2_context(path: str | Path) -> pd.DataFrame:
    return pd.read_csv(path)


def load_bandar_detector(path: str | Path) -> pd.DataFrame:
    return pd.read_csv(path)


def load_broker_summary(path: str | Path) -> pd.DataFrame:
    return pd.read_csv(path)


def calculate_hhi(values: list[float] | pd.Series) -> float:
    series = pd.Series(values, dtype="float64").dropna().abs()
    total = series.sum()
    if total <= 0:
        return 0.0
    shares = series / total
    return float((shares**2).sum())


def _top_side(group: pd.DataFrame, side: str, count: int = 3) -> dict[str, Any]:
    side_group = group[group["side"] == side].dropna(subset=["net_value"]).copy()
    side_group["abs_net_value"] = side_group["net_value"].abs()
    side_group = side_group.sort_values("abs_net_value", ascending=False)
    label = "buyer" if side == "BUY" else "seller"
    result: dict[str, Any] = {}
    for index in range(1, count + 1):
        if len(side_group) >= index:
            row = side_group.iloc[index - 1]
            result[f"top_{label}_{index}_code"] = row.get("broker_code")
            result[f"top_{label}_{index}_net_value"] = row.get("net_value")
            result[f"top_{label}_{index}_avg_price"] = row.get("avg_price")
        else:
            result[f"top_{label}_{index}_code"] = None
            result[f"top_{label}_{index}_net_value"] = None
            result[f"top_{label}_{index}_avg_price"] = None
    return result


def calculate_broker_features(df: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    if df.empty:
        return pd.DataFrame(rows)
    working = df.copy()
    if "window_label" not in working.columns:
        working["window_label"] = "CUSTOM"
    for ticker, group in working.groupby("ticker"):
        buyer_values = group.loc[group["side"] == "BUY", "net_value"].fillna(0).abs()
        seller_values = group.loc[group["side"] == "SELL", "net_value"].fillna(0).abs()
        row: dict[str, Any] = {"ticker": ticker}
        row.update(_top_side(group, "BUY", 3))
        row.update(_top_side(group, "SELL", 3))
        row["top3_buyer_value"] = float(buyer_values.sort_values(ascending=False).head(3).sum())
        row["top3_seller_value"] = float(seller_values.sort_values(ascending=False).head(3).sum())
        row["buyer_hhi"] = calculate_hhi(buyer_values)
        row["seller_hhi"] = calculate_hhi(seller_values)
        row["top_buyer_avg_price"] = row.get("top_buyer_1_avg_price")
        row["top_seller_avg_price"] = row.get("top_seller_1_avg_price")
        row["broker_activity_available"] = bool(buyer_values.sum() > 0 or seller_values.sum() > 0)
        rows.append(row)
    return pd.DataFrame(rows)


def calculate_buyer_seller_features(df: pd.DataFrame) -> pd.DataFrame:
    return calculate_broker_features(df)


def _accdist_score(label: Any, acc: int, big_acc: int, dist: int, big_dist: int) -> int:
    text = str(label or "").lower()
    if "big acc" in text:
        return big_acc
    if "acc" in text:
        return acc
    if "big dist" in text:
        return big_dist
    if "dist" in text:
        return dist
    return 0


def score_single_window(row: dict[str, Any] | pd.Series, stage2_row: dict[str, Any] | pd.Series | None = None) -> float | None:
    merged = {}
    if stage2_row is not None:
        merged.update(stage2_row.to_dict() if isinstance(stage2_row, pd.Series) else dict(stage2_row))
    merged.update(row.to_dict() if isinstance(row, pd.Series) else dict(row))
    if not merged.get("broker_activity_available", True):
        return None

    score = 50
    score += _accdist_score(merged.get("broker_accdist"), 20, 30, -20, -30)
    score += _accdist_score(merged.get("avg_accdist"), 15, 25, -15, -25)
    score += _accdist_score(merged.get("top3_accdist"), 10, 20, -10, -20)
    score += _accdist_score(merged.get("top5_accdist"), 8, 15, -8, -15)

    avg_percent = merged.get("avg_percent")
    if avg_percent is not None and pd.notna(avg_percent):
        avg_percent = float(avg_percent)
        if avg_percent >= 20:
            score += 15
        elif 5 <= avg_percent < 20:
            score += 8
        elif avg_percent <= -20:
            score -= 15
        elif -20 < avg_percent <= -5:
            score -= 8

    avg_amount = merged.get("avg_amount")
    if avg_amount is not None and pd.notna(avg_amount):
        if float(avg_amount) > 0:
            score += 5
        elif float(avg_amount) < 0:
            score -= 5

    if merged.get("relative_activity_bucket") in {"NORMAL", "NORMAL_TO_QUIET", "ACTIVE", "VERY_ACTIVE"}:
        score += 5
    if _value(merged, "close_location") >= 0.6:
        score += 5
    if _value(merged, "momentum_score") >= 60:
        score += 5
    if merged.get("technical_context") in SUPPORTIVE_CONTEXTS:
        score += 5

    detector_avg = _value(merged, "detector_average_price")
    close = _value(merged, "close")
    if detector_avg > 0 and close > detector_avg * 1.10:
        score -= 10
    if merged.get("technical_context") in {"TOO_VOLATILE", "TOO_QUIET_ABSOLUTE", "INVALID_DATA"}:
        score -= 20
    return max(0, min(100, float(score)))


def calculate_bandarmology_score(row: dict[str, Any] | pd.Series) -> float | None:
    return score_single_window(row, {})


def classify_single_window_signal(score: float | None, broker_activity_available: bool) -> str:
    if not broker_activity_available or score is None or pd.isna(score):
        return "NO_BROKER_DATA"
    if score >= 75:
        return "STRONG_ACCUMULATION"
    if score >= 60:
        return "MILD_ACCUMULATION"
    if score >= 45:
        return "NEUTRAL_FLOW"
    if score >= 30:
        return "MILD_DISTRIBUTION"
    return "STRONG_DISTRIBUTION"


def classify_bandarmology_signal(score: float | None, broker_activity_available: bool) -> str:
    return classify_single_window_signal(score, broker_activity_available)


def _weighted_average(score_by_window: dict[str, float | None], labels: list[str] | None = None) -> float | None:
    labels = labels or list(WINDOW_WEIGHTS)
    available = {
        label: score_by_window.get(label)
        for label in labels
        if score_by_window.get(label) is not None and pd.notna(score_by_window.get(label))
    }
    if not available:
        return None
    weight_total = sum(WINDOW_WEIGHTS.get(label, 1.0) for label in available)
    if weight_total <= 0:
        return None
    return float(sum(float(score) * WINDOW_WEIGHTS.get(label, 1.0) for label, score in available.items()) / weight_total)


def aggregate_multi_window_scores(window_scores: dict[str, float | None]) -> dict[str, Any]:
    weighted = _weighted_average(window_scores)
    short_term = _weighted_average(window_scores, ["1D", "3D", "5D"])
    medium_term = _weighted_average(window_scores, ["10D", "20D"])
    return {
        "weighted_bandarmology_score": weighted,
        "short_term_score": short_term,
        "medium_term_score": medium_term,
        "score_trend": (short_term - medium_term) if short_term is not None and medium_term is not None else pd.NA,
    }


def calculate_consistency_features(window_rows: pd.DataFrame) -> dict[str, Any]:
    signals = window_rows["single_window_signal"].dropna().tolist() if "single_window_signal" in window_rows else []
    available_signals = [signal for signal in signals if signal != "NO_BROKER_DATA"]
    return {
        "available_window_count": len(available_signals),
        "accumulation_window_count": sum(signal in ACC_SIGNALS for signal in signals),
        "distribution_window_count": sum(signal in DIST_SIGNALS for signal in signals),
        "strong_accumulation_window_count": sum(signal == "STRONG_ACCUMULATION" for signal in signals),
        "strong_distribution_window_count": sum(signal == "STRONG_DISTRIBUTION" for signal in signals),
    }


def classify_final_bandarmology_signal(row: dict[str, Any] | pd.Series) -> str:
    weighted = row.get("weighted_bandarmology_score")
    if weighted is None or pd.isna(weighted):
        return "NO_BROKER_DATA"
    weighted = float(weighted)
    if _value(row, "strong_distribution_window_count") >= 3 or weighted < 30:
        return "STRONG_DISTRIBUTION"
    if row.get("signal_1d") in ACC_SIGNALS and _value(row, "medium_term_score", 100) < 45:
        return "SHORT_TERM_ACCUMULATION_AGAINST_MEDIUM_DISTRIBUTION"
    if row.get("signal_1d") in DIST_SIGNALS and _value(row, "medium_term_score") >= 60:
        return "PULLBACK_WITH_MEDIUM_ACCUMULATION"
    available_count = max(1, int(_value(row, "available_window_count")))
    strong_required = min(3, available_count)
    mild_required = min(2, available_count)
    if weighted >= 75 and _value(row, "accumulation_window_count") >= strong_required and _value(row, "strong_distribution_window_count") == 0:
        return "STRONG_ACCUMULATION"
    if weighted >= 60 and _value(row, "accumulation_window_count") >= mild_required and _value(row, "distribution_window_count") <= 2:
        return "MILD_ACCUMULATION"
    if 45 <= weighted < 60:
        return "NEUTRAL_FLOW"
    if 30 <= weighted < 45:
        return "MILD_DISTRIBUTION"
    return "STRONG_DISTRIBUTION"


def build_bandarmology_reason(row: dict[str, Any] | pd.Series) -> str:
    signal = row.get("bandarmology_signal")
    if signal == "NO_BROKER_DATA":
        return "no_broker_summary_data_available"
    if signal == "SHORT_TERM_ACCUMULATION_AGAINST_MEDIUM_DISTRIBUTION":
        return "short_term_accumulation_but_medium_window_distribution_dominates"
    if signal == "PULLBACK_WITH_MEDIUM_ACCUMULATION":
        return "short_term_distribution_inside_medium_term_accumulation"
    if signal in ACC_SIGNALS:
        return "multi_window_broker_detector_supports_accumulation"
    if signal in DIST_SIGNALS:
        return "multi_window_broker_detector_shows_distribution"
    return "multi_window_broker_detector_flow_is_neutral"


def build_bandarmology_summary(row: dict[str, Any] | pd.Series) -> str:
    signal = row.get("bandarmology_signal")
    if signal == "NO_BROKER_DATA":
        return "No broker summary data available across the requested windows."
    if signal == "SHORT_TERM_ACCUMULATION_AGAINST_MEDIUM_DISTRIBUTION":
        return "Short-term broker flow improves, but medium-window distribution is still dominant. Keep on watchlist, do not execute by default."
    if signal == "PULLBACK_WITH_MEDIUM_ACCUMULATION":
        return "Short-term selling appears inside a medium-term accumulation structure. Watch for reversal confirmation before execution."
    if signal in ACC_SIGNALS:
        return "Multi-window broker detector supports accumulation and is eligible for trade-plan review if technical context confirms."
    if signal in DIST_SIGNALS:
        return "Multi-window broker detector is distribution-biased; broker flow confirmation is not strong enough."
    return "Multi-window broker detector is neutral; wait for clearer accumulation."


def _assign_single_window_scores(stage2: pd.DataFrame, detector: pd.DataFrame, broker_features: pd.DataFrame) -> pd.DataFrame:
    detector = detector.copy()
    if "window_label" not in detector.columns:
        detector["window_label"] = "CUSTOM"
    detector["window_label"] = detector["window_label"].map(_normalize_window_label)
    if set(detector["window_label"].dropna().unique()) == {"CUSTOM"}:
        detector["window_label"] = "20D"
    merged = detector.merge(stage2, on="ticker", how="left", suffixes=("", "_stage2"))
    if not broker_features.empty:
        merged = merged.merge(broker_features[["ticker", "broker_activity_available"]], on="ticker", how="left")
    else:
        merged["broker_activity_available"] = False
    merged["broker_activity_available"] = merged["broker_activity_available"].fillna(False)
    scores = []
    signals = []
    for idx, row in merged.iterrows():
        s = score_single_window(row, row)
        scores.append(s)
        signals.append(classify_single_window_signal(s, bool(row["broker_activity_available"])))
    merged["single_window_score"] = scores
    merged["single_window_signal"] = signals
    return merged


def _copy_window_columns(row: dict[str, Any], label: str, window_row: pd.Series | None) -> None:
    suffix = label.lower()
    if window_row is None:
        row[f"score_{suffix}"] = pd.NA
        row[f"signal_{suffix}"] = "NO_BROKER_DATA"
        return
    row[f"score_{suffix}"] = window_row.get("single_window_score")
    row[f"signal_{suffix}"] = window_row.get("single_window_signal")
    for field in [
        "broker_accdist",
        "avg_accdist",
        "avg_amount",
        "avg_percent",
        "top3_accdist",
        "top5_accdist",
        "detector_average_price",
    ]:
        row[f"{field}_{suffix}"] = window_row.get(field)


def run_stage3b_multi_window_scoring(
    stage2_path: str | Path,
    detector_summary_path: str | Path,
    broker_summary_path: str | Path,
    output_path: str | Path,
) -> pd.DataFrame:
    stage2 = load_stage2_context(stage2_path)
    detector = load_bandar_detector(detector_summary_path)
    broker = load_broker_summary(broker_summary_path)
    broker_features = calculate_broker_features(broker)
    window_scored = _assign_single_window_scores(stage2, detector, broker_features)

    rows: list[dict[str, Any]] = []
    window_by_ticker = {ticker: group for ticker, group in window_scored.groupby("ticker")}
    for _, stage2_row in stage2.iterrows():
        ticker = stage2_row["ticker"]
        ticker_windows = window_by_ticker.get(ticker, pd.DataFrame())
        row = stage2_row.to_dict()
        row["as_of_date"] = ticker_windows["to_date"].dropna().max() if not ticker_windows.empty else stage2_row.get("last_date")
        score_by_window: dict[str, float | None] = {}
        for label in WINDOW_LABELS:
            label_rows = ticker_windows[ticker_windows["window_label"] == label]
            window_row = label_rows.iloc[0] if not label_rows.empty else None
            _copy_window_columns(row, label, window_row)
            score = None if window_row is None else window_row.get("single_window_score")
            score_by_window[label] = None if score is None or pd.isna(score) else float(score)
        row.update(aggregate_multi_window_scores(score_by_window))
        row.update(calculate_consistency_features(ticker_windows))
        if not broker_features.empty:
            feature_match = broker_features[broker_features["ticker"] == ticker]
            if not feature_match.empty:
                row.update(feature_match.iloc[0].to_dict())
        row["broker_activity_available"] = bool(row.get("broker_activity_available", False))
        row["bandarmology_score"] = row.get("weighted_bandarmology_score")
        row["bandarmology_signal"] = classify_final_bandarmology_signal(row)
        row["bandarmology_reason"] = build_bandarmology_reason(row)
        row["bandarmology_summary"] = build_bandarmology_summary(row)
        det5 = row.get("detector_average_price_5d")
        top_buyer_avg = row.get("top_buyer_1_avg_price")
        close = row.get("close")
        row["close_vs_detector_average_5d"] = (
            (float(close) - float(det5)) / float(det5)
            if close is not None and pd.notna(close) and det5 is not None and pd.notna(det5) and float(det5) != 0
            else pd.NA
        )
        row["close_vs_top_buyer_avg"] = (
            (float(close) - float(top_buyer_avg)) / float(top_buyer_avg)
            if close is not None and pd.notna(close) and top_buyer_avg is not None and pd.notna(top_buyer_avg) and float(top_buyer_avg) != 0
            else pd.NA
        )
        rows.append(row)

    output = pd.DataFrame(rows)
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    output.to_csv(path, index=False)
    counts = output["bandarmology_signal"].value_counts().to_dict() if not output.empty else {}
    print(f"Total tickers scored: {len(output)}")
    print(f"Broker data available: {int(output['broker_activity_available'].sum()) if 'broker_activity_available' in output else 0}")
    for signal in [
        "STRONG_ACCUMULATION",
        "MILD_ACCUMULATION",
        "SHORT_TERM_ACCUMULATION_AGAINST_MEDIUM_DISTRIBUTION",
        "PULLBACK_WITH_MEDIUM_ACCUMULATION",
        "NEUTRAL_FLOW",
        "MILD_DISTRIBUTION",
        "STRONG_DISTRIBUTION",
        "NO_BROKER_DATA",
    ]:
        print(f"{signal:48s}: {counts.get(signal, 0)}")
    print(f"Output saved to: {path}")
    return output


def run_stage3b_bandarmology_scoring(
    stage2_path: str | Path,
    detector_summary_path: str | Path,
    broker_summary_path: str | Path,
    output_path: str | Path,
) -> pd.DataFrame:
    return run_stage3b_multi_window_scoring(stage2_path, detector_summary_path, broker_summary_path, output_path)
