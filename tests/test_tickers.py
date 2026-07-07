from __future__ import annotations

import pytest

from interday_liquidity_screener.tickers import load_tickers, normalize_ticker


def test_normalize_ticker_adds_jk_suffix() -> None:
    assert normalize_ticker("bbca") == "BBCA.JK"
    assert normalize_ticker("TLKM.JK") == "TLKM.JK"
    assert normalize_ticker("  ") is None


def test_normalize_ticker_rejects_invalid_symbols() -> None:
    with pytest.raises(ValueError):
        normalize_ticker("BBCA/JK")


def test_load_tickers_from_txt_deduplicates_and_sorts(tmp_path) -> None:
    tickers_file = tmp_path / "tickers.txt"
    tickers_file.write_text("# daftar utama\nbbca\n\nTLKM.JK\nBBCA\nASII # inline comment\n", encoding="utf-8")

    assert load_tickers(tickers_file) == ["ASII.JK", "BBCA.JK", "TLKM.JK"]


def test_load_tickers_from_csv_uses_ticker_column(tmp_path) -> None:
    tickers_file = tmp_path / "tickers.csv"
    tickers_file.write_text("ticker,name\nbbri,Bank BRI\nbmri,Bank Mandiri\n", encoding="utf-8")

    assert load_tickers(tickers_file) == ["BBRI.JK", "BMRI.JK"]
