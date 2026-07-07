from __future__ import annotations

from interday_liquidity_screener.ticker_universe import UNIVERSE_BY_KEY, load_universe_tickers, read_universe_text


def test_universe_presets_include_requested_modes() -> None:
    for key in ["manual", "all_idx", "syariah", "lq45", "idx30", "idx80", "jii", "kompas100"]:
        assert key in UNIVERSE_BY_KEY


def test_lq45_universe_file_loads_normalized_tickers() -> None:
    tickers = load_universe_tickers("lq45")

    assert "BBCA.JK" in tickers
    assert "TLKM.JK" in tickers


def test_manual_universe_has_no_default_text() -> None:
    assert read_universe_text("manual") == ""

