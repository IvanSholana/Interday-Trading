"""Legacy precomputed-signal replay, named explicitly to avoid overclaiming."""

from __future__ import annotations

import pandas as pd

from interday_liquidity_screener.backtest_interday import InterdayBacktestConfig, simulate_interday_signal


class SignalReplayBacktester:
    """Replay existing Stage-4 signals; this is not an end-to-end backtest."""

    def __init__(self, config: InterdayBacktestConfig | None = None) -> None:
        self.config = config or InterdayBacktestConfig()

    def run(self, signals: pd.DataFrame, price_data: dict[str, pd.DataFrame]) -> pd.DataFrame:
        rows = []
        for _, signal in signals.iterrows():
            ticker = str(signal.get("ticker", ""))
            history = price_data.get(ticker, pd.DataFrame())
            rows.append(simulate_interday_signal(signal, history, self.config))
        return pd.DataFrame(rows)


__all__ = ["SignalReplayBacktester"]
