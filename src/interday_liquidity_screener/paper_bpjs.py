from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

import pandas as pd


SUPPORTIVE_ORDERBOOK_STATUSES = {"ORDERBOOK_SUPPORTIVE", "ORDERBOOK_NEUTRAL"}
PAPER_OUTPUT_COLUMNS = [
    "date",
    "ticker",
    "strategy_mode",
    "planned_entry_price",
    "stop_loss",
    "take_profit_1",
    "take_profit_2",
    "orderbook_status",
    "orderbook_score",
    "spread_pct",
    "depth_imbalance_top5",
    "offer_wall_ratio_top5",
    "fnet",
    "foreign_net_ratio",
    "paper_entry_price",
    "paper_entry_time",
    "planned_exit_time",
    "paper_exit_price",
    "paper_exit_time",
    "exit_reason",
    "return_pct",
    "pnl_amount",
    "position_size_lots",
    "shares",
    "position_value",
    "notes",
    "status",
]


@dataclass(frozen=True)
class BpjsPaperConfig:
    date: str
    entry_time: str = "09:15"
    exit_time: str = "15:45"
    lot_size: int = 100


def _is_true(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "y", "1.0"}
    try:
        if pd.isna(value):
            return False
    except (TypeError, ValueError):
        return False
    return bool(value)


def _float(value: Any, default: float | None = None) -> float | None:
    if value is None:
        return default
    try:
        if pd.isna(value):
            return default
    except (TypeError, ValueError):
        pass
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _int(value: Any, default: int = 0) -> int:
    parsed = _float(value)
    return int(parsed) if parsed is not None else default


def _merge_orderbook(stage4: pd.DataFrame, orderbook: pd.DataFrame | None) -> pd.DataFrame:
    if orderbook is None or orderbook.empty:
        return stage4.copy()
    stage4 = stage4.copy()
    keep = [column for column in orderbook.columns if column == "ticker" or column not in stage4.columns]
    return stage4.merge(orderbook[keep], on="ticker", how="left")


def is_bpjs_paper_candidate(row: dict[str, Any] | pd.Series) -> bool:
    return (
        str(row.get("strategy_mode", "")).lower() == "bpjs"
        and row.get("trade_status") == "VALID_TRADE_PLAN"
        and _is_true(row.get("is_plan_valid"))
        and str(row.get("orderbook_status")) in SUPPORTIVE_ORDERBOOK_STATUSES
        and _int(row.get("executable_position_size_lots", row.get("position_size_lots"))) > 0
    )


def build_bpjs_paper_trade(row: dict[str, Any] | pd.Series, config: BpjsPaperConfig) -> dict[str, Any]:
    lots = _int(row.get("executable_position_size_lots", row.get("position_size_lots")))
    shares = lots * config.lot_size
    lastprice = _float(row.get("lastprice"))
    planned_entry = _float(row.get("entry_price"))
    entry_price = lastprice if lastprice is not None and lastprice > 0 else planned_entry
    position_value = shares * entry_price if entry_price is not None else pd.NA
    return {
        "date": config.date,
        "ticker": row.get("ticker"),
        "strategy_mode": row.get("strategy_mode"),
        "planned_entry_price": planned_entry,
        "stop_loss": _float(row.get("stop_loss")),
        "take_profit_1": _float(row.get("take_profit_1")),
        "take_profit_2": _float(row.get("take_profit_2")),
        "orderbook_status": row.get("orderbook_status"),
        "orderbook_score": _float(row.get("orderbook_score")),
        "spread_pct": _float(row.get("spread_pct")),
        "depth_imbalance_top5": _float(row.get("depth_imbalance_top5")),
        "offer_wall_ratio_top5": _float(row.get("offer_wall_ratio_top5")),
        "fnet": _float(row.get("fnet")),
        "foreign_net_ratio": _float(row.get("foreign_net_ratio")),
        "paper_entry_price": entry_price,
        "paper_entry_time": config.entry_time,
        "planned_exit_time": config.exit_time,
        "paper_exit_price": pd.NA,
        "paper_exit_time": pd.NA,
        "exit_reason": pd.NA,
        "return_pct": pd.NA,
        "pnl_amount": pd.NA,
        "position_size_lots": lots,
        "shares": shares,
        "position_value": position_value,
        "notes": "Forward paper trade only. No broker order was sent.",
        "status": "OPEN_PAPER_TRADE",
    }


def create_bpjs_paper_trades(
    stage4: pd.DataFrame,
    orderbook: pd.DataFrame | None,
    config: BpjsPaperConfig,
) -> pd.DataFrame:
    merged = _merge_orderbook(stage4, orderbook)
    rows = [build_bpjs_paper_trade(row, config) for _, row in merged.iterrows() if is_bpjs_paper_candidate(row)]
    output = pd.DataFrame(rows)
    for column in PAPER_OUTPUT_COLUMNS:
        if column not in output.columns:
            output[column] = pd.NA
    return output[PAPER_OUTPUT_COLUMNS]


def update_bpjs_paper_trades(paper: pd.DataFrame, actual_exit: pd.DataFrame) -> pd.DataFrame:
    output = paper.copy()
    for column in ["paper_exit_time", "exit_reason", "status", "notes"]:
        if column in output.columns:
            output[column] = output[column].astype("object")
    exits = actual_exit.copy()
    exits["ticker"] = exits["ticker"].astype(str)
    exit_map = exits.set_index("ticker").to_dict(orient="index")
    for idx, row in output.iterrows():
        ticker = str(row.get("ticker"))
        if ticker not in exit_map:
            continue
        actual = exit_map[ticker]
        exit_price = _float(actual.get("exit_price"))
        entry_price = _float(row.get("paper_entry_price"))
        shares = _int(row.get("shares"))
        if exit_price is None or entry_price is None or entry_price <= 0:
            continue
        return_pct = (exit_price - entry_price) / entry_price
        output.at[idx, "paper_exit_price"] = exit_price
        output.at[idx, "paper_exit_time"] = actual.get("exit_time")
        output.at[idx, "exit_reason"] = actual.get("exit_reason", "MANUAL_EXIT")
        output.at[idx, "return_pct"] = return_pct
        output.at[idx, "pnl_amount"] = shares * entry_price * return_pct
        output.at[idx, "status"] = "CLOSED_PAPER_TRADE"
    return output[PAPER_OUTPUT_COLUMNS]


def calculate_bpjs_summary(paper: pd.DataFrame, source_candidates: pd.DataFrame | None = None) -> dict[str, Any]:
    closed = paper[paper["status"] == "CLOSED_PAPER_TRADE"].copy() if not paper.empty else pd.DataFrame()
    returns = pd.to_numeric(closed.get("return_pct", pd.Series(dtype=float)), errors="coerce").dropna()
    wins = returns[returns > 0]
    losses = returns[returns < 0]
    pnl = pd.to_numeric(closed.get("pnl_amount", pd.Series(dtype=float)), errors="coerce").fillna(0)
    total_candidates = int(len(source_candidates)) if source_candidates is not None else int(len(paper))
    source = source_candidates if source_candidates is not None else paper
    return {
        "total_candidates": total_candidates,
        "opened_paper_trades": int((paper["status"] == "OPEN_PAPER_TRADE").sum()) if not paper.empty else 0,
        "closed_paper_trades": int(len(closed)),
        "win_count": int(len(wins)),
        "loss_count": int(len(losses)),
        "win_rate": float(len(wins) / len(closed)) if len(closed) else 0.0,
        "average_return_pct": float(returns.mean()) if not returns.empty else None,
        "median_return_pct": float(returns.median()) if not returns.empty else None,
        "total_pnl_amount": float(pnl.sum()) if not pnl.empty else 0.0,
        "best_trade_pct": float(returns.max()) if not returns.empty else None,
        "worst_trade_pct": float(returns.min()) if not returns.empty else None,
        "orderbook_supportive_count": int((source.get("orderbook_status", pd.Series(dtype=str)) == "ORDERBOOK_SUPPORTIVE").sum()) if not source.empty else 0,
        "orderbook_neutral_count": int((source.get("orderbook_status", pd.Series(dtype=str)) == "ORDERBOOK_NEUTRAL").sum()) if not source.empty else 0,
        "skipped_orderbook_count": int((~source.get("orderbook_status", pd.Series(dtype=str)).isin(SUPPORTIVE_ORDERBOOK_STATUSES)).sum()) if not source.empty else 0,
    }


def run_stage5_paper_bpjs(
    stage4_path: str | Path,
    orderbook_path: str | Path | None,
    output_path: str | Path,
    config: BpjsPaperConfig,
    summary_output_path: str | Path | None = None,
) -> pd.DataFrame:
    stage4 = pd.read_csv(stage4_path)
    orderbook = pd.read_csv(orderbook_path) if orderbook_path else None
    paper = create_bpjs_paper_trades(stage4, orderbook, config)
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    paper.to_csv(output_file, index=False)
    summary = calculate_bpjs_summary(paper, source_candidates=_merge_orderbook(stage4, orderbook))
    if summary_output_path:
        summary_file = Path(summary_output_path)
        summary_file.parent.mkdir(parents=True, exist_ok=True)
        summary_file.write_text(json.dumps(summary, indent=2, allow_nan=False, default=str), encoding="utf-8")
        print(f"Summary output saved to: {summary_file}")
    print(f"BPJS paper trades opened: {len(paper)}")
    print(f"Paper output saved to: {output_file}")
    return paper


def run_stage5_update_bpjs_paper(
    paper_path: str | Path,
    actual_exit_path: str | Path,
    output_path: str | Path,
    summary_output_path: str | Path | None = None,
) -> pd.DataFrame:
    paper = pd.read_csv(paper_path)
    actual_exit = pd.read_csv(actual_exit_path)
    updated = update_bpjs_paper_trades(paper, actual_exit)
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    updated.to_csv(output_file, index=False)
    if summary_output_path:
        summary = calculate_bpjs_summary(updated)
        summary_file = Path(summary_output_path)
        summary_file.parent.mkdir(parents=True, exist_ok=True)
        summary_file.write_text(json.dumps(summary, indent=2, allow_nan=False, default=str), encoding="utf-8")
        print(f"Summary output saved to: {summary_file}")
    print(f"Updated paper output saved to: {output_file}")
    return updated
