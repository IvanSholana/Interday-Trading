"""LiquidityPositionSizer — caps position size based on avg daily value."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LiquiditySizerConfig:
    """Configuration for liquidity-based position sizing."""

    enabled: bool = False
    max_pct_of_avg_value_20d: float = 0.10  # Max 10% of avg daily value


class LiquidityPositionSizer:
    """Caps position size to a fraction of avg daily traded value."""

    def __init__(self, config: LiquiditySizerConfig | None = None) -> None:
        self.config = config or LiquiditySizerConfig()

    def calculate_max_position_value(self, avg_value_20d: float) -> float:
        """Return max position value = avg_value_20d * max_pct."""
        return avg_value_20d * self.config.max_pct_of_avg_value_20d

    def apply_limit(
        self,
        risk_based_value: float,
        capital_based_value: float,
        avg_value_20d: float,
    ) -> tuple[float, str]:
        """Return (final_value, binding_constraint).

        binding_constraint: "RISK", "CAPITAL", or "LIQUIDITY".
        final_value = min(risk_based_value, capital_based_value, liquidity_limit)
        """
        liquidity_limit = self.calculate_max_position_value(avg_value_20d)

        candidates = [
            (risk_based_value, "RISK"),
            (capital_based_value, "CAPITAL"),
            (liquidity_limit, "LIQUIDITY"),
        ]

        final_value, binding_constraint = min(candidates, key=lambda x: x[0])
        return (final_value, binding_constraint)


__all__ = ["LiquidityPositionSizer", "LiquiditySizerConfig"]
