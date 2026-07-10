"""BPJS ranking separated into alpha, execution, risk, and confidence axes."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RankingBreakdown:
    alpha_score: float
    execution_quality_score: float
    risk_feasibility_score: float
    confidence_score: float
    ranking_score: float
    estimated_tp_probability: float | None = None


def _clip(value: float) -> float:
    return round(max(0.0, min(100.0, float(value))), 2)


def rank_bpjs_candidate(*, technical: float, smart_money: float, price_extension: float,
                        market_context: float, liquidity: float, orderbook: float,
                        net_profit_feasibility: float, risk_feasibility: float,
                        data_quality: float, estimated_tp_probability: float | None = None) -> RankingBreakdown:
    alpha = _clip(0.50 * technical + 0.25 * smart_money + 0.15 * price_extension + 0.10 * market_context)
    execution = _clip(0.35 * liquidity + 0.35 * orderbook + 0.30 * net_profit_feasibility)
    risk = _clip(risk_feasibility)
    confidence = _clip(data_quality)
    # Risk feasibility is a gate/status axis, not directional alpha.
    probability = None
    if estimated_tp_probability is not None:
        probability = max(0.0, min(1.0, float(estimated_tp_probability)))
        ranking = _clip(0.40 * alpha + 0.30 * execution + 0.15 * confidence + 0.15 * probability * 100)
    else:
        ranking = _clip(0.45 * alpha + 0.35 * execution + 0.20 * confidence)
    return RankingBreakdown(alpha, execution, risk, confidence, ranking, probability)


__all__ = ["RankingBreakdown", "rank_bpjs_candidate"]
