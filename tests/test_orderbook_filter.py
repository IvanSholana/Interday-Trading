from __future__ import annotations

import pandas as pd

from interday_liquidity_screener.constants import WatchlistStatus
from interday_liquidity_screener.orderbook_filter import (
    OrderbookFilterConfig,
    is_corp_action_active,
    is_notation_risky,
    load_orderbook_universe,
    normalize_orderbook_payload,
)


def payload(**overrides) -> dict:
    data = {
        "symbol": "YUPI",
        "name": "Yupi Indo Jelly Gum Tbk.",
        "lastprice": 1225,
        "open": 1210,
        "high": 1240,
        "low": 1175,
        "close": 1225,
        "previous": 1210,
        "change": 15,
        "percentage_change": 1.24,
        "average": 1215,
        "volume": 100000,
        "value": 6_000_000_000,
        "frequency": 150,
        "foreign": "0.00",
        "domestic": "100.00",
        "fbuy": 0,
        "fsell": 0,
        "fnet": 100_000_000,
        "ara": 1500,
        "arb": 1000,
        "tradable": True,
        "notation": "",
        "uma": False,
        "corp_action": "",
        "bid": [
            {"price": "1225", "que_num": "1", "volume": "3300"},
            {"price": "1210", "que_num": "7", "volume": "4200"},
            {"price": "1200", "que_num": "7", "volume": "1300"},
            {"price": "1195", "que_num": "4", "volume": "400"},
            {"price": "1190", "que_num": "4", "volume": "1600"},
        ],
        "offer": [
            {"price": "1230", "que_num": "4", "volume": "8000"},
            {"price": "1235", "que_num": "3", "volume": "1000"},
            {"price": "1240", "que_num": "2", "volume": "1000"},
            {"price": "1245", "que_num": "2", "volume": "1000"},
            {"price": "1250", "que_num": "2", "volume": "1000"},
        ],
    }
    data.update(overrides)
    return {"data": data, "message": "ok"}


def test_empty_bid_offer_no_orderbook_data() -> None:
    row = normalize_orderbook_payload(payload(bid=[], offer=[]), "YUPI")

    assert row["orderbook_status"] == "NO_ORDERBOOK_DATA"


def test_spread_from_best_bid_offer() -> None:
    row = normalize_orderbook_payload(payload(), "YUPI")

    assert row["best_bid"] == 1225
    assert row["best_offer"] == 1230
    assert row["spread"] == 5
    assert round(row["spread_pct"], 4) == 0.0041


def test_bid_depth_positive_when_bid_top5_exceeds_offer_top5() -> None:
    row = normalize_orderbook_payload(payload(offer=[{"price": "1230", "que_num": "1", "volume": "100"}]), "YUPI")

    assert row["depth_imbalance_top5"] > 0


def test_offer_wall_ratio_waits() -> None:
    row = normalize_orderbook_payload(payload(), "YUPI", OrderbookFilterConfig(max_offer_wall_ratio=2.5))

    assert row["offer_wall_ratio_top5"] >= 3.0
    assert row["orderbook_status"] == "WAIT_OFFER_WALL"


def test_not_tradable_rejected() -> None:
    row = normalize_orderbook_payload(payload(tradable=False), "YUPI")

    assert row["orderbook_status"] == "REJECT_NOT_TRADABLE"


def test_uma_rejected() -> None:
    row = normalize_orderbook_payload(payload(uma=True), "YUPI")

    assert row["orderbook_status"] == "REJECT_UMA_OR_NOTATION_RISK"


def test_corporate_action_rejected() -> None:
    row = normalize_orderbook_payload(payload(corp_action={"active": True, "text": "Corporate Action"}), "YUPI")

    assert row["corp_action_active"] is True
    assert row["orderbook_status"] == "REJECT_CORPORATE_ACTION_RISK"


def test_inactive_corporate_action_dict_is_not_rejected() -> None:
    row = normalize_orderbook_payload(payload(corp_action={"active": False, "text": "Perusahaan Memiliki Corporate Action"}), "YUPI")

    assert row["corp_action_active"] is False
    assert row["orderbook_status"] != "REJECT_CORPORATE_ACTION_RISK"


def test_inactive_corporate_action_string_dict_is_not_rejected() -> None:
    value = "{'active': False, 'icon': 'x', 'text': 'Perusahaan Memiliki Corporate Action'}"
    row = normalize_orderbook_payload(payload(corp_action=value), "YUPI")

    assert row["corp_action_active"] is False
    assert row["orderbook_status"] != "REJECT_CORPORATE_ACTION_RISK"


def test_empty_notation_and_corporate_action_arrays_are_safe() -> None:
    row = normalize_orderbook_payload(payload(notation=[], corp_action=[]), "YUPI")

    assert row["notation_risky"] is False
    assert row["corp_action_active"] is False
    assert row["orderbook_status"] != "REJECT_UMA_OR_NOTATION_RISK"
    assert row["orderbook_status"] != "REJECT_CORPORATE_ACTION_RISK"


def test_empty_notation_string_list_is_not_risky() -> None:
    row = normalize_orderbook_payload(payload(notation="[]"), "YUPI")

    assert row["notation_risky"] is False
    assert row["orderbook_status"] != "REJECT_UMA_OR_NOTATION_RISK"


def test_non_empty_notation_is_risky() -> None:
    row = normalize_orderbook_payload(payload(notation=["X"]), "YUPI")

    assert row["notation_risky"] is True
    assert row["orderbook_status"] == "REJECT_UMA_OR_NOTATION_RISK"


def test_jsonish_helpers() -> None:
    assert is_corp_action_active("{'active': False}") is False
    assert is_corp_action_active('{"active": true}') is True
    assert is_notation_risky("[]") is False
    assert is_notation_risky("['X']") is True


def test_near_ara_waits() -> None:
    row = normalize_orderbook_payload(payload(ara=1240), "YUPI")

    assert row["near_ara"] is True
    assert row["orderbook_status"] == "WAIT_NEAR_ARA_ARB"


def test_supportive_orderbook() -> None:
    row = normalize_orderbook_payload(
        payload(
            bid=[{"price": "1225", "que_num": "1", "volume": "10000"} for _ in range(5)],
            offer=[{"price": "1230", "que_num": "1", "volume": "1000"} for _ in range(5)],
        ),
        "YUPI",
    )

    assert row["orderbook_status"] == "ORDERBOOK_SUPPORTIVE"


def test_morning_universe_includes_hybrid_candidates_needing_orderbook(tmp_path) -> None:
    stage2_path = tmp_path / "stage2.csv"
    bandar_path = tmp_path / "stage3b.csv"
    watchlist_path = tmp_path / "hybrid.csv"
    pd.DataFrame(
        [
            {
                "ticker": "PGEO",
                "is_data_valid": True,
                "liquidity_bucket": "HIGH_LIQUIDITY",
                "bandar_watch_eligible": True,
                "technical_context": "BREAKOUT_NEAR",
            },
            {
                "ticker": "MAPI",
                "is_data_valid": True,
                "liquidity_bucket": "HIGH_LIQUIDITY",
                "bandar_watch_eligible": False,
                "technical_context": "TOO_QUIET_ABSOLUTE",
            },
            {
                "ticker": "SKIP",
                "is_data_valid": True,
                "liquidity_bucket": "HIGH_LIQUIDITY",
                "bandar_watch_eligible": False,
                "technical_context": "TOO_QUIET_ABSOLUTE",
            },
        ]
    ).to_csv(stage2_path, index=False)
    pd.DataFrame(
        [
            {"ticker": "PGEO", "broker_activity_available": True, "bandarmology_signal": "MILD_ACCUMULATION"},
            {"ticker": "MAPI", "broker_activity_available": False, "bandarmology_signal": "NO_BROKER_DATA"},
            {"ticker": "SKIP", "broker_activity_available": False, "bandarmology_signal": "NO_BROKER_DATA"},
        ]
    ).to_csv(bandar_path, index=False)
    pd.DataFrame(
        [
            {"symbol": "MAPI", "final_status": WatchlistStatus.NEED_ORDERBOOK.value},
            {"symbol": "SKIP", "final_status": WatchlistStatus.SKIP.value},
        ]
    ).to_csv(watchlist_path, index=False)

    universe = load_orderbook_universe(stage2_path, bandar_path, watchlist_path)

    assert set(universe["ticker"]) == {"PGEO", "MAPI"}
