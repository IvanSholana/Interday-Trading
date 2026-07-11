"""
P8 Time-Decay TP + Trailing Stop.

Implements two exit improvements:
1. Time-decay: TP target reduces progressively as holding days increase
   (incentivizes early profit-taking, reduces time-stop exits).
2. Trailing stop: After price moves in favor, SL tightens to lock in profit.

Usage:
    from enhancements.trailing_stop import TrailingStopExit
    ts = TrailingStopExit(enabled=True)
    exit_result = ts.simulate_exit(entry_price, sl, tp1, tp2, daily_bars, time_stop)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd


@dataclass
class TrailingStopExit:
    """Enhanced exit logic with trailing stop and time-decay TP."""
    enabled: bool = True
    # Trailing stop: activate after price moves X% in favor
    trail_activation_pct: float = 0.02  # Activate after 2% profit
    trail_distance_pct: float = 0.015  # Trail SL 1.5% below highest price
    # Time decay: reduce TP by X% per holding day after day N
    time_decay_start_day: int = 3  # Start decaying after day 3
    time_decay_pct_per_day: float = 0.003  # Reduce TP by 0.3% per day
    # Breakeven stop: move SL to entry after X% profit locked
    breakeven_activation_pct: float = 0.015  # Move SL to entry after 1.5% profit

    def compute_decayed_tp(
        self,
        original_tp: float,
        entry_price: float,
        holding_days: int,
    ) -> float:
        """Compute time-decayed TP1 target.

        After time_decay_start_day, TP decreases daily to encourage exit.
        Never goes below entry_price + 1 tick worth of profit.
        """
        if not self.enabled or holding_days <= self.time_decay_start_day:
            return original_tp

        decay_days = holding_days - self.time_decay_start_day
        decay_amount = entry_price * self.time_decay_pct_per_day * decay_days
        decayed_tp = original_tp - decay_amount

        # Floor: at minimum entry + 1% (never decay below profit)
        floor_tp = entry_price * 1.01
        return max(decayed_tp, floor_tp)

    def compute_trailing_sl(
        self,
        current_sl: float,
        entry_price: float,
        highest_price: float,
    ) -> float:
        """Compute trailing stop loss based on highest price reached.

        Returns updated SL (only moves up, never down).
        """
        if not self.enabled:
            return current_sl

        profit_from_entry = (highest_price - entry_price) / entry_price

        # Breakeven stop
        if profit_from_entry >= self.breakeven_activation_pct:
            breakeven_sl = entry_price * 1.001  # Tiny buffer above entry
            current_sl = max(current_sl, breakeven_sl)

        # Trailing stop activation
        if profit_from_entry >= self.trail_activation_pct:
            trail_sl = highest_price * (1 - self.trail_distance_pct)
            current_sl = max(current_sl, trail_sl)

        return current_sl

    def simulate_exit(
        self,
        entry_price: float,
        stop_loss: float,
        take_profit_1: float,
        take_profit_2: float,
        daily_bars: pd.DataFrame,
        time_stop_days: int = 10,
        slippage_pct: float = 0.001,
    ) -> dict[str, Any]:
        """Simulate exit with trailing stop + time-decay TP.

        Args:
            entry_price: Actual entry price.
            stop_loss: Original planned SL.
            take_profit_1: Original planned TP1.
            take_profit_2: Original planned TP2.
            daily_bars: OHLCV bars starting from entry day (inclusive).
            time_stop_days: Maximum holding period.
            slippage_pct: Exit slippage estimate.

        Returns:
            Dict with exit details (exit_price, exit_reason, holding_days, etc.)
        """
        if not self.enabled or daily_bars.empty:
            return {"exit_reason": "ENHANCEMENT_DISABLED"}

        window = daily_bars.iloc[:time_stop_days]
        highest_price = entry_price
        current_sl = stop_loss
        exit_reason = "TIME_STOP"
        exit_price = float(window.iloc[-1]["close"]) * (1 - slippage_pct) if not window.empty else entry_price
        exit_day = len(window)
        tp1_hit = False
        tp2_hit = False

        for offset, (_, bar) in enumerate(window.iterrows()):
            high = float(bar["high"])
            low = float(bar["low"])
            holding_days = offset + 1

            # Update highest price for trailing
            highest_price = max(highest_price, high)

            # Compute current targets
            current_tp1 = self.compute_decayed_tp(take_profit_1, entry_price, holding_days)
            current_sl = self.compute_trailing_sl(current_sl, entry_price, highest_price)

            # Check SL hit first (conservative)
            if low <= current_sl:
                exit_reason = "TRAILING_SL_HIT" if current_sl > stop_loss else "SL_HIT"
                exit_price = current_sl * (1 - slippage_pct)
                exit_day = holding_days
                break

            # Check TP1 hit
            if high >= current_tp1:
                tp1_hit = True
                exit_reason = "TP1_HIT_DECAYED" if current_tp1 < take_profit_1 else "TP1_HIT"
                exit_price = current_tp1 * (1 - slippage_pct)
                exit_day = holding_days
                tp2_hit = high >= take_profit_2
                break

        return {
            "exit_reason": exit_reason,
            "exit_price": exit_price,
            "holding_days": exit_day,
            "final_sl": current_sl,
            "final_tp1": self.compute_decayed_tp(take_profit_1, entry_price, exit_day),
            "highest_price": highest_price,
            "tp1_hit": tp1_hit,
            "tp2_hit": tp2_hit,
            "trailing_activated": current_sl > stop_loss,
        }
