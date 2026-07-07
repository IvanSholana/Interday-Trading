from __future__ import annotations

from interday_liquidity_screener.journal import append_journal_entry, load_journal


def test_append_journal_entry_calculates_pnl(tmp_path):
    path = tmp_path / "journal.csv"
    append_journal_entry(
        path,
        {
            "date": "2026-07-06",
            "symbol": "TEST",
            "mode": "bpjs_live",
            "status_before_entry": "EXECUTION_DRAFT",
            "entry_price": 1000,
            "exit_price": 1020,
            "lot": 1,
            "fees": 500,
            "slippage": 100,
        },
    )
    journal = load_journal(path)
    assert len(journal) == 1
    assert journal.iloc[0]["gross_pnl"] == 2000
    assert journal.iloc[0]["net_pnl"] == 1400

