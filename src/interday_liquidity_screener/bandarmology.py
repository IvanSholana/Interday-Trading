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
}


def _value(row: dict[str, Any] | pd.Series, key: str, default: float = 0.0) -> float:
    value = row.get(key, default)
    return float(value) if value is not None and pd.notna(value) else default


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


def calculate_buyer_seller_features(df: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    if df.empty:
        return pd.DataFrame(rows)
    for ticker, group in df.groupby("ticker"):
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


def calculate_bandarmology_score(row: dict[str, Any] | pd.Series) -> float | None:
    if not row.get("broker_activity_available", False):
        return None
    score = 50
    score += _accdist_score(row.get("broker_accdist"), 20, 30, -20, -30)
    score += _accdist_score(row.get("avg_accdist"), 15, 25, -15, -25)
    score += _accdist_score(row.get("top3_accdist"), 10, 20, -10, -20)
    score += _accdist_score(row.get("top5_accdist"), 8, 15, -8, -15)

    avg_percent = row.get("avg_percent")
    if avg_percent is not None and pd.notna(avg_percent):
        if avg_percent >= 20:
            score += 15
        elif 5 <= avg_percent < 20:
            score += 8
        elif avg_percent <= -20:
            score -= 15
        elif -20 < avg_percent <= -5:
            score -= 8

    avg_amount = row.get("avg_amount")
    if avg_amount is not None and pd.notna(avg_amount):
        if avg_amount > 0:
            score += 5
        elif avg_amount < 0:
            score -= 5

    if row.get("relative_activity_bucket") in {"NORMAL", "ACTIVE", "VERY_ACTIVE"}:
        score += 5
    if _value(row, "close_location") >= 0.6:
        score += 5
    if _value(row, "momentum_score") >= 60:
        score += 5
    if row.get("technical_context") in SUPPORTIVE_CONTEXTS:
        score += 5

    detector_avg = _value(row, "detector_average_price")
    close = _value(row, "close")
    if detector_avg > 0 and close > detector_avg * 1.10:
        score -= 10
    if row.get("technical_context") in {"TOO_VOLATILE", "TOO_QUIET_ABSOLUTE"}:
        score -= 20
    return max(0, min(100, float(score)))


def classify_bandarmology_signal(score: float | None, broker_activity_available: bool) -> str:
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


def build_bandarmology_reason(row: dict[str, Any] | pd.Series) -> str:
    if row.get("bandarmology_signal") == "NO_BROKER_DATA":
        return "no_broker_summary_data_available"
    negative_labels = " ".join(
        str(row.get(column, ""))
        for column in ["broker_accdist", "avg_accdist", "top3_accdist", "top5_accdist"]
    ).lower()
    if "dist" in negative_labels and _value(row, "avg_amount") < 0:
        return "broker_flow_shows_distribution_with_negative_avg_and_top_broker_pressure"
    if row.get("bandarmology_signal") in {"STRONG_ACCUMULATION", "MILD_ACCUMULATION"}:
        return "broker_detector_supports_accumulation"
    return "broker_detector_flow_is_neutral_or_distribution"


def build_bandarmology_summary(row: dict[str, Any] | pd.Series) -> str:
    reason = row.get("bandarmology_reason")
    if row.get("bandarmology_signal") == "NO_BROKER_DATA":
        return "No broker summary data available, cannot score bandarmology."
    if reason == "broker_flow_shows_distribution_with_negative_avg_and_top_broker_pressure":
        return "Broker detector shows distribution: average flow and top broker groups are negative, with Dist signals on avg/top3/top5. Avoid treating this as accumulation."
    if row.get("bandarmology_signal") in {"STRONG_ACCUMULATION", "MILD_ACCUMULATION"}:
        return "Broker detector supports accumulation and technical context is acceptable for trade-plan review."
    return "Broker detector is neutral or distribution-biased; broker flow confirmation is not strong enough."


def run_stage3b_bandarmology_scoring(
    stage2_path: str | Path,
    detector_summary_path: str | Path,
    broker_summary_path: str | Path,
    output_path: str | Path,
) -> pd.DataFrame:
    stage2 = load_stage2_context(stage2_path)
    detector = load_bandar_detector(detector_summary_path)
    broker = load_broker_summary(broker_summary_path)
    features = calculate_buyer_seller_features(broker)
    merged = stage2.merge(detector, on="ticker", how="left").merge(features, on="ticker", how="left")
    merged["broker_activity_available"] = merged["broker_activity_available"].fillna(False)
    merged["close_vs_detector_average"] = merged.apply(
        lambda row: (row["close"] - row["detector_average_price"]) / row["detector_average_price"]
        if pd.notna(row.get("detector_average_price")) and row.get("detector_average_price") not in {0, None}
        else pd.NA,
        axis=1,
    )
    merged["close_vs_top_buyer_avg"] = merged.apply(
        lambda row: (row["close"] - row["top_buyer_avg_price"]) / row["top_buyer_avg_price"]
        if pd.notna(row.get("top_buyer_avg_price")) and row.get("top_buyer_avg_price") not in {0, None}
        else pd.NA,
        axis=1,
    )
    merged["bandarmology_score"] = merged.apply(calculate_bandarmology_score, axis=1)
    merged["bandarmology_signal"] = merged.apply(
        lambda row: classify_bandarmology_signal(row["bandarmology_score"], bool(row["broker_activity_available"])),
        axis=1,
    )
    merged["bandarmology_reason"] = merged.apply(build_bandarmology_reason, axis=1)
    merged["bandarmology_summary"] = merged.apply(build_bandarmology_summary, axis=1)

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(path, index=False)
    counts = merged["bandarmology_signal"].value_counts().to_dict()
    print(f"Total tickers scored: {len(merged)}")
    print(f"Broker data available: {int(merged['broker_activity_available'].sum())}")
    for signal in ["STRONG_ACCUMULATION", "MILD_ACCUMULATION", "NEUTRAL_FLOW", "MILD_DISTRIBUTION", "STRONG_DISTRIBUTION", "NO_BROKER_DATA"]:
        print(f"{signal:22s}: {counts.get(signal, 0)}")
    print(f"Output saved to: {path}")
    return merged
