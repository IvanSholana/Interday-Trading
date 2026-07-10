"""Point-in-time corporate-action event store.

Price adjustment ratios are intentionally not used as an event source: they
encode hindsight. Only events announced by the decision timestamp are visible.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3
from typing import Iterable

import pandas as pd


@dataclass(frozen=True)
class CorporateActionEvent:
    ticker: str
    event_type: str
    announcement_timestamp: pd.Timestamp
    cum_date: pd.Timestamp | None = None
    ex_date: pd.Timestamp | None = None
    recording_date: pd.Timestamp | None = None
    effective_date: pd.Timestamp | None = None
    source: str = ""
    ingested_at: pd.Timestamp | None = None


class CorporateActionStore:
    """Small deterministic event store supporting as-of queries."""

    def __init__(self, events: Iterable[CorporateActionEvent] = (), db_path: str | Path | None = None) -> None:
        self._events = tuple(events)
        self.db_path = Path(db_path) if db_path is not None else None
        if self.db_path is not None:
            self._initialize()

    def _connect(self) -> sqlite3.Connection:
        if self.db_path is None:
            raise ValueError("persistent corporate-action store requires db_path")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        return sqlite3.connect(self.db_path)

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS corporate_actions (
                    ticker TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    announcement_timestamp TEXT NOT NULL,
                    cum_date TEXT,
                    ex_date TEXT,
                    recording_date TEXT,
                    effective_date TEXT,
                    source TEXT NOT NULL,
                    ingested_at TEXT NOT NULL,
                    PRIMARY KEY (ticker, event_type, announcement_timestamp, source)
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_corporate_actions_asof ON corporate_actions(ticker, announcement_timestamp)"
            )

    @staticmethod
    def _iso(value: pd.Timestamp | None) -> str | None:
        return None if value is None or pd.isna(value) else pd.Timestamp(value).isoformat()

    def add(self, event: CorporateActionEvent) -> None:
        if self.db_path is None:
            self._events = (*self._events, event)
            return
        ingested_at = event.ingested_at or pd.Timestamp.now(tz="UTC").tz_localize(None)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO corporate_actions
                (ticker, event_type, announcement_timestamp, cum_date, ex_date, recording_date,
                 effective_date, source, ingested_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(ticker, event_type, announcement_timestamp, source) DO UPDATE SET
                    cum_date=excluded.cum_date, ex_date=excluded.ex_date,
                    recording_date=excluded.recording_date, effective_date=excluded.effective_date,
                    ingested_at=excluded.ingested_at
                """,
                (event.ticker.replace(".JK", "").upper(), event.event_type,
                 self._iso(event.announcement_timestamp), self._iso(event.cum_date), self._iso(event.ex_date),
                 self._iso(event.recording_date), self._iso(event.effective_date), event.source,
                 self._iso(pd.Timestamp(ingested_at))),
            )

    def ingest_frame(self, frame: pd.DataFrame) -> int:
        required = {"ticker", "event_type", "announcement_timestamp", "source"}
        missing = required.difference(frame.columns)
        if missing:
            raise ValueError(f"corporate action input missing columns: {', '.join(sorted(missing))}")
        for _, row in frame.iterrows():
            self.add(CorporateActionEvent(
                ticker=str(row["ticker"]), event_type=str(row["event_type"]),
                announcement_timestamp=pd.Timestamp(row["announcement_timestamp"]),
                cum_date=pd.Timestamp(row["cum_date"]) if pd.notna(row.get("cum_date")) else None,
                ex_date=pd.Timestamp(row["ex_date"]) if pd.notna(row.get("ex_date")) else None,
                recording_date=pd.Timestamp(row["recording_date"]) if pd.notna(row.get("recording_date")) else None,
                effective_date=pd.Timestamp(row["effective_date"]) if pd.notna(row.get("effective_date")) else None,
                source=str(row["source"]),
                ingested_at=pd.Timestamp(row["ingested_at"]) if pd.notna(row.get("ingested_at")) else None,
            ))
        return len(frame)

    def as_of(self, decision_timestamp: pd.Timestamp, ticker: str | None = None) -> tuple[CorporateActionEvent, ...]:
        cutoff = pd.Timestamp(decision_timestamp)
        normalized_ticker = ticker.replace(".JK", "").upper() if ticker else None
        visible = list(self._events)
        if self.db_path is not None:
            params: list[str] = [cutoff.isoformat()]
            where = "announcement_timestamp <= ?"
            if normalized_ticker:
                where += " AND ticker = ?"
                params.append(normalized_ticker)
            with self._connect() as connection:
                rows = connection.execute(
                    f"SELECT ticker,event_type,announcement_timestamp,cum_date,ex_date,recording_date,effective_date,source,ingested_at FROM corporate_actions WHERE {where}",
                    params,
                ).fetchall()
            visible.extend(CorporateActionEvent(
                row[0], row[1], pd.Timestamp(row[2]),
                pd.Timestamp(row[3]) if row[3] else None, pd.Timestamp(row[4]) if row[4] else None,
                pd.Timestamp(row[5]) if row[5] else None, pd.Timestamp(row[6]) if row[6] else None,
                row[7], pd.Timestamp(row[8]) if row[8] else None,
            ) for row in rows)
        filtered = []
        for event in visible:
            event_ticker = event.ticker.replace(".JK", "").upper()
            if normalized_ticker and event_ticker != normalized_ticker:
                continue
            if pd.Timestamp(event.announcement_timestamp) <= cutoff:
                filtered.append(event)
        return tuple(sorted(filtered, key=lambda event: pd.Timestamp(event.announcement_timestamp)))

    def blackout_dates_as_of(self, decision_timestamp: pd.Timestamp, ticker: str) -> list[pd.Timestamp]:
        dates: list[pd.Timestamp] = []
        for event in self.as_of(decision_timestamp, ticker):
            event_date = event.ex_date or event.effective_date or event.cum_date
            if event_date is not None:
                dates.append(pd.Timestamp(event_date).normalize())
        return dates


__all__ = ["CorporateActionEvent", "CorporateActionStore"]
