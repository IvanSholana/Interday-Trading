"""Correlation audit for hybrid score components; never mutates weights."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


DEFAULT_FEATURES = (
    "liquidity_score", "technical_score", "smart_money_score", "price_extension_score",
    "market_regime_score", "sector_strength_score", "orderbook_score",
)


@dataclass(frozen=True)
class FeatureCorrelationAudit:
    correlation_matrix: pd.DataFrame
    high_correlation_pairs: tuple[tuple[str, str, float], ...]
    sample_size: int
    method: str = "spearman"


def audit_feature_correlations(frame: pd.DataFrame, features: tuple[str, ...] = DEFAULT_FEATURES,
                               threshold: float = 0.80, min_sample_size: int = 30) -> FeatureCorrelationAudit:
    available = [feature for feature in features if feature in frame.columns]
    numeric = frame[available].apply(pd.to_numeric, errors="coerce") if available else pd.DataFrame()
    complete = numeric.dropna()
    if len(complete) < min_sample_size:
        return FeatureCorrelationAudit(pd.DataFrame(index=available, columns=available, dtype=float), (), len(complete))
    matrix = complete.corr(method="spearman")
    pairs = []
    for left_index, left in enumerate(available):
        for right in available[left_index + 1:]:
            value = matrix.loc[left, right]
            if pd.notna(value) and abs(float(value)) >= threshold:
                pairs.append((left, right, float(value)))
    return FeatureCorrelationAudit(matrix, tuple(pairs), len(complete))


__all__ = ["DEFAULT_FEATURES", "FeatureCorrelationAudit", "audit_feature_correlations"]
