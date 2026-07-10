"""CostModel — applies fees and slippage to execution prices."""

from __future__ import annotations

from interday_liquidity_screener.backtest.config import CostModelConfig
from interday_liquidity_screener.trade_plan import round_price_to_tick


class CostModel:
    """Terapkan fee dan slippage pada harga eksekusi.

    Slippage diterapkan dengan arah yang merugikan trader:
    - Entry: harga naik (lebih mahal)
    - Exit: harga turun (lebih murah)

    Harga setelah slippage dibulatkan ke tick-size IDX yang valid.
    """

    def __init__(self, config: CostModelConfig | None = None) -> None:
        self._config = config or CostModelConfig()

    @property
    def config(self) -> CostModelConfig:
        """Return the cost model configuration."""
        return self._config

    def apply_entry_slippage(self, signal_price: float) -> float:
        """Entry price = signal_price * (1 + slippage_pct), rounded ke tick terdekat (ceil).

        Slippage arah merugikan trader: entry lebih mahal.
        Ceil rounding memastikan harga eksekusi >= harga slippage (worst case).
        """
        slipped = signal_price * (1 + self._config.slippage_pct)
        if self._config.snap_to_tick:
            return self.snap_price_to_tick(slipped, mode="ceil")
        return slipped

    def apply_exit_slippage(self, signal_price: float) -> float:
        """Exit price = signal_price * (1 - slippage_pct), rounded ke tick terdekat (floor).

        Slippage arah merugikan trader: exit lebih murah.
        Floor rounding memastikan harga eksekusi <= harga slippage (worst case).
        """
        slipped = signal_price * (1 - self._config.slippage_pct)
        if self._config.snap_to_tick:
            return self.snap_price_to_tick(slipped, mode="floor")
        return slipped

    def calculate_net_return(self, entry_price: float, exit_price: float) -> float:
        """Hitung return bersih setelah fee beli dan fee jual.

        Formula: return_net = (exit_price / entry_price - 1) - fee_buy_pct - fee_sell_pct
        """
        if entry_price <= 0:
            return 0.0
        return_gross = exit_price / entry_price - 1
        return (
            return_gross
            - self._config.fee_buy_pct
            - self._config.fee_sell_pct
            - self._config.sell_tax_pct
            - self._config.estimated_spread_pct
        )

    def calculate_cost_breakdown(self, entry_price: float, exit_price: float, shares: int) -> dict[str, float]:
        """Return fee, tax, spread and slippage components separately."""
        entry_value = float(entry_price) * int(shares)
        exit_value = float(exit_price) * int(shares)
        return {
            "buy_fee": entry_value * self._config.fee_buy_pct,
            "sell_fee": exit_value * self._config.fee_sell_pct,
            "sell_tax": exit_value * self._config.sell_tax_pct,
            "estimated_spread_cost": entry_value * self._config.estimated_spread_pct,
            "estimated_slippage_cost": (entry_value + exit_value) * self._config.slippage_pct,
        }

    def snap_price_to_tick(self, price: float, mode: str = "nearest") -> float:
        """Bulatkan harga ke tick-size IDX yang valid.

        Menggunakan round_price_to_tick dari trade_plan.py.

        Args:
            price: Harga yang akan dibulatkan.
            mode: Mode pembulatan — "ceil", "floor", atau "nearest".

        Returns:
            Harga yang sudah dibulatkan ke tick IDX valid.
        """
        return round_price_to_tick(price, mode=mode)


__all__ = ["CostModel"]
