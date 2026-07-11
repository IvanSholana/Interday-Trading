"""
P7 Support/Resistance-Based Take Profit.

Instead of fixed TP % or only ATR-based, this module calculates TP targets
based on actual price structure: nearest resistance level (high_20d, high_60d,
MA levels above price). This produces more realistic profit targets.

Usage:
    from enhancements.sr_take_profit import SRTakeProfit
    sr = SRTakeProfit(enabled=True)
    tp1, tp2 = sr.compute_tp_levels(entry_price, row_data)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd


@dataclass
class SRTakeProfit:
    """Compute TP levels from nearest resistance/support structure."""
    enabled: bool = True
    # Minimum TP % (even if resistance is far)
    min_tp1_pct: float = 0.03
    min_tp2_pct: float = 0.05
    # Maximum TP % (cap even if resistance is very far)
    max_tp1_pct: float = 0.12
    max_tp2_pct: float = 0.20
    # Buffer below resistance (don't target exact resistance, allow some room)
    resistance_buffer_pct: float = 0.005

    def _find_resistance_levels(self, entry_price: float, row: dict[str, Any]) -> list[float]:
        """Collect all known resistance levels above entry_price, sorted ascending."""
        levels: list[float] = []
        candidates = [
            row.get("high_20d"),
            row.get("high_60d"),
            row.get("ma50"),
            row.get("ma100"),
            row.get("ma200"),
        ]
        for level in candidates:
            if level is not None and not pd.isna(level):
                lv = float(level)
                if lv > entry_price * 1.01:  # at least 1% above entry
                    levels.append(lv)
        return sorted(set(levels))

    def compute_tp_levels(
        self,
        entry_price: float,
        row: dict[str, Any],
        atr14: float | None = None,
        config_tp1_pct: float = 0.05,
        config_tp2_pct: float = 0.08,
    ) -> tuple[float, float]:
        """Compute TP1 and TP2 based on resistance structure.

        Returns (tp1_price, tp2_price). Uses resistance levels when available,
        falls back to config-based TP when not.
        """
        if not self.enabled or entry_price <= 0:
            return (
                entry_price * (1 + config_tp1_pct),
                entry_price * (1 + config_tp2_pct),
            )

        resistances = self._find_resistance_levels(entry_price, row)
        fixed_tp1 = entry_price * (1 + config_tp1_pct)
        fixed_tp2 = entry_price * (1 + config_tp2_pct)

        # TP1: nearest resistance (with buffer), bounded by min/max
        if resistances:
            nearest_r = resistances[0]
            sr_tp1 = nearest_r * (1 - self.resistance_buffer_pct)
            tp1 = max(
                entry_price * (1 + self.min_tp1_pct),
                min(sr_tp1, entry_price * (1 + self.max_tp1_pct)),
            )
        else:
            tp1 = fixed_tp1

        # TP2: second resistance or ATR-extended target
        if len(resistances) >= 2:
            second_r = resistances[1]
            sr_tp2 = second_r * (1 - self.resistance_buffer_pct)
            tp2 = max(
                entry_price * (1 + self.min_tp2_pct),
                min(sr_tp2, entry_price * (1 + self.max_tp2_pct)),
            )
        elif atr14 and atr14 > 0:
            # Use 3×ATR as TP2 target
            tp2 = max(fixed_tp2, entry_price + atr14 * 3)
            tp2 = min(tp2, entry_price * (1 + self.max_tp2_pct))
        else:
            tp2 = fixed_tp2

        # Ensure TP2 > TP1
        tp2 = max(tp2, tp1 * 1.02)
        return tp1, tp2
