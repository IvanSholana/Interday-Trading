"""Point-in-time ticker-universe membership store."""

from __future__ import annotations

from pathlib import Path
import sqlite3

import pandas as pd
from typing import Callable


class UniverseHistoryStore:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS universe_membership (
                    universe_name TEXT NOT NULL,
                    ticker TEXT NOT NULL,
                    valid_from TEXT NOT NULL,
                    valid_to TEXT,
                    source TEXT NOT NULL,
                    ingested_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (universe_name, ticker, valid_from, source)
                )
                """
            )

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def add_membership(self, universe_name: str, ticker: str, valid_from: pd.Timestamp,
                       valid_to: pd.Timestamp | None = None, source: str = "") -> None:
        with self._connect() as connection:
            connection.execute(
                """INSERT OR REPLACE INTO universe_membership
                   (universe_name,ticker,valid_from,valid_to,source) VALUES (?,?,?,?,?)""",
                (universe_name, ticker.replace(".JK", "").upper(), pd.Timestamp(valid_from).isoformat(),
                 pd.Timestamp(valid_to).isoformat() if valid_to is not None else None, source),
            )

    def members_as_of(self, universe_name: str, decision_timestamp: pd.Timestamp) -> list[str]:
        cutoff = pd.Timestamp(decision_timestamp).isoformat()
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT ticker FROM universe_membership
                   WHERE universe_name=? AND valid_from<=? AND (valid_to IS NULL OR valid_to>=?)
                   ORDER BY ticker""",
                (universe_name, cutoff, cutoff),
            ).fetchall()
        return [row[0] for row in rows]

    def version(self, universe_name: str) -> str:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*),MIN(valid_from),MAX(COALESCE(valid_to,valid_from)) FROM universe_membership WHERE universe_name=?",
                (universe_name,),
            ).fetchone()
        return f"{universe_name}:{row[0]}:{row[1] or 'EMPTY'}:{row[2] or 'EMPTY'}"

    def provider(self, universe_name: str) -> Callable[[pd.Timestamp], list[str]]:
        return lambda decision_timestamp: self.members_as_of(universe_name, decision_timestamp)


__all__ = ["UniverseHistoryStore"]
