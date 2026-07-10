"""Single source of truth for the BPJS capital and execution profile."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BPJSCapitalProfile:
    """Configurable defaults for small-capital, single-position BPJS trading."""

    capital_min: float = 100_000
    capital_max: float = 1_000_000
    max_concurrent_positions: int = 1
    preferred_position_pct: float = 1.0
    max_position_pct: float = 1.0
    risk_per_trade_pct: float = 0.01
    max_risk_per_trade_pct: float = 0.015
    hard_max_loss_pct: float = 0.02
    default_stop_loss_pct: float = 0.01
    maximum_stop_loss_pct: float = 0.015
    target_tp1_pct: float = 0.02
    target_tp2_pct: float = 0.03
    target_extension_pct: float = 0.04
    maximum_holding_sessions: int = 3
    buy_fee_pct: float = 0.0015
    sell_fee_pct: float = 0.0015
    sell_tax_pct: float = 0.001
    estimated_spread_pct: float = 0.0
    estimated_slippage_pct: float = 0.001
    lot_size: int = 100


DEFAULT_BPJS_PROFILE = BPJSCapitalProfile()


__all__ = ["BPJSCapitalProfile", "DEFAULT_BPJS_PROFILE"]
