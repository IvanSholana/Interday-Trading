from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import pandas as pd

from .constants import WatchlistStatus
from .hybrid_config import FeesConfig


POSITIVE_STATUSES = {
    WatchlistStatus.EXECUTION_READY,
    WatchlistStatus.EXECUTION_CANDIDATE,
    WatchlistStatus.EXECUTION_DRAFT,
    WatchlistStatus.NEED_ORDERBOOK,
}

WATCH_STATUSES = {
    WatchlistStatus.READY_SOON,
    WatchlistStatus.EARLY_WATCH,
}

REJECTION_STATUSES = {
    WatchlistStatus.DANGER_CHASING,
    WatchlistStatus.DISTRIBUTION_WARNING,
    WatchlistStatus.ORDERBOOK_WEAK,
    WatchlistStatus.ORDERBOOK_REJECT,
    WatchlistStatus.LOW_LIQUIDITY,
    WatchlistStatus.NET_PROFIT_NOT_WORTH_IT,
    WatchlistStatus.TOO_EXPENSIVE_FOR_CAPITAL,
    WatchlistStatus.RISK_REWARD_BAD,
    WatchlistStatus.DATA_INSUFFICIENT,
    WatchlistStatus.SKIP,
}

STATUS_PRIORITY = {
    WatchlistStatus.EXECUTION_READY: 0,
    WatchlistStatus.EXECUTION_DRAFT: 1,
    WatchlistStatus.EXECUTION_CANDIDATE: 2,
    WatchlistStatus.NEED_ORDERBOOK: 3,
    WatchlistStatus.READY_SOON: 4,
    WatchlistStatus.EARLY_WATCH: 5,
}


@dataclass(frozen=True)
class RecommendationPolicy:
    version: str = "2026-07-professional-mvp-v1"
    min_risk_reward: float = 1.2
    min_expected_gross_profit_idr: float = 5_000.0
    min_expected_net_profit_idr: float = 5_000.0
    max_portfolio_loss_pct: float = 0.02
    execution_ready_a_confidence: float = 80.0
    positive_b_confidence: float = 65.0
    watch_c_confidence: float = 45.0
    score_weight: float = 0.55
    max_rr_component_input: float = 3.0
    rr_component_weight: float = 5.0
    hard_flag_penalty: float = 25.0
    rejection_status_penalty: float = 20.0
    live_confirmation_penalty: float = 8.0
    soft_flag_penalty: float = 4.0

    def to_dict(self) -> dict[str, float | str]:
        return asdict(self)


DEFAULT_RECOMMENDATION_POLICY = RecommendationPolicy()
RECOMMENDATION_SCHEMA_VERSION = "recommendation-pack-v1"


class Readiness:
    READY = "READY"
    NEEDS_LIVE_CONFIRMATION = "NEEDS_LIVE_CONFIRMATION"
    WATCH_ONLY = "WATCH_ONLY"
    REJECTED_OR_LOW_PRIORITY = "REJECTED_OR_LOW_PRIORITY"


class ExecutionDecision:
    REVIEW_BUY = "REVIEW_BUY"
    WAIT_CONFIRMATION = "WAIT_CONFIRMATION"
    WATCH_ONLY = "WATCH_ONLY"
    AVOID = "AVOID"


class PortfolioDecision:
    WITHIN_BUDGET_REVIEW = "WITHIN_BUDGET_REVIEW"
    PICK_PRIMARY_ONLY_OR_REDUCE_SIZE = "PICK_PRIMARY_ONLY_OR_REDUCE_SIZE"
    REDUCE_RISK_BEFORE_EXECUTION = "REDUCE_RISK_BEFORE_EXECUTION"
    NO_PORTFOLIO_ACTION = "NO_PORTFOLIO_ACTION"


class AuditFlag:
    UNKNOWN_STATUS = "UNKNOWN_STATUS"
    NEEDS_LIVE_CONFIRMATION = "NEEDS_LIVE_CONFIRMATION"
    WATCH_ONLY = "WATCH_ONLY"
    INCOMPLETE_PRICE_PLAN = "INCOMPLETE_PRICE_PLAN"
    TP_OUTSIDE_USER_CAP = "TP_OUTSIDE_USER_CAP"
    RISK_REWARD_BELOW_MINIMUM = "RISK_REWARD_BELOW_MINIMUM"
    NO_AFFORDABLE_LOT = "NO_AFFORDABLE_LOT"
    HIGH_CAPITAL_CONCENTRATION = "HIGH_CAPITAL_CONCENTRATION"
    POSITION_REDUCED_TO_CAP = "POSITION_REDUCED_TO_CAP"
    LOW_GROSS_PROFIT = "LOW_GROSS_PROFIT"
    LOW_NET_PROFIT_AFTER_COSTS = "LOW_NET_PROFIT_AFTER_COSTS"


class PortfolioFlag:
    NO_SELECTED_CANDIDATES = "NO_SELECTED_CANDIDATES"
    SHORTLIST_OVER_ALLOCATED = "SHORTLIST_OVER_ALLOCATED"
    PORTFOLIO_MAX_LOSS_ABOVE_2PCT = "PORTFOLIO_MAX_LOSS_ABOVE_2PCT"


HARD_AUDIT_FLAGS = {
    AuditFlag.INCOMPLETE_PRICE_PLAN,
    AuditFlag.NO_AFFORDABLE_LOT,
    AuditFlag.TP_OUTSIDE_USER_CAP,
    AuditFlag.LOW_NET_PROFIT_AFTER_COSTS,
}

COLUMN_ALIASES = {
    "symbol": ("symbol", "ticker", "yahoo_ticker"),
    "name": ("name", "symbol", "ticker"),
    "entry_price": ("entry_price", "entry_trigger_price", "raw_entry_price", "close"),
    "tp1_price": ("tp1_price", "take_profit_1", "raw_take_profit_1"),
    "stop_loss_price": ("stop_loss_price", "stop_loss", "raw_stop_loss"),
    "position_value": ("position_value", "executable_position_value", "theoretical_position_value"),
    "target_tp_pct": ("target_tp_pct", "reward_pct_tp1"),
    "stop_loss_pct": ("stop_loss_pct", "risk_pct"),
    "risk_reward_ratio": ("risk_reward_ratio", "risk_reward_tp1"),
    "lots": ("affordable_lot", "position_size_lots", "executable_position_size_lots", "theoretical_position_size_lots"),
}


@dataclass(frozen=True)
class CandidateRecommendation:
    symbol: str
    name: str
    final_status: str
    readiness: str
    execution_decision: str
    final_score: float
    rank: int | None
    entry_price: float | None
    tp1_price: float | None
    stop_loss_price: float | None
    target_tp_pct: float | None
    stop_loss_pct: float | None
    risk_reward_ratio: float | None
    position_value: float
    lots: int
    capital_usage_pct: float
    expected_gross_profit: float | None
    estimated_buy_fee: float | None
    estimated_sell_fee: float | None
    estimated_slippage: float | None
    expected_net_profit: float | None
    max_loss_amount: float | None
    confidence_score: float
    confidence_components: dict[str, float]
    decision_grade: str
    audit_flags: list[str]
    primary_reason: str
    next_action: str
    warnings: str
    skip_reasons: str


@dataclass(frozen=True)
class RecommendationPack:
    run_id: str
    schema_version: str
    policy_version: str
    policy: dict[str, float | str]
    capital: float
    max_tp_pct: float
    max_position_pct: float
    portfolio_decision: str
    portfolio_flags: list[str]
    total_selected_position_value: float
    total_selected_capital_usage_pct: float
    total_selected_expected_gross_profit: float | None
    total_selected_expected_net_profit: float | None
    total_selected_max_loss_amount: float | None
    total_selected_max_loss_pct: float | None
    selected_count: int
    ready_count: int
    draft_count: int
    watch_count: int
    rejected_count: int
    excluded_by_tp_limit_count: int
    data_quality: dict[str, int]
    primary: CandidateRecommendation | None
    candidates: list[CandidateRecommendation]
    next_action: str
    caveat: str

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        return data


def _data_quality_summary(rows: list[CandidateRecommendation], selected_count: int) -> dict[str, int]:
    total_rows = len(rows)
    complete_price_plan = sum(
        1
        for item in rows
        if item.entry_price is not None and item.tp1_price is not None and item.stop_loss_price is not None
    )
    return {
        "total_rows": total_rows,
        "selected_count": selected_count,
        "complete_price_plan_count": complete_price_plan,
        "missing_price_plan_count": total_rows - complete_price_plan,
        "affordable_lot_count": sum(1 for item in rows if item.lots > 0),
        "unknown_status_count": sum(1 for item in rows if item.final_status and _status(item.final_status) is None),
    }


def _num(row: pd.Series, column: str) -> float | None:
    if column not in row:
        return None
    value = pd.to_numeric(pd.Series([row[column]]), errors="coerce").iloc[0]
    if pd.isna(value):
        return None
    return float(value)


def _num_any(row: pd.Series, logical_column: str) -> float | None:
    for column in COLUMN_ALIASES.get(logical_column, (logical_column,)):
        value = _num(row, column)
        if value is not None:
            return value
    return None


def _text(row: pd.Series, column: str) -> str:
    value = row.get(column, "")
    if value is None or pd.isna(value):
        return ""
    return str(value)


def _text_any(row: pd.Series, logical_column: str) -> str:
    for column in COLUMN_ALIASES.get(logical_column, (logical_column,)):
        value = _text(row, column)
        if value:
            return value
    return ""


def _status(value: Any) -> WatchlistStatus | None:
    try:
        return WatchlistStatus(str(value))
    except ValueError:
        return None


def _readiness(status: WatchlistStatus | None) -> str:
    if status == WatchlistStatus.EXECUTION_READY:
        return Readiness.READY
    if status in {WatchlistStatus.EXECUTION_DRAFT, WatchlistStatus.EXECUTION_CANDIDATE, WatchlistStatus.NEED_ORDERBOOK}:
        return Readiness.NEEDS_LIVE_CONFIRMATION
    if status in WATCH_STATUSES:
        return Readiness.WATCH_ONLY
    return Readiness.REJECTED_OR_LOW_PRIORITY


def _next_action(status: WatchlistStatus | None) -> str:
    if status == WatchlistStatus.EXECUTION_READY:
        return "Eligible for execution review; still confirm price has not gapped above the entry zone."
    if status == WatchlistStatus.EXECUTION_DRAFT:
        return "Run Fase Pagi/orderbook confirmation before execution; do not chase if opening price gaps above the plan."
    if status == WatchlistStatus.EXECUTION_CANDIDATE:
        return "Review live orderbook and last price; execute only if spread/depth and entry zone remain supportive."
    if status == WatchlistStatus.NEED_ORDERBOOK:
        return "Resume the run in Fase Pagi to resolve orderbook status."
    if status in WATCH_STATUSES:
        return "Keep on radar; wait for stronger setup or live validation before planning an entry."
    return "Do not execute from this run unless a later scan changes the status."


def _audit_flags(
    status: WatchlistStatus | None,
    entry: float | None,
    tp1: float | None,
    stop: float | None,
    tp_pct: float | None,
    max_tp_pct: float,
    rr: float | None,
    lots: int,
    usage: float,
    expected_profit: float | None,
    expected_net_profit: float | None,
    position_capped: bool,
) -> list[str]:
    flags: list[str] = []
    if status is None:
        flags.append(AuditFlag.UNKNOWN_STATUS)
    elif status in REJECTION_STATUSES:
        flags.append(f"STATUS_{status.value}")
    elif status in {WatchlistStatus.EXECUTION_DRAFT, WatchlistStatus.EXECUTION_CANDIDATE, WatchlistStatus.NEED_ORDERBOOK}:
        flags.append(AuditFlag.NEEDS_LIVE_CONFIRMATION)
    elif status in WATCH_STATUSES:
        flags.append(AuditFlag.WATCH_ONLY)
    if entry is None or tp1 is None or stop is None:
        flags.append(AuditFlag.INCOMPLETE_PRICE_PLAN)
    if tp_pct is not None and (tp_pct <= 0 or tp_pct > max_tp_pct):
        flags.append(AuditFlag.TP_OUTSIDE_USER_CAP)
    if rr is not None and rr < DEFAULT_RECOMMENDATION_POLICY.min_risk_reward:
        flags.append(AuditFlag.RISK_REWARD_BELOW_MINIMUM)
    if lots < 1:
        flags.append(AuditFlag.NO_AFFORDABLE_LOT)
    if usage > 0.95:
        flags.append(AuditFlag.HIGH_CAPITAL_CONCENTRATION)
    if position_capped:
        flags.append(AuditFlag.POSITION_REDUCED_TO_CAP)
    if expected_profit is not None and expected_profit < DEFAULT_RECOMMENDATION_POLICY.min_expected_gross_profit_idr:
        flags.append(AuditFlag.LOW_GROSS_PROFIT)
    if expected_net_profit is not None and expected_net_profit < DEFAULT_RECOMMENDATION_POLICY.min_expected_net_profit_idr:
        flags.append(AuditFlag.LOW_NET_PROFIT_AFTER_COSTS)
    return flags


def _confidence_components(status: WatchlistStatus | None, final_score: float, rr: float | None, flags: list[str]) -> dict[str, float]:
    status_base = {
        WatchlistStatus.EXECUTION_READY: 30.0,
        WatchlistStatus.EXECUTION_DRAFT: 18.0,
        WatchlistStatus.EXECUTION_CANDIDATE: 16.0,
        WatchlistStatus.NEED_ORDERBOOK: 14.0,
        WatchlistStatus.READY_SOON: 10.0,
        WatchlistStatus.EARLY_WATCH: 6.0,
    }.get(status, 0.0)
    policy = DEFAULT_RECOMMENDATION_POLICY
    score_component = max(0.0, min(final_score, 100.0)) * policy.score_weight
    rr_component = max(0.0, min(rr or 0.0, policy.max_rr_component_input)) * policy.rr_component_weight
    penalty = 0.0
    for flag in flags:
        if flag in {AuditFlag.INCOMPLETE_PRICE_PLAN, AuditFlag.NO_AFFORDABLE_LOT, AuditFlag.TP_OUTSIDE_USER_CAP}:
            penalty += policy.hard_flag_penalty
        elif flag.startswith("STATUS_"):
            penalty += policy.rejection_status_penalty
        elif flag in {AuditFlag.NEEDS_LIVE_CONFIRMATION, AuditFlag.WATCH_ONLY}:
            penalty += policy.live_confirmation_penalty
        else:
            penalty += policy.soft_flag_penalty
    final_confidence = round(max(0.0, min(100.0, status_base + score_component + rr_component - penalty)), 1)
    return {
        "status_base": round(status_base, 1),
        "score_component": round(score_component, 1),
        "risk_reward_component": round(rr_component, 1),
        "audit_penalty": round(penalty, 1),
        "final_confidence": final_confidence,
    }


def _decision_grade(status: WatchlistStatus | None, confidence: float, flags: list[str]) -> str:
    if status in REJECTION_STATUSES or HARD_AUDIT_FLAGS.intersection(flags):
        return "D"
    policy = DEFAULT_RECOMMENDATION_POLICY
    if status == WatchlistStatus.EXECUTION_READY and confidence >= policy.execution_ready_a_confidence:
        return "A"
    if status in POSITIVE_STATUSES and confidence >= policy.positive_b_confidence:
        return "B"
    if status in POSITIVE_STATUSES | WATCH_STATUSES and confidence >= policy.watch_c_confidence:
        return "C"
    return "D"


def _execution_decision(status: WatchlistStatus | None, readiness: str, grade: str, flags: list[str]) -> str:
    if status in REJECTION_STATUSES or HARD_AUDIT_FLAGS.intersection(flags):
        return ExecutionDecision.AVOID
    if readiness == Readiness.READY and grade in {"A", "B"}:
        return ExecutionDecision.REVIEW_BUY
    if readiness == Readiness.NEEDS_LIVE_CONFIRMATION:
        return ExecutionDecision.WAIT_CONFIRMATION
    if readiness == Readiness.WATCH_ONLY:
        return ExecutionDecision.WATCH_ONLY
    return ExecutionDecision.AVOID


def _primary_reason(row: pd.Series, status: WatchlistStatus | None, tp_pct: float | None, max_tp_pct: float) -> str:
    explanation = _text(row, "explanation")
    if explanation:
        return explanation
    if status in POSITIVE_STATUSES:
        tp_note = f" TP target is within the {max_tp_pct:.1%} cap." if tp_pct is not None and tp_pct <= max_tp_pct else ""
        return f"{status.value} with acceptable ranking and a complete draft risk plan.{tp_note}"
    if status in WATCH_STATUSES:
        return f"{status.value}; setup is improving but is not an execution signal yet."
    if status in REJECTION_STATUSES:
        return f"{status.value}; risk or data gates rejected the candidate."
    return "Status is not recognized by the current recommendation layer."


def _position_value_for_cap(position_value: float, entry: float | None, capital: float, max_position_pct: float) -> tuple[float, bool]:
    if not entry or entry <= 0 or capital <= 0:
        return 0.0, False

    lot_value = entry * 100
    position_cap = capital * max_position_pct
    target_value = position_value if position_value > 0 else position_cap
    capped = position_value > 0 and target_value > position_cap
    if target_value > position_cap:
        target_value = position_cap
    return max(0.0, int(target_value // lot_value) * lot_value), capped


def _cost_adjusted_profit(
    row: pd.Series,
    entry: float | None,
    tp1: float | None,
    lots: int,
    position_value: float,
    position_capped: bool,
    fees: FeesConfig,
) -> tuple[float | None, float | None, float | None, float | None, float | None]:
    expected_gross_profit = None
    if entry and tp1 and lots > 0:
        expected_gross_profit = max(0.0, (tp1 - entry) * lots * 100)

    row_net_profit = _num(row, "net_profit_after_fee")
    row_buy_fee = _num(row, "estimated_buy_fee")
    row_sell_fee = _num(row, "estimated_sell_fee")
    row_slippage = _num(row, "estimated_slippage")
    if not position_capped and row_net_profit is not None:
        return expected_gross_profit, row_buy_fee, row_sell_fee, row_slippage, row_net_profit

    if expected_gross_profit is None or not tp1 or lots <= 0:
        return expected_gross_profit, row_buy_fee, row_sell_fee, row_slippage, row_net_profit

    exit_value = tp1 * lots * 100
    buy_fee = max(position_value * float(fees.buy_fee_pct), float(fees.minimum_buy_fee) if position_value else 0.0)
    sell_fee = max(
        exit_value * (float(fees.sell_fee_pct) + float(fees.sell_tax_pct)),
        float(fees.minimum_sell_fee) if position_value else 0.0,
    )
    slippage = position_value * float(fees.slippage_pct_default) + exit_value * float(fees.slippage_pct_default)
    net_profit = expected_gross_profit - buy_fee - sell_fee - slippage
    return expected_gross_profit, buy_fee, sell_fee, slippage, net_profit


def _portfolio_flags(total_usage: float, total_loss_pct: float | None, selected_count: int) -> list[str]:
    flags: list[str] = []
    if selected_count == 0:
        flags.append(PortfolioFlag.NO_SELECTED_CANDIDATES)
    if total_usage > 1.0:
        flags.append(PortfolioFlag.SHORTLIST_OVER_ALLOCATED)
    if total_loss_pct is not None and total_loss_pct > DEFAULT_RECOMMENDATION_POLICY.max_portfolio_loss_pct:
        flags.append(PortfolioFlag.PORTFOLIO_MAX_LOSS_ABOVE_2PCT)
    return flags


def _portfolio_decision(flags: list[str]) -> str:
    if PortfolioFlag.NO_SELECTED_CANDIDATES in flags:
        return PortfolioDecision.NO_PORTFOLIO_ACTION
    if PortfolioFlag.SHORTLIST_OVER_ALLOCATED in flags:
        return PortfolioDecision.PICK_PRIMARY_ONLY_OR_REDUCE_SIZE
    if PortfolioFlag.PORTFOLIO_MAX_LOSS_ABOVE_2PCT in flags:
        return PortfolioDecision.REDUCE_RISK_BEFORE_EXECUTION
    return PortfolioDecision.WITHIN_BUDGET_REVIEW


def _build_candidate(row: pd.Series, capital: float, max_tp_pct: float, max_position_pct: float) -> CandidateRecommendation:
    status = _status(row.get("final_status"))
    symbol = _text_any(row, "symbol")
    name = _text_any(row, "name") or symbol
    entry = _num_any(row, "entry_price")
    tp1 = _num_any(row, "tp1_price")
    stop = _num_any(row, "stop_loss_price")
    score = _num(row, "final_score") or 0.0
    rank_value = _num(row, "rank")
    rank = int(rank_value) if rank_value is not None else None
    source_position_value = _num_any(row, "position_value") or 0.0
    position_value, position_capped = _position_value_for_cap(source_position_value, entry, capital, max_position_pct)
    derived_lots = int(position_value // (entry * 100)) if entry and entry > 0 else 0
    lots = derived_lots or int(_num_any(row, "lots") or 0)
    tp_pct = (tp1 - entry) / entry if entry and tp1 else _num_any(row, "target_tp_pct")
    sl_pct = (entry - stop) / entry if entry and stop else _num_any(row, "stop_loss_pct")
    rr = _num_any(row, "risk_reward_ratio")
    if rr is None and tp_pct is not None and sl_pct and sl_pct > 0:
        rr = tp_pct / sl_pct
    expected_profit, buy_fee, sell_fee, slippage, net_profit = _cost_adjusted_profit(
        row,
        entry,
        tp1,
        lots,
        position_value,
        position_capped,
        FeesConfig(),
    )
    max_loss = None
    if entry and stop and lots > 0:
        max_loss = max(0.0, (entry - stop) * lots * 100)
    usage = position_value / capital if capital > 0 else 0.0
    audit_flags = _audit_flags(
        status,
        entry,
        tp1,
        stop,
        tp_pct,
        max_tp_pct,
        rr,
        lots,
        usage,
        expected_profit,
        net_profit,
        position_capped,
    )
    confidence_components = _confidence_components(status, score, rr, audit_flags)
    confidence = confidence_components["final_confidence"]
    grade = _decision_grade(status, confidence, audit_flags)
    readiness = _readiness(status)

    return CandidateRecommendation(
        symbol=symbol,
        name=name,
        final_status=status.value if status else _text(row, "final_status"),
        readiness=readiness,
        execution_decision=_execution_decision(status, readiness, grade, audit_flags),
        final_score=score,
        rank=rank,
        entry_price=entry,
        tp1_price=tp1,
        stop_loss_price=stop,
        target_tp_pct=tp_pct,
        stop_loss_pct=sl_pct,
        risk_reward_ratio=rr,
        position_value=position_value,
        lots=lots,
        capital_usage_pct=usage,
        expected_gross_profit=expected_profit,
        estimated_buy_fee=buy_fee,
        estimated_sell_fee=sell_fee,
        estimated_slippage=slippage,
        expected_net_profit=net_profit,
        max_loss_amount=max_loss,
        confidence_score=confidence,
        confidence_components=confidence_components,
        decision_grade=grade,
        audit_flags=audit_flags,
        primary_reason=_primary_reason(row, status, tp_pct, max_tp_pct),
        next_action=_next_action(status),
        warnings=_text(row, "warnings"),
        skip_reasons=_text(row, "skip_reasons"),
    )


def _sort_key(candidate: CandidateRecommendation) -> tuple[int, float, float, float]:
    status = _status(candidate.final_status)
    priority = STATUS_PRIORITY.get(status, 99)
    rr = candidate.risk_reward_ratio or 0.0
    return (priority, -candidate.final_score, -rr, -candidate.capital_usage_pct)


def build_recommendation_pack(
    watchlist: pd.DataFrame,
    run_id: str,
    capital: float,
    max_tp_pct: float = 0.05,
    max_position_pct: float = 1.0,
    limit: int = 5,
) -> RecommendationPack:
    if watchlist.empty:
        return RecommendationPack(
            run_id=run_id,
            schema_version=RECOMMENDATION_SCHEMA_VERSION,
            policy_version=DEFAULT_RECOMMENDATION_POLICY.version,
            policy=DEFAULT_RECOMMENDATION_POLICY.to_dict(),
            capital=capital,
            max_tp_pct=max_tp_pct,
            max_position_pct=max_position_pct,
            portfolio_decision=PortfolioDecision.NO_PORTFOLIO_ACTION,
            portfolio_flags=[PortfolioFlag.NO_SELECTED_CANDIDATES],
            total_selected_position_value=0.0,
            total_selected_capital_usage_pct=0.0,
            total_selected_expected_gross_profit=None,
            total_selected_expected_net_profit=None,
            total_selected_max_loss_amount=None,
            total_selected_max_loss_pct=None,
            selected_count=0,
            ready_count=0,
            draft_count=0,
            watch_count=0,
            rejected_count=0,
            excluded_by_tp_limit_count=0,
            data_quality=_data_quality_summary([], 0),
            primary=None,
            candidates=[],
            next_action="No watchlist rows are available for this run.",
            caveat=_standard_caveat(),
        )

    rows = [
        _build_candidate(row, capital, max_tp_pct, max_position_pct)
        for _, row in watchlist.fillna("").iterrows()
    ]
    ready_count = sum(1 for item in rows if item.readiness == Readiness.READY)
    draft_count = sum(1 for item in rows if item.readiness == Readiness.NEEDS_LIVE_CONFIRMATION)
    watch_count = sum(1 for item in rows if item.readiness == Readiness.WATCH_ONLY)
    rejected_count = sum(1 for item in rows if item.readiness == Readiness.REJECTED_OR_LOW_PRIORITY)
    tp_eligible = [
        item
        for item in rows
        if item.target_tp_pct is None or (0 < item.target_tp_pct <= max_tp_pct)
    ]
    excluded_by_tp_limit = len(rows) - len(tp_eligible)
    actionable = [
        item
        for item in tp_eligible
        if _status(item.final_status) in POSITIVE_STATUSES | WATCH_STATUSES and item.lots > 0
    ]
    actionable = sorted(actionable, key=_sort_key)[: max(limit, 0)]
    primary = actionable[0] if actionable else None
    total_position = sum(item.position_value for item in actionable)
    total_gross_profit = sum(item.expected_gross_profit or 0.0 for item in actionable) if actionable else None
    total_net_profit = sum(item.expected_net_profit or 0.0 for item in actionable) if actionable else None
    total_max_loss = sum(item.max_loss_amount or 0.0 for item in actionable) if actionable else None
    total_usage = total_position / capital if capital > 0 else 0.0
    total_loss_pct = total_max_loss / capital if total_max_loss is not None and capital > 0 else None
    portfolio_flags = _portfolio_flags(total_usage, total_loss_pct, len(actionable))
    portfolio_decision = _portfolio_decision(portfolio_flags)

    if primary is None:
        next_action = "No capital-sized candidate passed the TP cap and status filters; wait for a new scan."
    elif primary.readiness == Readiness.READY:
        next_action = "Review the primary candidate at market open; keep the entry zone, TP, SL, and orderbook gates intact."
    elif primary.readiness == Readiness.NEEDS_LIVE_CONFIRMATION:
        next_action = "Use this as a Fase Malam shortlist and run Fase Pagi/orderbook confirmation before buying."
    else:
        next_action = "Treat the shortlist as monitoring only until a later run upgrades the status."

    return RecommendationPack(
        run_id=run_id,
        schema_version=RECOMMENDATION_SCHEMA_VERSION,
        policy_version=DEFAULT_RECOMMENDATION_POLICY.version,
        policy=DEFAULT_RECOMMENDATION_POLICY.to_dict(),
        capital=capital,
        max_tp_pct=max_tp_pct,
        max_position_pct=max_position_pct,
        portfolio_decision=portfolio_decision,
        portfolio_flags=portfolio_flags,
        total_selected_position_value=total_position,
        total_selected_capital_usage_pct=total_usage,
        total_selected_expected_gross_profit=total_gross_profit,
        total_selected_expected_net_profit=total_net_profit,
        total_selected_max_loss_amount=total_max_loss,
        total_selected_max_loss_pct=total_loss_pct,
        selected_count=len(actionable),
        ready_count=ready_count,
        draft_count=draft_count,
        watch_count=watch_count,
        rejected_count=rejected_count,
        excluded_by_tp_limit_count=excluded_by_tp_limit,
        data_quality=_data_quality_summary(rows, len(actionable)),
        primary=primary,
        candidates=actionable,
        next_action=next_action,
        caveat=_standard_caveat(),
    )


def _idr(value: float | None) -> str:
    if value is None:
        return "-"
    return f"Rp {value:,.0f}"


def _pct(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value * 100:.2f}%"


def _standard_caveat() -> str:
    return (
        "This is a decision-support shortlist from the scanner, not a guarantee of profit "
        "or an instruction to place an order."
    )


def render_recommendation_markdown(pack: RecommendationPack) -> str:
    lines = [
        f"# Professional Trade Recommendation Pack: {pack.run_id}",
        "",
        f"- **Schema**: {pack.schema_version}",
        f"- **Capital**: {_idr(pack.capital)}",
        f"- **Policy**: {pack.policy_version}",
        f"- **TP cap**: {_pct(pack.max_tp_pct)}",
        f"- **Max position**: {_pct(pack.max_position_pct)}",
        f"- **Portfolio decision**: {pack.portfolio_decision}",
        f"- **Portfolio flags**: {', '.join(pack.portfolio_flags) if pack.portfolio_flags else 'CLEAR'}",
        f"- **Selected exposure**: {_idr(pack.total_selected_position_value)} ({_pct(pack.total_selected_capital_usage_pct)} of capital)",
        f"- **Selected expected gross / net / max loss**: {_idr(pack.total_selected_expected_gross_profit)} / {_idr(pack.total_selected_expected_net_profit)} / {_idr(pack.total_selected_max_loss_amount)}",
        f"- **Ready / Draft / Watch / Rejected**: {pack.ready_count} / {pack.draft_count} / {pack.watch_count} / {pack.rejected_count}",
        f"- **Excluded by TP cap**: {pack.excluded_by_tp_limit_count}",
        f"- **Data quality**: {pack.data_quality['complete_price_plan_count']} complete price plans / {pack.data_quality['total_rows']} rows",
        "",
    ]
    if pack.primary is None:
        lines.append("## Primary Candidate")
        lines.append("No capital-sized candidate passed the recommendation filters.")
    else:
        primary = pack.primary
        lines.extend(
            [
                "## Primary Candidate",
                (
                    f"**{primary.symbol}** ({primary.final_status}, {primary.execution_decision}, grade {primary.decision_grade}, "
                    f"confidence {primary.confidence_score:.1f}, score {primary.final_score:.1f}) "
                    f"is the current top-ranked candidate for this capital profile."
                ),
                "",
                f"- **Entry / TP / SL**: {_idr(primary.entry_price)} / {_idr(primary.tp1_price)} / {_idr(primary.stop_loss_price)}",
                f"- **TP / SL pct**: {_pct(primary.target_tp_pct)} / {_pct(primary.stop_loss_pct)}",
                f"- **Risk:Reward**: {primary.risk_reward_ratio:.2f}x" if primary.risk_reward_ratio is not None else "- **Risk:Reward**: -",
                f"- **Lots / position value**: {primary.lots} lot / {_idr(primary.position_value)} ({_pct(primary.capital_usage_pct)} of capital)",
                f"- **Expected gross / net profit / max loss**: {_idr(primary.expected_gross_profit)} / {_idr(primary.expected_net_profit)} / {_idr(primary.max_loss_amount)}",
                f"- **Estimated fees + slippage**: {_idr((primary.estimated_buy_fee or 0) + (primary.estimated_sell_fee or 0) + (primary.estimated_slippage or 0))}",
                (
                    "- **Confidence model**: "
                    f"status {primary.confidence_components['status_base']:.1f} + "
                    f"score {primary.confidence_components['score_component']:.1f} + "
                    f"R:R {primary.confidence_components['risk_reward_component']:.1f} - "
                    f"penalty {primary.confidence_components['audit_penalty']:.1f}"
                ),
                f"- **Audit flags**: {', '.join(primary.audit_flags) if primary.audit_flags else 'CLEAR'}",
                f"- **Why**: {primary.primary_reason}",
                f"- **Next action**: {primary.next_action}",
            ]
        )

    if pack.candidates:
        lines.extend(["", "## Shortlist", "| Symbol | Decision | Grade | Status | Confidence | Score | Entry | TP | SL | Lots | TP% | R:R | Flags |", "|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|"])
        for item in pack.candidates:
            rr_text = f"{item.risk_reward_ratio:.2f}x" if item.risk_reward_ratio is not None else "-"
            flags = ", ".join(item.audit_flags) if item.audit_flags else "CLEAR"
            lines.append(
                "| "
                + " | ".join(
                    [
                        item.symbol,
                        item.execution_decision,
                        item.decision_grade,
                        item.final_status,
                        f"{item.confidence_score:.1f}",
                        f"{item.final_score:.1f}",
                        _idr(item.entry_price),
                        _idr(item.tp1_price),
                        _idr(item.stop_loss_price),
                        str(item.lots),
                        _pct(item.target_tp_pct),
                        rr_text,
                        flags,
                    ]
                )
                + " |"
            )

    lines.extend(["", "## Portfolio Action", pack.next_action, "", f"**Caveat**: {pack.caveat}"])
    return "\n".join(lines)
