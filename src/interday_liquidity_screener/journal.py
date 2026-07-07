from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd


JOURNAL_COLUMNS = [
    "date",
    "symbol",
    "mode",
    "status_before_entry",
    "entry_time",
    "entry_price",
    "lot",
    "tp1",
    "tp2",
    "stop_loss",
    "exit_time",
    "exit_price",
    "exit_reason",
    "gross_pnl",
    "net_pnl",
    "fees",
    "slippage",
    "holding_period",
    "pre_market_score",
    "orderbook_score",
    "smart_money_score",
    "technical_score",
    "liquidity_score",
    "warnings_at_entry",
    "mistake_tag",
    "review_note",
]


def _float(value: Any, default: float = 0.0) -> float:
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


def build_journal_entry(**kwargs: Any) -> dict[str, Any]:
    row = {column: kwargs.get(column) for column in JOURNAL_COLUMNS}
    lot = int(_float(row.get("lot"), 0))
    shares = lot * 100
    entry = _float(row.get("entry_price"))
    exit_price = _float(row.get("exit_price"))
    fees = _float(row.get("fees"))
    slippage = _float(row.get("slippage"))
    if row.get("gross_pnl") is None and entry > 0 and exit_price > 0:
        row["gross_pnl"] = (exit_price - entry) * shares
    if row.get("net_pnl") is None and row.get("gross_pnl") is not None:
        row["net_pnl"] = _float(row.get("gross_pnl")) - fees - slippage
    return row


def load_journal(path: str | Path) -> pd.DataFrame:
    journal_path = Path(path)
    if not journal_path.exists():
        return pd.DataFrame(columns=JOURNAL_COLUMNS)
    df = pd.read_csv(journal_path)
    for column in JOURNAL_COLUMNS:
        if column not in df.columns:
            df[column] = pd.NA
    return df[JOURNAL_COLUMNS]


def append_journal_entry(path: str | Path, entry: dict[str, Any]) -> pd.DataFrame:
    journal_path = Path(path)
    journal_path.parent.mkdir(parents=True, exist_ok=True)
    current = load_journal(journal_path)
    next_row = pd.DataFrame([build_journal_entry(**entry)])
    output = pd.concat([current, next_row], ignore_index=True)
    output = output[JOURNAL_COLUMNS]
    output.to_csv(journal_path, index=False)
    return output

