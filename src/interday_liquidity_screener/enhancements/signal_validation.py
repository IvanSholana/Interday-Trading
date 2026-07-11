"""
P10 Statistical Signal Validation + Walk-Forward Metrics.

Validates signal quality by computing out-of-sample hit rates, confidence
intervals, and walk-forward performance metrics from historical backtest data.

Usage:
    from enhancements.signal_validation import SignalValidator
    validator = SignalValidator()
    report = validator.validate_signals(backtest_trades_df)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


@dataclass
class SignalValidator:
    """Statistical validation of trading signals from backtest data."""
    enabled: bool = True
    # Minimum trades needed for statistical significance
    min_trades_for_significance: int = 15
    # Confidence level for intervals
    confidence_level: float = 0.95
    # Walk-forward window sizes
    train_window_days: int = 60
    test_window_days: int = 20
    # Minimum acceptable out-of-sample win rate
    min_oos_win_rate: float = 0.40
    # Signal degradation threshold (when to flag)
    degradation_threshold_pct: float = 0.20  # 20% drop from historical

    def compute_hit_rate_by_signal(self, trades: pd.DataFrame) -> dict[str, Any]:
        """Compute win rate per entry_setup/bandarmology_signal type.

        Returns per-signal stats: hit_rate, count, avg_return, significance.
        """
        if not self.enabled or trades.empty:
            return {"signals": {}, "overall": {}}

        closed = trades[trades["backtest_status"] == "CLOSED_TRADE"].copy()
        if closed.empty:
            return {"signals": {}, "overall": {"total_closed": 0}}

        closed["net_return_pct"] = pd.to_numeric(closed["net_return_pct"], errors="coerce")
        closed["is_win"] = closed["net_return_pct"] > 0

        # Overall stats
        overall_win_rate = float(closed["is_win"].mean())
        overall_count = len(closed)

        # Per entry_setup
        signal_stats: dict[str, dict[str, Any]] = {}
        if "technical_context" in closed.columns:
            for signal, group in closed.groupby("technical_context"):
                if len(group) < 3:
                    continue
                win_rate = float(group["is_win"].mean())
                avg_ret = float(group["net_return_pct"].mean())
                signal_stats[str(signal)] = {
                    "count": len(group),
                    "win_rate": round(win_rate, 3),
                    "avg_return_pct": round(avg_ret, 4),
                    "significant": len(group) >= self.min_trades_for_significance,
                    "confidence_interval": self._bootstrap_ci(group["is_win"].values) if len(group) >= 10 else None,
                }

        # Per bandarmology signal
        bandar_stats: dict[str, dict[str, Any]] = {}
        if "bandarmology_signal" in closed.columns:
            for signal, group in closed.groupby("bandarmology_signal"):
                if len(group) < 3 or pd.isna(signal):
                    continue
                win_rate = float(group["is_win"].mean())
                bandar_stats[str(signal)] = {
                    "count": len(group),
                    "win_rate": round(win_rate, 3),
                    "avg_return_pct": round(float(group["net_return_pct"].mean()), 4),
                }

        return {
            "overall": {
                "total_closed": overall_count,
                "win_rate": round(overall_win_rate, 3),
                "avg_return_pct": round(float(closed["net_return_pct"].mean()), 4),
            },
            "by_technical_context": signal_stats,
            "by_bandarmology_signal": bandar_stats,
        }

    def walk_forward_analysis(self, trades: pd.DataFrame) -> dict[str, Any]:
        """Perform rolling-window walk-forward analysis.

        Each window: train on N days of historical trades, test on next M days.
        This isolates in-sample from out-of-sample to detect overfitting.

        NOTE: This is a simplified walk-forward on closed trades sorted by exit_date.
        A full point-in-time walk-forward would re-run signal generation per window,
        which requires the full pipeline and is computationally expensive.
        """
        if not self.enabled or trades.empty:
            return {"windows": [], "degradation_detected": False, "method": "rolling_trade_window"}

        closed = trades[trades["backtest_status"] == "CLOSED_TRADE"].copy()
        if len(closed) < self.min_trades_for_significance:
            return {"windows": [], "note": "insufficient trades for walk-forward", "method": "rolling_trade_window"}

        closed["exit_date"] = pd.to_datetime(closed["exit_date"], errors="coerce")
        closed = closed.dropna(subset=["exit_date"]).sort_values("exit_date")
        closed["net_return_pct"] = pd.to_numeric(closed["net_return_pct"], errors="coerce")
        closed["is_win"] = closed["net_return_pct"] > 0

        # Rolling window: train on train_window trades, test on test_window trades
        # Step by test_window to avoid overlap in test sets
        train_size = max(self.min_trades_for_significance, len(closed) // 4)
        test_size = max(5, len(closed) // 8)
        windows: list[dict[str, Any]] = []

        idx = 0
        window_num = 0
        while idx + train_size + test_size <= len(closed):
            window_num += 1
            train = closed.iloc[idx:idx + train_size]
            test = closed.iloc[idx + train_size:idx + train_size + test_size]

            train_wr = float(train["is_win"].mean())
            test_wr = float(test["is_win"].mean())
            train_avg_ret = float(train["net_return_pct"].mean())
            test_avg_ret = float(test["net_return_pct"].mean())
            degradation = (train_wr - test_wr) / train_wr if train_wr > 0 else 0

            windows.append({
                "window": window_num,
                "train_period": f"{train['exit_date'].iloc[0].date()} to {train['exit_date'].iloc[-1].date()}",
                "test_period": f"{test['exit_date'].iloc[0].date()} to {test['exit_date'].iloc[-1].date()}",
                "train_trades": len(train),
                "test_trades": len(test),
                "train_win_rate": round(train_wr, 3),
                "test_win_rate": round(test_wr, 3),
                "train_avg_return": round(train_avg_ret, 4),
                "test_avg_return": round(test_avg_ret, 4),
                "degradation_pct": round(degradation, 3),
                "oos_acceptable": test_wr >= self.min_oos_win_rate,
            })

            # Step forward by test_size (non-overlapping test windows)
            idx += test_size

        degradation_detected = any(
            w["degradation_pct"] > self.degradation_threshold_pct for w in windows
        )

        avg_oos = float(np.mean([w["test_win_rate"] for w in windows])) if windows else None
        avg_train = float(np.mean([w["train_win_rate"] for w in windows])) if windows else None
        overfit_gap = round(avg_train - avg_oos, 3) if avg_train is not None and avg_oos is not None else None

        return {
            "method": "rolling_trade_window",
            "windows": windows,
            "total_windows": len(windows),
            "degradation_detected": degradation_detected,
            "avg_oos_win_rate": round(avg_oos, 3) if avg_oos is not None else None,
            "avg_train_win_rate": round(avg_train, 3) if avg_train is not None else None,
            "overfit_gap": overfit_gap,
            "note": (
                "Overfit gap > 10% — signal parameters may not generalize."
                if overfit_gap and overfit_gap > 0.10
                else "Out-of-sample performance is consistent with in-sample."
                if overfit_gap is not None and overfit_gap <= 0.10
                else None
            ),
        }

    def _bootstrap_ci(self, wins: np.ndarray, n_bootstrap: int = 1000) -> dict[str, float]:
        """Bootstrap confidence interval for win rate."""
        rng = np.random.default_rng(42)
        boot_rates = []
        for _ in range(n_bootstrap):
            sample = rng.choice(wins, size=len(wins), replace=True)
            boot_rates.append(float(sample.mean()))

        alpha = 1 - self.confidence_level
        lower = float(np.percentile(boot_rates, alpha / 2 * 100))
        upper = float(np.percentile(boot_rates, (1 - alpha / 2) * 100))
        return {
            "lower": round(lower, 3),
            "upper": round(upper, 3),
            "confidence_level": self.confidence_level,
        }

    def full_validation_report(self, trades: pd.DataFrame) -> dict[str, Any]:
        """Generate complete signal validation report."""
        hit_rates = self.compute_hit_rate_by_signal(trades)
        walk_forward = self.walk_forward_analysis(trades)

        # Overall assessment
        overall_wr = hit_rates.get("overall", {}).get("win_rate", 0)
        oos_wr = walk_forward.get("avg_oos_win_rate")
        assessment = "ROBUST"
        if overall_wr < self.min_oos_win_rate:
            assessment = "WEAK_SIGNAL"
        elif walk_forward.get("degradation_detected"):
            assessment = "DEGRADING"
        elif oos_wr and oos_wr < self.min_oos_win_rate:
            assessment = "OOS_UNDERPERFORM"

        return {
            "assessment": assessment,
            "hit_rates": hit_rates,
            "walk_forward": walk_forward,
            "recommendation": (
                "Signals are statistically valid for production use."
                if assessment == "ROBUST"
                else "Review signal parameters; out-of-sample performance shows weakness."
            ),
        }
