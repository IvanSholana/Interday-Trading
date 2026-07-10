from __future__ import annotations

from dataclasses import dataclass

from interday_liquidity_screener.constants import WatchlistStatus


@dataclass(frozen=True)
class StrategyDefinition:
    name: str
    eligibility_gate: str
    setup_definition: str
    entry_trigger: str
    invalidation_rule: str
    stop_rule: str
    target_rule: str
    time_stop_sessions: int
    allowed_market_regimes: tuple[str, ...]
    required_features: tuple[str, ...]
    optional_features: tuple[str, ...]


@dataclass(frozen=True)
class StrategyEvaluation:
    definition: StrategyDefinition
    eligible: bool
    trigger_touched: bool
    status_cap: WatchlistStatus
    reasons: tuple[str, ...] = ()


def present(row: dict, field: str) -> bool:
    value = row.get(field)
    return value is not None and str(value) != "nan"


__all__ = ["StrategyDefinition", "StrategyEvaluation", "present"]
