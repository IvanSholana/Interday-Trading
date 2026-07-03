from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import time
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pandas as pd


SECRET_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"deepseek_api_key",
        r"stockbit_token",
        r"authorization",
        r"bearer\s+[a-z0-9._\-]+",
        r"api[_-]?key",
        r"token",
        r"secret",
    ]
]
VALID_CATEGORIES = {"VALID", "WATCH", "NEAR_VALID", "REJECTED", "AVOID"}
WATCH_STATUSES = (
    "WATCH_",
    "WAIT_",
    "WATCH_BANDAR_ACCUMULATION_WAIT_TECHNICAL_TRIGGER",
    "WATCH_SHORT_TERM_ACCUMULATION_AGAINST_DISTRIBUTION",
    "WATCH_PULLBACK_WITH_MEDIUM_ACCUMULATION",
)
NEAR_VALID_STATUSES = {
    "REJECT_BAD_RISK_REWARD_TP1",
    "REJECT_BAD_RISK_REWARD_TP2",
    "REJECT_STOP_TOO_WIDE",
    "WAIT_ORDERBOOK_SPREAD_TOO_WIDE",
    "WAIT_ORDERBOOK_OFFER_WALL",
}
REJECTED_IMPORTANT_STATUSES = {
    "REJECT_CORPORATE_ACTION_RISK",
    "REJECT_UMA_OR_NOTATION_RISK",
    "REJECT_NOT_TRADABLE",
    "REJECT_TOO_VOLATILE",
    "REJECT_INVALID_STOP",
}
AVOID_SIGNALS = {"STRONG_DISTRIBUTION", "MILD_DISTRIBUTION", "NO_BROKER_DATA"}
SKIP_CONTEXTS = {"TOO_VOLATILE", "INVALID_DATA"}
CANDIDATE_FIELDS = [
    "ticker",
    "strategy_mode",
    "trade_status",
    "is_plan_valid",
    "technical_context",
    "technical_context_summary",
    "liquidity_bucket",
    "relative_activity_bucket",
    "close",
    "entry_price",
    "stop_loss",
    "take_profit_1",
    "take_profit_2",
    "risk_pct",
    "risk_reward_tp1",
    "risk_reward_tp2",
    "executable_position_size_lots",
    "bandarmology_signal",
    "bandarmology_score",
    "bandarmology_reason",
    "accumulation_window_count",
    "distribution_window_count",
    "short_term_score",
    "medium_term_score",
    "score_trend",
    "orderbook_status",
    "orderbook_score",
    "spread_pct",
    "depth_imbalance_top5",
    "offer_wall_ratio_top5",
    "foreign_net_ratio",
    "trade_reason",
    "trade_summary",
]


@dataclass(frozen=True)
class DeepSeekConfig:
    api_key: str | None
    model: str = "deepseek-reasoner"
    base_url: str = "https://api.deepseek.com"
    timeout_seconds: int = 120
    max_retries: int = 2
    retry_backoff_seconds: float = 5.0


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_optional_csv(path: str | Path | None, warnings: list[str] | None = None) -> pd.DataFrame:
    if not path:
        return pd.DataFrame()
    file_path = Path(path)
    if not file_path.exists():
        if warnings is not None:
            warnings.append(f"missing_optional_csv:{file_path}")
        return pd.DataFrame()
    return pd.read_csv(file_path)


def load_optional_json(path: str | Path | None, warnings: list[str] | None = None) -> dict[str, Any]:
    if not path:
        return {}
    file_path = Path(path)
    if not file_path.exists():
        if warnings is not None:
            warnings.append(f"missing_optional_json:{file_path}")
        return {}
    try:
        return json.loads(file_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        if warnings is not None:
            warnings.append(f"invalid_optional_json:{file_path}")
        return {}


def sanitize_for_llm(value: Any) -> Any:
    if value is None:
        return None
    try:
        if not isinstance(value, (dict, list, tuple, set)) and pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if any(pattern.search(key_text) for pattern in SECRET_PATTERNS):
                continue
            sanitized[key_text] = sanitize_for_llm(item)
        return sanitized
    if isinstance(value, (list, tuple, set)):
        return [sanitize_for_llm(item) for item in value]
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, float):
        if pd.isna(value):
            return None
        return round(float(value), 6)
    if isinstance(value, str):
        text = value.strip()
        if any(pattern.search(text) for pattern in SECRET_PATTERNS):
            return "[REDACTED]"
        return text[:1200]
    if isinstance(value, (int, bool)):
        return value
    return str(value)[:1200]


def _is_true(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "y", "1.0"}
    try:
        if not isinstance(value, (list, tuple, set, dict)) and pd.isna(value):
            return False
    except (TypeError, ValueError):
        pass
    return bool(value)


def _num(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        if not isinstance(value, (list, tuple, set, dict)) and pd.isna(value):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _status_counts(df: pd.DataFrame) -> dict[str, int]:
    if df.empty or "trade_status" not in df.columns:
        return {}
    return {str(k): int(v) for k, v in df["trade_status"].fillna("UNKNOWN").value_counts().sort_index().items()}


def _merge_inputs(stage2: pd.DataFrame, bandarmology: pd.DataFrame, orderbook: pd.DataFrame, stage4: pd.DataFrame) -> pd.DataFrame:
    if stage4.empty:
        return pd.DataFrame()
    merged = stage4.copy()
    for optional in [stage2, bandarmology, orderbook]:
        if optional.empty or "ticker" not in optional.columns:
            continue
        keep = [column for column in optional.columns if column == "ticker" or column not in merged.columns]
        merged = merged.merge(optional[keep], on="ticker", how="left")
    return merged


def _candidate_dict(row: pd.Series, backtest_summary: dict[str, Any] | None = None) -> dict[str, Any]:
    data = {field: sanitize_for_llm(row.get(field)) for field in CANDIDATE_FIELDS if field in row.index}
    if backtest_summary and "expectancy_pct" in backtest_summary:
        data["backtest_expectancy_pct"] = sanitize_for_llm(backtest_summary.get("expectancy_pct"))
    return data


def _sort_rows(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    output = df.copy()
    for column in columns:
        if column not in output.columns:
            output[column] = 0
    return output.sort_values(columns, ascending=[False] * len(columns), na_position="last")


def select_candidate_rows(stage4_df: pd.DataFrame, strategy_mode: str, max_candidates: int) -> dict[str, pd.DataFrame]:
    if stage4_df.empty:
        return {key: pd.DataFrame() for key in ["valid", "watchlist", "near_valid", "rejected_important", "avoid"]}
    df = stage4_df.copy()
    if "strategy_mode" in df.columns:
        df = df[df["strategy_mode"].fillna(strategy_mode).astype(str).str.lower() == strategy_mode.lower()]
    status = df.get("trade_status", pd.Series("", index=df.index)).fillna("").astype(str)
    signal = df.get("bandarmology_signal", pd.Series("", index=df.index)).fillna("").astype(str)
    context = df.get("technical_context", pd.Series("", index=df.index)).fillna("").astype(str)
    liquidity = df.get("liquidity_bucket", pd.Series("", index=df.index)).fillna("").astype(str)

    groups = {
        "valid": df[(status == "VALID_TRADE_PLAN") & df.get("is_plan_valid", pd.Series(False, index=df.index)).map(_is_true)],
        "watchlist": df[status.str.startswith(WATCH_STATUSES)],
        "near_valid": df[
            status.isin(NEAR_VALID_STATUSES)
            & signal.isin({"STRONG_ACCUMULATION", "MILD_ACCUMULATION", "PULLBACK_WITH_MEDIUM_ACCUMULATION"})
            & liquidity.isin({"HIGH_LIQUIDITY", "GOOD_LIQUIDITY"})
        ],
        "rejected_important": df[status.isin(REJECTED_IMPORTANT_STATUSES)],
        "avoid": df[signal.isin(AVOID_SIGNALS) | context.isin(SKIP_CONTEXTS)],
    }
    sort_columns = {
        "valid": ["risk_reward_tp1", "bandarmology_score", "orderbook_score"],
        "watchlist": ["bandarmology_score", "orderbook_score"],
        "near_valid": ["bandarmology_score", "risk_reward_tp1"],
        "rejected_important": ["bandarmology_score", "orderbook_score"],
        "avoid": ["bandarmology_score"],
    }
    remaining = max(0, int(max_candidates))
    limited: dict[str, pd.DataFrame] = {}
    for key in ["valid", "watchlist", "near_valid", "rejected_important", "avoid"]:
        take = min(10, remaining)
        limited[key] = _sort_rows(groups[key], sort_columns[key]).head(take).copy()
        remaining -= len(limited[key])
    return limited


def build_market_summary(stage4: pd.DataFrame, strategy_mode: str) -> dict[str, Any]:
    if stage4.empty:
        return {"total_screened": 0, "valid_trade_plans": 0, "watchlist_count": 0, "rejected_count": 0, "skipped_count": 0, "strategy_mode": strategy_mode}
    df = stage4.copy()
    if "strategy_mode" in df.columns:
        df = df[df["strategy_mode"].fillna(strategy_mode).astype(str).str.lower() == strategy_mode.lower()]
    status = df.get("trade_status", pd.Series("", index=df.index)).fillna("").astype(str)
    return {
        "total_screened": int(len(df)),
        "valid_trade_plans": int((status == "VALID_TRADE_PLAN").sum()),
        "watchlist_count": int(status.str.startswith(WATCH_STATUSES).sum()),
        "rejected_count": int(status.str.startswith("REJECT_").sum()),
        "skipped_count": int(status.str.startswith("SKIPPED_").sum()),
        "strategy_mode": strategy_mode,
    }


def build_backtest_summary(metrics: dict[str, Any]) -> dict[str, Any]:
    keys = ["evaluated_trades", "win_rate", "profit_factor", "expectancy_pct", "max_drawdown_pct", "total_net_pnl_amount", "average_holding_days"]
    return {key: sanitize_for_llm(metrics.get(key)) for key in keys if key in metrics}


def build_bpjs_summary(summary: dict[str, Any]) -> dict[str, Any]:
    keys = ["total_candidates", "opened_paper_trades", "closed_paper_trades", "win_rate", "average_return_pct", "total_pnl_amount", "skipped_orderbook_count"]
    return {key: sanitize_for_llm(summary.get(key)) for key in keys if key in summary}


def build_candidate_evidence(groups: dict[str, pd.DataFrame], backtest_summary: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    return {
        key: [_candidate_dict(row, backtest_summary) for _, row in df.iterrows()]
        for key, df in groups.items()
    }


def build_rejected_summary(stage4: pd.DataFrame) -> list[dict[str, Any]]:
    if stage4.empty or "trade_status" not in stage4.columns:
        return []
    rejected = stage4[stage4["trade_status"].fillna("").astype(str).str.startswith(("REJECT_", "SKIPPED_"))]
    counts = rejected["trade_status"].fillna("UNKNOWN").value_counts().head(20)
    return [{"trade_status": str(status), "count": int(count)} for status, count in counts.items()]


def build_watchlist_summary(stage4: pd.DataFrame) -> list[dict[str, Any]]:
    if stage4.empty or "trade_status" not in stage4.columns:
        return []
    watch = stage4[stage4["trade_status"].fillna("").astype(str).str.startswith(WATCH_STATUSES)]
    counts = watch["trade_status"].fillna("UNKNOWN").value_counts().head(20)
    return [{"trade_status": str(status), "count": int(count)} for status, count in counts.items()]


def build_evidence_pack(
    stage2_path: str | Path | None,
    bandarmology_path: str | Path | None,
    orderbook_path: str | Path | None,
    stage4_path: str | Path | None,
    backtest_metrics_path: str | Path | None,
    bpjs_summary_path: str | Path | None,
    strategy_mode: str,
    run_date: str,
    max_candidates: int = 30,
) -> dict[str, Any]:
    warnings: list[str] = []
    stage2 = load_optional_csv(stage2_path, warnings)
    bandarmology = load_optional_csv(bandarmology_path, warnings)
    orderbook = load_optional_csv(orderbook_path, warnings)
    stage4 = load_optional_csv(stage4_path, warnings)
    backtest_metrics = load_optional_json(backtest_metrics_path, warnings)
    bpjs_summary_json = load_optional_json(bpjs_summary_path, warnings)
    merged = _merge_inputs(stage2, bandarmology, orderbook, stage4)
    groups = select_candidate_rows(merged, strategy_mode, max_candidates)
    backtest_summary = build_backtest_summary(backtest_metrics)
    evidence = {
        "metadata": {
            "run_date": run_date,
            "strategy_mode": strategy_mode,
            "generated_at": utc_now_iso(),
            "pipeline_stage": "stage6",
            "evidence_version": "1.0",
        },
        "safety_rules": {
            "llm_can_create_new_trade_signal": False,
            "llm_can_override_stage4_status": False,
            "llm_can_change_risk_parameters": False,
            "llm_can_recommend_auto_order": False,
        },
        "input_files": {
            "stage2": str(stage2_path) if stage2_path else None,
            "bandarmology": str(bandarmology_path) if bandarmology_path else None,
            "orderbook": str(orderbook_path) if orderbook_path else None,
            "stage4": str(stage4_path) if stage4_path else None,
            "backtest_metrics": str(backtest_metrics_path) if backtest_metrics_path else None,
            "bpjs_summary": str(bpjs_summary_path) if bpjs_summary_path else None,
        },
        "warnings": warnings,
        "market_summary": build_market_summary(merged, strategy_mode),
        "status_distribution": _status_counts(merged),
        "backtest_summary": backtest_summary,
        "bpjs_summary": build_bpjs_summary(bpjs_summary_json),
        "candidate_groups": build_candidate_evidence(groups, backtest_summary),
        "rejection_summary": build_rejected_summary(merged),
        "watchlist_summary": build_watchlist_summary(merged),
        "llm_instruction": {
            "task": "Analyze evidence only. Do not invent new signals.",
            "allowed_actions": ["explain", "rank_existing_candidates", "summarize_watchlist", "identify_risks", "suggest_parameters_to_backtest"],
            "forbidden_actions": ["change_stage4_status", "change_stop_loss", "change_take_profit", "change_position_size", "recommend_auto_order", "recommend_buy_for_rejected_ticker"],
        },
    }
    return sanitize_for_llm(evidence)


def write_evidence_pack(evidence: dict[str, Any], output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(evidence, indent=2, ensure_ascii=False, allow_nan=False, default=str), encoding="utf-8")
    return path


def get_deepseek_config() -> DeepSeekConfig:
    return DeepSeekConfig(
        api_key=os.getenv("DEEPSEEK_API_KEY"),
        model=os.getenv("DEEPSEEK_MODEL") or "deepseek-reasoner",
        base_url=(os.getenv("DEEPSEEK_BASE_URL") or "https://api.deepseek.com").rstrip("/"),
        timeout_seconds=int(os.getenv("DEEPSEEK_TIMEOUT_SECONDS") or "120"),
    )


SYSTEM_PROMPT = """You are a conservative trading analyst reviewing a deterministic screening pipeline.
You are NOT allowed to create new trade signals.
You are NOT allowed to override the pipeline trade_status.
You are NOT allowed to change entry, stop-loss, take-profit, or position size.
You are NOT allowed to recommend auto-order execution.
You must only analyze the provided evidence.
If a ticker is rejected, you may explain why, but you must not recommend buying it.
If a ticker is watchlisted, you may describe the trigger to wait for.
If a ticker is valid, you may rank it and explain the risks.
Always preserve the original trade_status.
Return structured JSON only, matching the requested schema.
Use cautious language.
Mention uncertainty and data limitations.
Do not invent missing data."""


def build_llm_messages(evidence_pack: dict[str, Any], strategy_mode: str) -> list[dict[str, str]]:
    schema = {
        "run_date": "YYYY-MM-DD",
        "strategy_mode": strategy_mode,
        "executive_summary": {"headline": "", "valid_count": 0, "watchlist_count": 0, "main_risk": "", "market_quality": "GOOD|MIXED|WEAK|INSUFFICIENT_DATA", "should_trade_today": "YES|SELECTIVE|NO|PAPER_ONLY", "reason": ""},
        "candidate_ranking": [],
        "watchlist_notes": [],
        "rejected_notes": [],
        "risk_review": {"portfolio_risks": [], "data_quality_warnings": [], "execution_warnings": [], "overfitting_warnings": []},
        "parameter_review": {"parameters_to_backtest": [], "suspected_too_strict_rules": [], "suspected_too_loose_rules": []},
        "final_notes": "",
    }
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": json.dumps(
                {
                    "strategy_mode": strategy_mode,
                    "evidence_pack": evidence_pack,
                    "required_output_schema": schema,
                },
                ensure_ascii=False,
                allow_nan=False,
                default=str,
            ),
        },
    ]


def call_deepseek_chat(messages: list[dict[str, str]], config: DeepSeekConfig) -> dict[str, Any]:
    if not config.api_key:
        raise RuntimeError("DEEPSEEK_API_KEY is required when dry-run is disabled.")
    payload = json.dumps({"model": config.model, "messages": messages, "response_format": {"type": "json_object"}}, ensure_ascii=False).encode("utf-8")
    url = f"{config.base_url}/chat/completions"
    for attempt in range(config.max_retries + 1):
        request = Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {config.api_key}"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=config.timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            if exc.code in {401, 403}:
                raise RuntimeError("DeepSeek API key invalid or unauthorized.") from exc
            if exc.code in {429, 500, 502, 503, 504} and attempt < config.max_retries:
                time.sleep(config.retry_backoff_seconds)
                continue
            raise
        except Exception:
            if attempt < config.max_retries:
                time.sleep(config.retry_backoff_seconds)
                continue
            raise
    raise RuntimeError("DeepSeek request failed after retries.")


def extract_llm_json_response(response: dict[str, Any] | str) -> tuple[dict[str, Any] | None, str, str | None]:
    raw_text = response if isinstance(response, str) else ""
    if isinstance(response, dict):
        try:
            raw_text = str(response["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError):
            raw_text = json.dumps(response, ensure_ascii=False, default=str)
    try:
        return json.loads(raw_text), raw_text, None
    except json.JSONDecodeError as exc:
        match = re.search(r"\{.*\}", raw_text, flags=re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0)), raw_text, None
            except json.JSONDecodeError:
                pass
        return None, raw_text, str(exc)


def _all_evidence_candidates(evidence: dict[str, Any]) -> dict[str, dict[str, Any]]:
    candidates: dict[str, dict[str, Any]] = {}
    for group in evidence.get("candidate_groups", {}).values():
        if not isinstance(group, list):
            continue
        for item in group:
            if isinstance(item, dict) and item.get("ticker"):
                candidates[str(item["ticker"])] = item
    return candidates


def _text_contains_forbidden_action(value: Any) -> bool:
    text = json.dumps(value, ensure_ascii=False, default=str).lower()
    forbidden_phrases = [
        "use auto order",
        "place auto order",
        "send auto order",
        "execute auto order",
        "market order immediately",
        "average down",
        "averaging down",
    ]
    return any(phrase in text for phrase in forbidden_phrases)


def validate_llm_output(llm_json: dict[str, Any], evidence: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    validated = sanitize_for_llm(llm_json or {})
    violations: list[dict[str, Any]] = []
    evidence_by_ticker = _all_evidence_candidates(evidence)

    def flag(kind: str, ticker: str | None, message: str) -> None:
        violations.append({"kind": kind, "ticker": ticker, "message": message})

    for section in ["candidate_ranking", "watchlist_notes", "rejected_notes"]:
        rows = validated.get(section, [])
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            ticker = str(row.get("ticker", ""))
            evidence_row = evidence_by_ticker.get(ticker)
            if not evidence_row:
                flag("unknown_ticker", ticker, "LLM output referenced ticker not present in evidence pack.")
                row["guardrail_validated"] = False
                row["category"] = "REJECTED"
                continue
            evidence_status = evidence_row.get("trade_status")
            original_status = row.get("original_trade_status")
            if original_status and original_status != evidence_status:
                flag("changed_trade_status", ticker, "LLM output changed original trade_status.")
                row["original_trade_status"] = evidence_status
            if row.get("category") == "VALID" and evidence_status != "VALID_TRADE_PLAN":
                flag("rejected_or_watch_marked_valid", ticker, "Non-valid Stage 4 ticker was marked VALID.")
                row["category"] = "WATCH" if str(evidence_status).startswith(WATCH_STATUSES) else "REJECTED"
            if evidence_row.get("is_plan_valid") is False and row.get("category") == "VALID":
                flag("invalid_plan_marked_valid", ticker, "Invalid Stage 4 plan was marked VALID.")
                row["category"] = "REJECTED"
            for price_field in ["stop_loss", "take_profit_1", "take_profit_2", "position_size_lots", "entry_price"]:
                if price_field in row and sanitize_for_llm(row.get(price_field)) != sanitize_for_llm(evidence_row.get(price_field)):
                    flag("changed_risk_parameter", ticker, f"LLM output attempted to change {price_field}.")
                    row.pop(price_field, None)
            row["guardrail_validated"] = not any(v.get("ticker") == ticker for v in violations)
    if _text_contains_forbidden_action(validated):
        flag("forbidden_execution_language", None, "LLM output contains auto-order or averaging-down language.")
    return validated, violations


def make_dry_run_response(evidence: dict[str, Any], strategy_mode: str) -> dict[str, Any]:
    groups = evidence.get("candidate_groups", {})
    valid = groups.get("valid", [])
    watch = groups.get("watchlist", [])
    near = groups.get("near_valid", [])
    rejected = groups.get("rejected_important", [])
    avoid = groups.get("avoid", [])
    ranking = []
    for idx, item in enumerate((valid + near + watch)[:10], start=1):
        status = item.get("trade_status")
        category = "VALID" if status == "VALID_TRADE_PLAN" else ("NEAR_VALID" if item in near else "WATCH")
        ranking.append(
            {
                "rank": idx,
                "ticker": item.get("ticker"),
                "original_trade_status": status,
                "category": category,
                "analyst_view": "Dry-run review: preserve Stage 4 status and review execution risk before acting.",
                "key_supporting_evidence": [f"bandarmology={item.get('bandarmology_signal')}", f"rr_tp1={item.get('risk_reward_tp1')}"],
                "key_risks": [f"orderbook={item.get('orderbook_status')}"],
                "execution_checklist": ["Confirm current price and orderbook manually.", "Do not override Stage 4 risk plan."],
                "do_not_override_status": True,
            }
        )
    return {
        "run_date": evidence.get("metadata", {}).get("run_date"),
        "strategy_mode": strategy_mode,
        "executive_summary": {
            "headline": "Dry-run analyst review generated from deterministic evidence pack.",
            "valid_count": len(valid),
            "watchlist_count": len(watch),
            "main_risk": "This is a dry-run mock response; no external LLM was called.",
            "market_quality": "INSUFFICIENT_DATA" if not valid and not watch else "MIXED",
            "should_trade_today": "PAPER_ONLY" if strategy_mode == "bpjs" else "SELECTIVE",
            "reason": "Stage 6 does not create signals and does not override Stage 4.",
        },
        "candidate_ranking": ranking,
        "watchlist_notes": [
            {
                "ticker": item.get("ticker"),
                "original_trade_status": item.get("trade_status"),
                "watch_reason": item.get("trade_reason") or "Watchlist item from Stage 4.",
                "trigger_to_wait_for": "Wait for Stage 4 to become valid without changing risk parameters.",
                "invalidation_condition": "Distribution, invalid data, or orderbook deterioration.",
                "do_not_execute_yet": True,
            }
            for item in watch[:20]
        ],
        "rejected_notes": [
            {
                "ticker": item.get("ticker"),
                "original_trade_status": item.get("trade_status"),
                "reason": item.get("trade_reason") or "Rejected by deterministic pipeline.",
                "what_would_need_to_improve": "Needs deterministic pipeline confirmation in a future run.",
                "avoid_for_now": True,
            }
            for item in (rejected + avoid)[:20]
        ],
        "risk_review": {
            "portfolio_risks": ["Respect Stage 4 position sizing and stop-loss."],
            "data_quality_warnings": evidence.get("warnings", []),
            "execution_warnings": ["No auto order; confirm current market manually."],
            "overfitting_warnings": ["Backtest and paper results are validation inputs, not guarantees."],
        },
        "parameter_review": {
            "parameters_to_backtest": ["max_entry_gap_pct", "min_rr_tp1", "time_stop_days"],
            "suspected_too_strict_rules": [],
            "suspected_too_loose_rules": [],
        },
        "final_notes": "Dry-run output for pipeline validation only.",
    }


def _table(rows: list[list[Any]]) -> str:
    if not rows:
        return "_None._\n"
    header = rows[0]
    lines = ["| " + " | ".join(map(str, header)) + " |", "| " + " | ".join(["---"] * len(header)) + " |"]
    for row in rows[1:]:
        lines.append("| " + " | ".join(str(cell).replace("\n", " ") for cell in row) + " |")
    return "\n".join(lines) + "\n"


def write_markdown_report(
    llm_json: dict[str, Any],
    metadata: dict[str, Any],
    guardrail_violations: list[dict[str, Any]],
    output_path: str | Path,
) -> Path:
    summary = llm_json.get("executive_summary", {})
    ranking = llm_json.get("candidate_ranking", [])
    watchlist = llm_json.get("watchlist_notes", [])
    rejected = llm_json.get("rejected_notes", [])
    lines = [
        "# Stage 6 LLM Analyst Report",
        "",
        f"Tanggal: {llm_json.get('run_date') or metadata.get('run_date')}",
        f"Strategy mode: {llm_json.get('strategy_mode') or metadata.get('strategy_mode')}",
        f"LLM provider: {metadata.get('llm_provider')}",
        f"Model: {metadata.get('model')}",
        f"Dry run: {metadata.get('dry_run')}",
        "",
        "## Executive Summary",
        summary.get("headline", ""),
        "",
        f"Market quality: {summary.get('market_quality', '')}",
        f"Should trade today: {summary.get('should_trade_today', '')}",
        f"Reason: {summary.get('reason', '')}",
        "",
        "## Valid Candidates",
        _table([["Rank", "Ticker", "Status", "Analyst View", "Key Risk"]] + [[row.get("rank", ""), row.get("ticker", ""), row.get("original_trade_status", ""), row.get("analyst_view", ""), "; ".join(row.get("key_risks", []))] for row in ranking if row.get("category") == "VALID"]),
        "## Watchlist",
        _table([["Ticker", "Status", "Watch Reason", "Trigger to Wait For", "Invalidation"]] + [[row.get("ticker", ""), row.get("original_trade_status", ""), row.get("watch_reason", ""), row.get("trigger_to_wait_for", ""), row.get("invalidation_condition", "")] for row in watchlist]),
        "## Near Valid / Rejected Important",
        _table([["Rank", "Ticker", "Status", "Analyst View", "Key Risk"]] + [[row.get("rank", ""), row.get("ticker", ""), row.get("original_trade_status", ""), row.get("analyst_view", ""), "; ".join(row.get("key_risks", []))] for row in ranking if row.get("category") in {"NEAR_VALID", "REJECTED"}]),
        "## Avoid",
        _table([["Ticker", "Status", "Reason", "What Would Need To Improve"]] + [[row.get("ticker", ""), row.get("original_trade_status", ""), row.get("reason", ""), row.get("what_would_need_to_improve", "")] for row in rejected]),
        "## Risk Review",
        json.dumps(llm_json.get("risk_review", {}), indent=2, ensure_ascii=False),
        "",
        "## Parameter Review",
        json.dumps(llm_json.get("parameter_review", {}), indent=2, ensure_ascii=False),
        "",
        "## Guardrail Notes",
        json.dumps(guardrail_violations, indent=2, ensure_ascii=False) if guardrail_violations else "No guardrail violations detected.",
        "",
        "## Safety Reminder",
        "This report is not investment advice. It does not override Stage 4 risk management. Do not auto-order from this report.",
        "",
    ]
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def write_ranking_json(llm_json: dict[str, Any], metadata: dict[str, Any], violations: list[dict[str, Any]], output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"metadata": metadata, "candidate_ranking": llm_json.get("candidate_ranking", []), "guardrail_violations": violations, "validated": not violations}
    path.write_text(json.dumps(sanitize_for_llm(payload), indent=2, ensure_ascii=False, allow_nan=False, default=str), encoding="utf-8")
    return path


def write_watchlist_csv(llm_json: dict[str, Any], metadata: dict[str, Any], violations: list[dict[str, Any]], output_path: str | Path) -> Path:
    rows = []
    invalid_tickers = {v.get("ticker") for v in violations if v.get("ticker")}
    for row in llm_json.get("watchlist_notes", []):
        rows.append(
            {
                "run_date": metadata.get("run_date"),
                "strategy_mode": metadata.get("strategy_mode"),
                "ticker": row.get("ticker"),
                "original_trade_status": row.get("original_trade_status"),
                "category": "WATCH",
                "analyst_view": row.get("watch_reason"),
                "watch_reason": row.get("watch_reason"),
                "trigger_to_wait_for": row.get("trigger_to_wait_for"),
                "invalidation_condition": row.get("invalidation_condition"),
                "key_risks": "",
                "do_not_execute_yet": row.get("do_not_execute_yet", True),
                "guardrail_validated": row.get("ticker") not in invalid_tickers,
            }
        )
    for row in llm_json.get("candidate_ranking", []):
        rows.append(
            {
                "run_date": metadata.get("run_date"),
                "strategy_mode": metadata.get("strategy_mode"),
                "ticker": row.get("ticker"),
                "original_trade_status": row.get("original_trade_status"),
                "category": row.get("category"),
                "analyst_view": row.get("analyst_view"),
                "watch_reason": "",
                "trigger_to_wait_for": "",
                "invalidation_condition": "",
                "key_risks": "; ".join(row.get("key_risks", [])),
                "do_not_execute_yet": row.get("category") != "VALID",
                "guardrail_validated": row.get("ticker") not in invalid_tickers,
            }
        )
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


def write_raw_response(
    provider: str,
    model: str,
    dry_run: bool,
    raw_text: str,
    parsed_json: dict[str, Any] | None,
    parse_error: str | None,
    violations: list[dict[str, Any]],
    output_path: str | Path,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "provider": provider,
        "model": model,
        "dry_run": dry_run,
        "request_metadata": {"created_by": "stage6_llm_analyst", "api_key_present": bool(os.getenv("DEEPSEEK_API_KEY"))},
        "raw_response_text": raw_text,
        "parsed_json": parsed_json,
        "parse_error": parse_error,
        "guardrail_violations": violations,
        "created_at": utc_now_iso(),
    }
    path.write_text(json.dumps(sanitize_for_llm(payload), indent=2, ensure_ascii=False, allow_nan=False, default=str), encoding="utf-8")
    return path


def run_llm_report(
    evidence_path: str | Path,
    report_output: str | Path,
    ranking_output: str | Path,
    watchlist_output: str | Path,
    raw_output: str | Path,
    strategy_mode: str,
    dry_run: bool = False,
) -> dict[str, Any]:
    evidence = json.loads(Path(evidence_path).read_text(encoding="utf-8"))
    config = get_deepseek_config()
    metadata = {
        "run_date": evidence.get("metadata", {}).get("run_date"),
        "strategy_mode": strategy_mode,
        "llm_provider": "dry_run_mock" if dry_run else "deepseek",
        "model": config.model,
        "dry_run": dry_run,
    }
    parse_error = None
    if dry_run:
        parsed = make_dry_run_response(evidence, strategy_mode)
        raw_text = json.dumps(parsed, ensure_ascii=False)
    else:
        try:
            response = call_deepseek_chat(build_llm_messages(evidence, strategy_mode), config)
            parsed, raw_text, parse_error = extract_llm_json_response(response)
        except Exception as exc:
            parsed = make_dry_run_response(evidence, strategy_mode)
            raw_text = json.dumps({"error": str(exc), "fallback": parsed}, ensure_ascii=False)
            parse_error = str(exc)
            metadata["llm_provider"] = "deepseek_error_fallback"
    validated, violations = validate_llm_output(parsed or {}, evidence)
    write_markdown_report(validated, metadata, violations, report_output)
    write_ranking_json(validated, metadata, violations, ranking_output)
    write_watchlist_csv(validated, metadata, violations, watchlist_output)
    write_raw_response(metadata["llm_provider"], metadata["model"], dry_run, raw_text, validated, parse_error, violations, raw_output)
    print(f"Stage 6 report saved to: {report_output}")
    print(f"Ranking output saved to: {ranking_output}")
    print(f"Watchlist output saved to: {watchlist_output}")
    print(f"Raw response output saved to: {raw_output}")
    return validated


def run_stage6_build_evidence(
    stage2_path: str | Path | None,
    bandarmology_path: str | Path | None,
    orderbook_path: str | Path | None,
    stage4_path: str | Path | None,
    backtest_metrics_path: str | Path | None,
    bpjs_summary_path: str | Path | None,
    output_path: str | Path,
    strategy_mode: str,
    run_date: str,
    max_candidates: int = 30,
) -> dict[str, Any]:
    evidence = build_evidence_pack(stage2_path, bandarmology_path, orderbook_path, stage4_path, backtest_metrics_path, bpjs_summary_path, strategy_mode, run_date, max_candidates)
    write_evidence_pack(evidence, output_path)
    print(f"Evidence pack saved to: {output_path}")
    return evidence
