from __future__ import annotations

import io
from urllib.error import HTTPError

import pytest

from interday_liquidity_screener import stockbit_collector as collector
from interday_liquidity_screener.stockbit_collector import (
    StockbitCollectorConfig,
    get_stockbit_token,
    parse_number,
    parse_windows_arg,
    resolve_window_dates,
    save_raw_json,
)


def test_parse_number_suffixes_and_symbols() -> None:
    assert parse_number("26.8B") == 26_800_000_000
    assert parse_number("99.4K") == 99_400
    assert parse_number("2,697") == 2697
    assert parse_number("2.14931e+06") == 2_149_310
    assert parse_number("-") is None


def test_parse_windows_arg() -> None:
    assert parse_windows_arg("1D,3D,5D") == {"1D": 1, "3D": 3, "5D": 5}


def test_parse_windows_arg_accepts_powershell_numeric_suffix_loss() -> None:
    assert parse_windows_arg("1,3,5") == {"1D": 1, "3D": 3, "5D": 5}


def test_resolve_window_dates_1d_same_day() -> None:
    assert resolve_window_dates("2026-07-02", "1D", 1) == ("2026-07-02", "2026-07-02")


def test_save_raw_json_multi_window_path(tmp_path) -> None:
    path = save_raw_json({"data": {}}, "BBRI", "2026-06-29", "2026-07-02", tmp_path, window_label="5D")

    assert path.name == "BBRI_5D_2026-06-29_2026-07-02.json"


def test_missing_stockbit_token_raises_clear_error(monkeypatch) -> None:
    monkeypatch.delenv("STOCKBIT_TOKEN", raising=False)
    monkeypatch.setattr(collector, "_load_dotenv", lambda path=".env": None)

    with pytest.raises(RuntimeError, match="STOCKBIT_TOKEN is empty"):
        get_stockbit_token()


def test_401_raises_token_expired_message(monkeypatch) -> None:
    def fake_urlopen(*args, **kwargs):
        raise HTTPError("url", 401, "Unauthorized", {}, None)

    monkeypatch.setattr(collector, "urlopen", fake_urlopen)

    with pytest.raises(RuntimeError, match="expired/invalid"):
        collector.fetch_marketdetector("BBRI", "2026-06-01", "2026-06-19", StockbitCollectorConfig(), token="x")


def test_429_retries_then_succeeds(monkeypatch) -> None:
    calls = {"count": 0}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b'{"data":[]}'

    def fake_urlopen(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            raise HTTPError("url", 429, "Too Many", {}, None)
        return FakeResponse()

    monkeypatch.setattr(collector, "urlopen", fake_urlopen)
    monkeypatch.setattr(collector.time, "sleep", lambda seconds: None)

    payload = collector.fetch_marketdetector(
        "BBRI",
        "2026-06-01",
        "2026-06-19",
        StockbitCollectorConfig(max_retries=1, retry_backoff_seconds=0),
        token="x",
    )

    assert payload == {"data": []}
    assert calls["count"] == 2


def sample_stockbit_payload() -> dict:
    return {
        "message": "ok",
        "data": {
            "bandar_detector": {
                "average": 2812.0059,
                "avg": {"accdist": "Big Dist", "amount": -1140144500000, "percent": -30.726545, "vol": -4054559.5},
                "avg5": {"accdist": "Dist", "amount": -1000, "percent": -5, "vol": -10},
                "broker_accdist": "Dist",
                "number_broker_buysell": 45,
                "top1": {"accdist": "Dist", "amount": -1, "percent": -2, "vol": -3},
                "top3": {"accdist": "Big Dist", "amount": -2, "percent": -20, "vol": -4},
                "top5": {"accdist": "Big Dist", "amount": -3, "percent": -25, "vol": -5},
                "top10": {"accdist": "Dist", "amount": -4, "percent": -10, "vol": -6},
                "total_buyer": 66,
                "total_seller": 21,
                "value": 3710617000000,
                "volume": 13195624,
            },
            "broker_summary": {
                "brokers_buy": [
                    {
                        "blot": "2.14931e+06",
                        "blotv": "5.482582e+08",
                        "bval": "6.0714307e+11",
                        "bvalv": "1.568527139e+12",
                        "netbs_broker_code": "XL",
                        "netbs_buy_avg_price": "2860.927823788135",
                        "type": "Lokal",
                        "freq": "273476",
                    }
                ],
                "brokers_sell": [
                    {
                        "slot": "1000",
                        "sval": "2.8B",
                        "slotv": "2000",
                        "svalv": "5.7B",
                        "netbs_broker_code": "YP",
                        "netbs_sell_avg_price": "2800",
                        "type": "Asing",
                        "freq": "21K",
                    }
                ],
            },
        },
    }


def test_normalize_real_stockbit_detector_summary() -> None:
    row = collector.normalize_bandar_detector_summary(sample_stockbit_payload(), "BBRI", "2026-06-01", "2026-06-19", "20D", 20)

    assert row["window_label"] == "20D"
    assert row["broker_accdist"] == "Dist"
    assert row["avg_accdist"] == "Big Dist"
    assert row["avg_amount"] == -1140144500000
    assert row["top3_accdist"] == "Big Dist"


def test_normalize_real_stockbit_broker_summary_long() -> None:
    rows = collector.normalize_broker_summary_long(sample_stockbit_payload(), "BBRI", "2026-06-01", "2026-06-19")

    assert rows[0]["side"] == "BUY"
    assert rows[0]["broker_code"] == "XL"
    assert rows[0]["net_lot"] == 2_149_310
    assert rows[1]["side"] == "SELL"
    assert rows[1]["net_value"] == 2_800_000_000
    assert rows[1]["frequency"] == 21_000
