"""WalkForwardRunner — iterates decision dates and replays pipeline logic."""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from typing import Any, Callable

import pandas as pd

from interday_liquidity_screener.backtest.config import BacktestConfig
from interday_liquidity_screener.backtest.cost_model import CostModel
from interday_liquidity_screener.backtest.simulator import TradeSimulation, TradeSimulator

# Type alias for the pluggable signal generator callback.
# Receives (price_data_up_to_T, ticker, decision_date) and returns
# a list of TradeSimulation objects with entry fields filled.
SignalGenerator = Callable[[pd.DataFrame, str, pd.Timestamp], list[TradeSimulation]]


def _noop_signal_generator(
    df: pd.DataFrame, ticker: str, date: pd.Timestamp
) -> list[TradeSimulation]:
    """Default no-op signal generator that returns no signals."""
    return []


@dataclass
class TradeLedger:
    """Ledger berisi semua hasil Trade_Simulation dan ticker yang di-skip.

    Attributes:
        trades: Daftar TradeSimulation yang telah disimulasikan.
        skipped: Daftar dict berisi ticker yang di-skip beserta alasan.
            Setiap dict memiliki key: ticker, date, reason.
    """

    trades: list[TradeSimulation] = field(default_factory=list)
    skipped: list[dict[str, Any]] = field(default_factory=list)

    def to_dataframe(self) -> pd.DataFrame:
        """Convert trades ke DataFrame untuk output CSV.

        Returns:
            DataFrame dengan semua kolom dari TradeSimulation dataclass.
            Jika tidak ada trades, returns DataFrame kosong dengan kolom yang sesuai.
        """
        if not self.trades:
            # Return empty DataFrame with correct columns
            fields = [f.name for f in dataclasses.fields(TradeSimulation)]
            return pd.DataFrame(columns=fields)

        records = [dataclasses.asdict(trade) for trade in self.trades]
        return pd.DataFrame(records)

    def filter_by_segment(self, key: str, value: str) -> list[TradeSimulation]:
        """Filter trades berdasarkan atribut segment.

        Args:
            key: Nama atribut TradeSimulation (e.g. "entry_setup", "ticker").
            value: Nilai yang dicari.

        Returns:
            List TradeSimulation yang memiliki getattr(trade, key) == value.
        """
        return [
            trade
            for trade in self.trades
            if getattr(trade, key, None) == value
        ]


class WalkForwardRunner:
    """Iterate tanggal keputusan, generate Entry_Signal, serahkan ke TradeSimulator.

    Metode walk-forward: keputusan pada tanggal T hanya menggunakan data
    sampai tanggal T (tanpa melihat masa depan). Hasil diukur pada bar setelah T.
    """

    def __init__(
        self,
        config: BacktestConfig,
        price_data: dict[str, pd.DataFrame],
        signal_generator: SignalGenerator | None = None,
    ) -> None:
        """Initialize WalkForwardRunner.

        Args:
            config: Konfigurasi backtest (tanggal, ticker, time_stop, dll).
            price_data: Dict mapping ticker -> DataFrame OHLCV dengan DatetimeIndex.
            signal_generator: Callable yang menghasilkan sinyal entry.
                Jika None, menggunakan no-op (tidak menghasilkan sinyal).
        """
        self._config = config
        self._price_data = price_data
        self._signal_generator = signal_generator or _noop_signal_generator
        self._cost_model = CostModel(config.cost_model)
        self._simulator = TradeSimulator(
            cost_model=self._cost_model,
            time_stop_days=config.time_stop_days,
        )

    @property
    def config(self) -> BacktestConfig:
        """Return the backtest configuration."""
        return self._config

    @property
    def simulator(self) -> TradeSimulator:
        """Return the trade simulator instance."""
        return self._simulator

    def run(self) -> TradeLedger:
        """Jalankan walk-forward backtest.

        Untuk setiap tanggal T dalam [start_date, end_date]:
          1. Untuk setiap ticker dalam universe:
             a. Slice price_data[ticker] sampai T (walk-forward constraint)
             b. Cek apakah data cukup (>= warmup_days)
             c. Jika tidak cukup: catat skip, lanjut
             d. Jalankan signal_generator untuk mendapat Entry_Signals
             e. Untuk setiap Entry_Signal: simulasi dengan future bars setelah T
          2. Return TradeLedger berisi semua TradeSimulation dan skipped

        Returns:
            TradeLedger dengan hasil semua simulasi trade dan daftar skip.
        """
        ledger = TradeLedger()

        # Determine trading days from union of all dates in price_data
        trading_days = self._get_trading_days()

        if trading_days.empty:
            return ledger

        for decision_date in trading_days:
            for ticker in self._config.universe_tickers:
                # Get price data for this ticker
                ticker_data = self._price_data.get(ticker)
                if ticker_data is None or ticker_data.empty:
                    ledger.skipped.append(
                        {
                            "ticker": ticker,
                            "date": decision_date,
                            "reason": "no_data",
                        }
                    )
                    continue

                # Slice data up to T (walk-forward constraint — Req 1.2)
                data_up_to_t = self._slice_up_to(ticker_data, decision_date)

                # Check warmup requirement (Req 1.7)
                if not self._has_sufficient_data(
                    data_up_to_t, self._config.warmup_days
                ):
                    ledger.skipped.append(
                        {
                            "ticker": ticker,
                            "date": decision_date,
                            "reason": "insufficient_data",
                        }
                    )
                    continue

                # Generate entry signals via pluggable callback
                signals = self._signal_generator(data_up_to_t, ticker, decision_date)

                # Simulate each entry signal (Req 1.1)
                for trade in signals:
                    # Get future bars after T for exit simulation
                    future_bars = ticker_data[ticker_data.index > decision_date]
                    self._simulator.simulate(trade, future_bars)
                    ledger.trades.append(trade)

        return ledger

    def _get_trading_days(self) -> pd.DatetimeIndex:
        """Determine trading days in [start_date, end_date] from price_data.

        Takes the union of all dates across all tickers, then filters
        to the configured [start_date, end_date] range.

        Returns:
            Sorted DatetimeIndex of trading days within the configured range.
        """
        start = pd.Timestamp(self._config.start_date)
        end = pd.Timestamp(self._config.end_date)

        all_dates: set[pd.Timestamp] = set()
        for df in self._price_data.values():
            if df is not None and not df.empty:
                all_dates.update(df.index)

        if not all_dates:
            return pd.DatetimeIndex([])

        # Filter to [start_date, end_date] range
        trading_days = pd.DatetimeIndex(sorted(all_dates))
        mask = (trading_days >= start) & (trading_days <= end)
        return trading_days[mask]

    def _slice_up_to(self, df: pd.DataFrame, date: pd.Timestamp) -> pd.DataFrame:
        """Slice DataFrame hanya sampai tanggal T (inclusive).

        Walk-forward constraint: hanya gunakan data yang tersedia sampai
        tanggal keputusan T. Tidak ada data masa depan yang bocor.

        Args:
            df: DataFrame dengan DatetimeIndex.
            date: Tanggal batas atas (inclusive).

        Returns:
            DataFrame subset dengan index <= date.
        """
        return df[df.index <= date]

    def _has_sufficient_data(self, df: pd.DataFrame, min_points: int = 200) -> bool:
        """Cek apakah data cukup untuk hitung indikator.

        Args:
            df: DataFrame yang sudah di-slice sampai tanggal T.
            min_points: Jumlah data point minimum (default: 200 = warmup_days).

        Returns:
            True jika len(df) >= min_points, False jika tidak.
        """
        return len(df) >= min_points


__all__ = ["SignalGenerator", "TradeLedger", "WalkForwardRunner"]
