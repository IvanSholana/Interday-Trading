"""TradeSimulator — simulates individual trades from entry to exit."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from interday_liquidity_screener.backtest.cost_model import CostModel


@dataclass
class TradeSimulation:
    """Representasi satu trade dari entry sampai exit.

    Fields wajib diisi saat pembuatan (entry info):
        ticker, entry_date, entry_price, raw_entry_price, stop_loss,
        take_profit_1, take_profit_2.

    Fields diisi oleh TradeSimulator setelah simulasi (exit info):
        exit_date, exit_price, exit_event, return_gross, return_net,
        r_multiple, mfe, mae, holding_days.

    Fields opsional (konteks sinyal):
        entry_setup, technical_context, bandarmology_signal.
    """

    # --- Entry fields (wajib) ---
    ticker: str
    entry_date: pd.Timestamp
    entry_price: float  # Harga setelah slippage
    raw_entry_price: float  # Harga sinyal asli
    stop_loss: float
    take_profit_1: float
    take_profit_2: float

    # --- Exit fields (diisi setelah simulasi) ---
    exit_date: pd.Timestamp | None = None
    exit_price: float | None = None
    exit_event: str | None = None  # "TP1_HIT", "SL_HIT", "TIME_STOP"

    # --- Performance metrics (diisi setelah simulasi) ---
    return_gross: float | None = None
    return_net: float | None = None
    r_multiple: float | None = None
    mfe: float | None = None  # Max Favorable Excursion (%)
    mae: float | None = None  # Max Adverse Excursion (%)
    holding_days: int | None = None

    # --- Signal context (opsional) ---
    entry_setup: str | None = None
    technical_context: str | None = None
    bandarmology_signal: str | None = None
    planned_entry: float | None = None
    actual_entry: float | None = None
    planned_lots: int = 0
    actual_lots: int = 0
    actual_risk_amount: float = 0.0


class TradeSimulator:
    """Simulasi satu trade dari entry sampai exit.

    Evaluasi dilakukan bar demi bar secara deterministik:
    1. Untuk setiap bar (sampai time_stop_days):
       - Track MFE dan MAE
       - Cek SL hit (low <= stop_loss)
       - Cek TP1 hit (high >= take_profit_1)
       - Jika keduanya terpenuhi pada bar yang sama → SL_HIT (konservatif)
       - Jika time_stop tercapai tanpa hit → TIME_STOP di close bar terakhir
    2. Apply exit slippage pada exit price
    3. Hitung return_gross, return_net, r_multiple, holding_days
    """

    def __init__(self, cost_model: CostModel, time_stop_days: int = 10) -> None:
        """Initialize TradeSimulator.

        Args:
            cost_model: Model biaya transaksi dan slippage.
            time_stop_days: Jumlah hari maksimum holding sebelum time-stop.
        """
        self._cost_model = cost_model
        self._time_stop_days = time_stop_days

    @property
    def cost_model(self) -> CostModel:
        """Return the cost model."""
        return self._cost_model

    @property
    def time_stop_days(self) -> int:
        """Return the time-stop limit in trading days."""
        return self._time_stop_days

    def simulate(
        self, trade: TradeSimulation, future_bars: pd.DataFrame
    ) -> TradeSimulation:
        """Simulasi satu trade bar demi bar.

        Args:
            trade: TradeSimulation dengan field entry terisi.
            future_bars: DataFrame OHLCV bar-bar setelah entry.
                         Kolom: open, high, low, close, volume.
                         Index: DatetimeIndex berurutan kronologis.

        Returns:
            TradeSimulation dengan semua field exit dan metrik terisi.
        """
        entry_price = trade.entry_price
        stop_loss = trade.stop_loss
        take_profit = trade.take_profit_1

        # Limit bars to time_stop_days
        bars_to_evaluate = future_bars.iloc[: self._time_stop_days]

        if bars_to_evaluate.empty:
            # No future bars — immediate time-stop at entry
            trade.exit_date = trade.entry_date
            trade.exit_price = self._cost_model.apply_exit_slippage(entry_price)
            trade.exit_event = "TIME_STOP"
            trade.mfe = 0.0
            trade.mae = 0.0
            trade.holding_days = 0
            trade.return_gross = trade.exit_price / entry_price - 1
            trade.return_net = self._cost_model.calculate_net_return(
                entry_price, trade.exit_price
            )
            trade.r_multiple = self._calculate_r_multiple(
                entry_price, trade.exit_price, stop_loss
            )
            return trade

        # Track MFE and MAE across all evaluated bars
        mfe = 0.0
        mae = 0.0
        exit_event: str | None = None
        exit_date: pd.Timestamp | None = None
        raw_exit_price: float | None = None

        for i, (bar_date, bar) in enumerate(bars_to_evaluate.iterrows()):
            bar_open = float(bar["open"])
            bar_high = float(bar["high"])
            bar_low = float(bar["low"])
            bar_close = float(bar["close"])

            # Update MFE and MAE (track up to and including exit bar)
            bar_mfe = (bar_high - entry_price) / entry_price
            bar_mae = (entry_price - bar_low) / entry_price
            mfe = max(mfe, bar_mfe)
            mae = max(mae, bar_mae)

            # Check exit conditions
            sl_hit = bar_low <= stop_loss
            tp_hit = bar_high >= take_profit

            if sl_hit and tp_hit:
                # Conservative tie-breaking: choose SL (Req 1.4)
                exit_event = "SL_HIT"
                exit_date = pd.Timestamp(bar_date)
                raw_exit_price = min(stop_loss, bar_open)
                break
            elif sl_hit:
                exit_event = "SL_HIT"
                exit_date = pd.Timestamp(bar_date)
                # A gap below the stop fills at the opening price, not at the
                # stale planned stop level.
                raw_exit_price = min(stop_loss, bar_open)
                break
            elif tp_hit:
                exit_event = "TP1_HIT"
                exit_date = pd.Timestamp(bar_date)
                raw_exit_price = take_profit
                break

        # If no SL/TP hit within time_stop_days → TIME_STOP
        if exit_event is None:
            exit_event = "TIME_STOP"
            last_bar = bars_to_evaluate.iloc[-1]
            exit_date = pd.Timestamp(bars_to_evaluate.index[-1])
            raw_exit_price = float(last_bar["close"])

        # Apply exit slippage to raw exit price
        exit_price_final = self._cost_model.apply_exit_slippage(raw_exit_price)

        # Calculate holding days (number of bars evaluated up to exit)
        if exit_event == "TIME_STOP":
            holding_days = len(bars_to_evaluate)
        else:
            # Find the index of the exit bar
            holding_days = (
                bars_to_evaluate.index.get_loc(exit_date) + 1  # type: ignore[arg-type]
            )

        # Calculate returns
        return_gross = exit_price_final / entry_price - 1
        return_net = self._cost_model.calculate_net_return(entry_price, exit_price_final)
        r_multiple = self._calculate_r_multiple(entry_price, exit_price_final, stop_loss)

        # Fill trade fields
        trade.exit_date = exit_date
        trade.exit_price = exit_price_final
        trade.exit_event = exit_event
        trade.return_gross = return_gross
        trade.return_net = return_net
        trade.r_multiple = r_multiple
        trade.mfe = mfe
        trade.mae = mae
        trade.holding_days = holding_days

        return trade

    @staticmethod
    def _calculate_r_multiple(
        entry_price: float, exit_price: float, stop_loss: float
    ) -> float:
        """Hitung R-multiple: (exit - entry) / (entry - stop_loss).

        R = 1.0 berarti profit sama dengan risiko awal.
        R = -1.0 berarti loss sama dengan risiko awal (SL hit sempurna).

        Returns 0.0 jika risk = 0 (entry == stop_loss) untuk menghindari division by zero.
        """
        risk = entry_price - stop_loss
        if risk == 0:
            return 0.0
        return (exit_price - entry_price) / risk


__all__ = ["TradeSimulation", "TradeSimulator"]
