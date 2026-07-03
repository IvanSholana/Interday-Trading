from __future__ import annotations

from collections.abc import Sequence
from typing import TypeVar

import pandas as pd

T = TypeVar("T")


def split_batches(items: Sequence[T], batch_size: int) -> list[list[T]]:
    if batch_size <= 0:
        raise ValueError("batch_size must be greater than 0")
    return [list(items[i : i + batch_size]) for i in range(0, len(items), batch_size)]


def safe_pct_change(series: pd.Series, periods: int) -> float | None:
    try:
        value = series.pct_change(periods).iloc[-1]
    except Exception:
        return None
    return float(value) if pd.notna(value) else None


def safe_float(value: object) -> float | None:
    return float(value) if pd.notna(value) else None
