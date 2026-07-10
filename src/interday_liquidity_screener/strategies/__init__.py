"""Explicit strategy contracts for hybrid candidate evaluation."""

from .base import StrategyDefinition, StrategyEvaluation
from .registry import evaluate_strategy

__all__ = ["StrategyDefinition", "StrategyEvaluation", "evaluate_strategy"]
