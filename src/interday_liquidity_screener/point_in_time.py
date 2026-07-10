"""Point-in-time invariants and feature availability metadata."""

from __future__ import annotations

import pandas as pd


FEATURE_AVAILABILITY = {
    "raw_ohlcv": "after_market_close",
    "technical_features": "after_market_close",
    "broker_snapshot": "as_of_snapshot_timestamp",
    "orderbook_snapshot": "live_only",
    "corporate_action": "as_of_announcement_timestamp",
}


def assert_point_in_time(
    data: pd.DataFrame,
    *,
    data_cutoff_timestamp: pd.Timestamp,
    decision_timestamp: pd.Timestamp,
) -> None:
    """Fail closed if an input row or cutoff is later than the decision."""

    cutoff = pd.Timestamp(data_cutoff_timestamp)
    decision = pd.Timestamp(decision_timestamp)
    if cutoff > decision:
        raise ValueError("data_cutoff_timestamp exceeds decision_timestamp")
    if data is None or data.empty:
        return
    timestamps = pd.to_datetime(data.index, errors="coerce")
    if timestamps.isna().any():
        raise ValueError("input contains an invalid timestamp")
    if timestamps.max() > cutoff:
        raise ValueError("future rows detected after data_cutoff_timestamp")


__all__ = ["FEATURE_AVAILABILITY", "assert_point_in_time"]
