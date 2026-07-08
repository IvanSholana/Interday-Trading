"""AdaptiveTakeProfit — ATR-based and resistance-based take-profit levels."""

from __future__ import annotations

import math
from dataclasses import dataclass

from interday_liquidity_screener.trade_plan import round_price_to_tick


@dataclass(frozen=True)
class AdaptiveTPConfig:
    """Configuration for adaptive take-profit calculation."""

    mode: str = "fixed"  # "adaptive" or "fixed"
    tp1_atr_multiple: float = 1.5
    tp2_atr_multiple: float = 2.5
    min_tp1_atr_multiple: float = 0.5  # Floor: entry + 0.5*ATR
    min_tp2_atr_multiple: float = 1.0  # Floor: entry + 1.0*ATR
    max_tp_pct: float = 0.12  # Ceiling 12%
    min_tp1_pct: float = 0.02  # Floor 2%
    fixed_tp1_pct: float = 0.05  # Fallback fixed mode
    fixed_tp2_pct: float = 0.08  # Fallback fixed mode


class AdaptiveTakeProfit:
    """Calculate adaptive take-profit levels using ATR and resistance levels."""

    def __init__(self, config: AdaptiveTPConfig | None = None) -> None:
        self.config = config or AdaptiveTPConfig()

    def calculate(
        self,
        entry_price: float,
        atr14: float,
        high_20d: float | None = None,
        high_60d: float | None = None,
    ) -> tuple[float, float]:
        """Return (tp1, tp2) clamped and tick-rounded."""
        cfg = self.config

        use_fixed = (
            cfg.mode == "fixed"
            or atr14 is None
            or (isinstance(atr14, float) and math.isnan(atr14))
            or atr14 == 0
        )

        if use_fixed:
            tp1 = entry_price * (1 + cfg.fixed_tp1_pct)
            tp2 = entry_price * (1 + cfg.fixed_tp2_pct)
            tp1 = round_price_to_tick(tp1, mode="floor")
            tp2 = round_price_to_tick(tp2, mode="floor")
            if tp1 >= tp2:
                tp2 = tp1 + 1
                tp2 = round_price_to_tick(tp2, mode="ceil")
            return (tp1, tp2)

        # Adaptive mode
        tp1_raw = entry_price + cfg.tp1_atr_multiple * atr14
        tp2_raw = entry_price + cfg.tp2_atr_multiple * atr14

        resistance = high_20d if high_20d is not None else high_60d
        if resistance is not None and resistance > tp2_raw:
            tp2_raw = resistance

        # Apply ATR-based floor
        tp1_floor = entry_price + cfg.min_tp1_atr_multiple * atr14
        tp2_floor = entry_price + cfg.min_tp2_atr_multiple * atr14
        tp1_raw = max(tp1_raw, tp1_floor)
        tp2_raw = max(tp2_raw, tp2_floor)

        # Apply percentage clamp
        min_tp_value = entry_price * (1 + cfg.min_tp1_pct)
        max_tp_value = entry_price * (1 + cfg.max_tp_pct)

        tp1 = max(tp1_raw, min_tp_value)
        tp1 = min(tp1, max_tp_value)
        tp2 = max(tp2_raw, min_tp_value)
        tp2 = min(tp2, max_tp_value)

        if tp1 >= tp2:
            tp2 = tp1 + 1

        tp1 = max(tp1, entry_price + 1)
        tp2 = max(tp2, entry_price + 2)

        tp1 = round_price_to_tick(tp1, mode="floor")
        tp2 = round_price_to_tick(tp2, mode="floor")

        if tp1 >= tp2:
            tp2 = tp1 + 1
            tp2 = round_price_to_tick(tp2, mode="ceil")

        if tp1 <= entry_price:
            tp1 = round_price_to_tick(entry_price + 1, mode="ceil")
        if tp2 <= tp1:
            tp2 = round_price_to_tick(tp1 + 1, mode="ceil")

        return (tp1, tp2)


__all__ = ["AdaptiveTakeProfit", "AdaptiveTPConfig"]
