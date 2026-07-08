from __future__ import annotations

from typing import Any, TypeVar
import math

import pandas as pd


def safe_float(value: Any, default: float | None = None) -> float | None:
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


def safe_bool(value: Any) -> bool:
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


def clip_score(value: float, low: float = 0, high: float = 100) -> float:
    return max(low, min(high, float(value)))


def threshold_score(value: float | None, threshold: float, weight: float) -> float:
    if value is None or threshold <= 0:
        return 0.0
    return min(max(value / threshold, 0), 1.0) * weight


_T = TypeVar("_T")


def first_present(row: dict[str, Any], keys: list[str], default: _T = None) -> _T:  # type: ignore[assignment]
    """Return the first non-None, non-NaN value found in *row* under *keys*.

    The TypeVar ``_T`` is bound to the type of *default* so that callers that
    pass a typed default (e.g. ``default=0.0``) get a typed return value back
    instead of opaque ``Any``.

    Args:
        row: A flat dictionary (typically a CSV row).
        keys: Ordered list of column names to try.
        default: Value returned if none of *keys* is present or non-null.

    Returns:
        The first valid value, or *default*.
    """
    for key in keys:
        if key in row and row.get(key) is not None:
            value = row.get(key)
            try:
                if pd.isna(value):
                    continue
            except (TypeError, ValueError):
                pass
            return value  # type: ignore[return-value]
    return default
