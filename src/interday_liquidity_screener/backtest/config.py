"""BacktestConfig and CostModelConfig dataclasses."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime

_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DEFAULT_TIME_STOP_DAYS = 10


@dataclass(frozen=True)
class CostModelConfig:
    """Konfigurasi model biaya transaksi dan slippage.

    Attributes:
        fee_buy_pct: Persentase fee beli (default 0.15% IDX).
        fee_sell_pct: Persentase fee jual termasuk pajak (default 0.25% IDX).
        slippage_pct: Persentase slippage default.
        snap_to_tick: Apakah harga hasil slippage harus valid tick IDX.
    """

    fee_buy_pct: float = 0.0015
    fee_sell_pct: float = 0.0025
    sell_tax_pct: float = 0.0
    estimated_spread_pct: float = 0.0
    slippage_pct: float = 0.001
    snap_to_tick: bool = True


@dataclass(frozen=True)
class BacktestConfig:
    """Konfigurasi utama untuk backtest engine walk-forward.

    Attributes:
        start_date: Tanggal mulai backtest (format YYYY-MM-DD).
        end_date: Tanggal akhir backtest (format YYYY-MM-DD).
        universe_tickers: Daftar ticker yang akan di-backtest.
        time_stop_days: Jumlah hari maksimum holding sebelum time-stop.
        cost_model: Konfigurasi model biaya.
        min_sample_size: Minimum sampel untuk signifikansi statistik.
        warmup_days: Hari data minimum sebelum sinyal pertama.
        output_dir: Direktori output hasil backtest.
    """

    start_date: str
    end_date: str
    universe_tickers: list[str]
    time_stop_days: int = _DEFAULT_TIME_STOP_DAYS
    cost_model: CostModelConfig = field(default_factory=CostModelConfig)
    min_sample_size: int = 30
    warmup_days: int = 200
    output_dir: str = "data/output/backtest"
    initial_capital: float = 1_000_000
    random_seed: int = 42
    feature_version: str = "technical-v1"
    strategy_version: str = "bpjs-v1"

    def __post_init__(self) -> None:
        """Validate fields after initialization."""
        if self.initial_capital <= 0:
            raise ValueError("initial_capital must be positive")
        # Validate time_stop_days: reject zero/negative, fallback to default
        if self.time_stop_days <= 0:
            object.__setattr__(self, "time_stop_days", _DEFAULT_TIME_STOP_DAYS)

        # Validate date format
        _validate_date_format(self.start_date, "start_date")
        _validate_date_format(self.end_date, "end_date")

        # Validate start_date < end_date
        start = datetime.strptime(self.start_date, "%Y-%m-%d")
        end = datetime.strptime(self.end_date, "%Y-%m-%d")
        if start >= end:
            raise ValueError(
                f"start_date ({self.start_date}) must be before end_date ({self.end_date})"
            )


def _validate_date_format(value: str, field_name: str) -> None:
    """Validate that a date string matches YYYY-MM-DD format and is a real date."""
    if not _DATE_PATTERN.match(value):
        raise ValueError(
            f"{field_name} must be in YYYY-MM-DD format, got '{value}'"
        )
    # Also validate it's a real calendar date
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        raise ValueError(
            f"{field_name} is not a valid calendar date: '{value}'"
        )


__all__ = ["BacktestConfig", "CostModelConfig"]
