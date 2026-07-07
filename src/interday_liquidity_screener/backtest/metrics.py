"""EdgeMetrics — compute aggregate and segmented edge metrics from trade ledger."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from interday_liquidity_screener.backtest.simulator import TradeSimulation


@dataclass
class EdgeMetricsResult:
    """Result of edge metrics computation."""

    total_trades: int = 0
    win_rate: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    expectancy: float = 0.0
    tp_hit_ratio: float = 0.0
    sl_hit_ratio: float = 0.0
    time_stop_ratio: float = 0.0
    avg_holding_days: float = 0.0
    mfe_median: float = 0.0
    mfe_p25: float = 0.0
    mfe_p75: float = 0.0
    mae_median: float = 0.0
    mae_p25: float = 0.0
    mae_p75: float = 0.0
    is_statistically_significant: bool = False
    sample_size: int = 0


class EdgeMetrics:
    """Compute edge metrics from a list of TradeSimulation objects."""

    def __init__(self, min_sample_size: int = 30) -> None:
        self._min_sample_size = min_sample_size

    @property
    def min_sample_size(self) -> int:
        return self._min_sample_size

    def compute(self, trades: list[TradeSimulation]) -> EdgeMetricsResult:
        """Compute aggregate edge metrics from completed trades.

        Only trades with exit_event != None are considered.
        """
        completed = [t for t in trades if t.exit_event is not None]
        n = len(completed)

        if n == 0:
            return EdgeMetricsResult(
                total_trades=0,
                sample_size=0,
                is_statistically_significant=False,
            )

        returns = [t.return_net for t in completed if t.return_net is not None]
        wins = [r for r in returns if r > 0]
        losses = [r for r in returns if r <= 0]

        win_rate = len(wins) / len(returns) if returns else 0.0
        avg_win = sum(wins) / len(wins) if wins else 0.0
        avg_loss = sum(losses) / len(losses) if losses else 0.0
        loss_rate = 1.0 - win_rate
        expectancy = (win_rate * avg_win) - (loss_rate * abs(avg_loss))

        tp_hits = sum(1 for t in completed if t.exit_event == "TP1_HIT")
        sl_hits = sum(1 for t in completed if t.exit_event == "SL_HIT")
        time_stops = sum(1 for t in completed if t.exit_event == "TIME_STOP")

        holding_days = [t.holding_days for t in completed if t.holding_days is not None]
        avg_holding = sum(holding_days) / len(holding_days) if holding_days else 0.0

        mfe_values = pd.Series([t.mfe for t in completed if t.mfe is not None])
        mae_values = pd.Series([t.mae for t in completed if t.mae is not None])

        return EdgeMetricsResult(
            total_trades=n,
            win_rate=win_rate,
            avg_win=avg_win,
            avg_loss=avg_loss,
            expectancy=expectancy,
            tp_hit_ratio=tp_hits / n if n else 0.0,
            sl_hit_ratio=sl_hits / n if n else 0.0,
            time_stop_ratio=time_stops / n if n else 0.0,
            avg_holding_days=avg_holding,
            mfe_median=float(mfe_values.quantile(0.5)) if not mfe_values.empty else 0.0,
            mfe_p25=float(mfe_values.quantile(0.25)) if not mfe_values.empty else 0.0,
            mfe_p75=float(mfe_values.quantile(0.75)) if not mfe_values.empty else 0.0,
            mae_median=float(mae_values.quantile(0.5)) if not mae_values.empty else 0.0,
            mae_p25=float(mae_values.quantile(0.25)) if not mae_values.empty else 0.0,
            mae_p75=float(mae_values.quantile(0.75)) if not mae_values.empty else 0.0,
            is_statistically_significant=n >= self._min_sample_size,
            sample_size=n,
        )

    def compute_segmented(
        self, trades: list[TradeSimulation], segment_key: str
    ) -> dict[str, EdgeMetricsResult]:
        """Compute metrics per segment (e.g., per entry_setup or technical_context)."""
        groups: dict[str, list[TradeSimulation]] = {}
        for trade in trades:
            value = getattr(trade, segment_key, None) or "UNKNOWN"
            groups.setdefault(str(value), []).append(trade)

        return {key: self.compute(group_trades) for key, group_trades in groups.items()}


__all__ = ["EdgeMetrics", "EdgeMetricsResult"]
