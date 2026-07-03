from __future__ import annotations

import pandas as pd

from interday_liquidity_screener.technical import (
    build_technical_reason,
    calculate_atr,
    calculate_rsi,
    calculate_technical_features,
    classify_technical_context,
    classify_relative_activity,
    classify_entry_setup,
    is_bandar_watch_eligible,
    build_latest_technical_row,
)


def make_ohlcv(days: int = 150, close_start: float = 1000, volume: int = 1_000_000) -> pd.DataFrame:
    index = pd.date_range("2026-01-01", periods=days, freq="B")
    closes = [close_start + i * 2 for i in range(days)]
    return pd.DataFrame(
        {
            "open": [price * 0.995 for price in closes],
            "high": [price * 1.02 for price in closes],
            "low": [price * 0.98 for price in closes],
            "close": closes,
            "adjusted_close": closes,
            "volume": [volume for _ in range(days)],
        },
        index=index,
    )


def liquid_row(**overrides) -> dict:
    row = {
        "is_data_valid": True,
        "data_points": 150,
        "liquidity_bucket": "HIGH_LIQUIDITY",
        "close": 110,
        "value_est": 110_000_000_000,
        "ma20": 105,
        "ma50": 100,
        "ma100": 95,
        "ma200": 90,
        "high_20d": 112,
        "low_20d": 95,
        "distance_to_ma20": 0.02,
        "distance_to_ma50": 0.10,
        "distance_from_20d_low": 0.20,
        "rsi14": 60,
        "atr_pct": 0.03,
        "volatility_20d": 0.02,
        "volume_ratio": 1.1,
        "value_ratio": 1.1,
        "return_1d": 0.01,
        "return_3d": 0.02,
        "return_5d": 0.03,
        "return_20d": 0.08,
        "close_location": 0.7,
        "trend_score": 100,
        "momentum_score": 100,
        "volatility_score": 100,
    }
    row.update(overrides)
    return row


def test_rsi_does_not_error_with_valid_data() -> None:
    rsi = calculate_rsi(make_ohlcv()["close"])

    assert len(rsi) == 150
    assert rsi.notna().all()


def test_atr_does_not_error_with_valid_data() -> None:
    atr = calculate_atr(make_ohlcv())

    assert len(atr) == 150
    assert atr.tail(20).notna().all()


def test_less_than_120_days_becomes_invalid_data() -> None:
    stage_1 = {"ticker": "TEST", "yahoo_ticker": "TEST.JK", "liquidity_bucket": "HIGH_LIQUIDITY"}
    result = build_latest_technical_row(stage_1, make_ohlcv(days=80))

    assert result["entry_setup"] == "INVALID_DATA"
    assert result["is_data_valid"] is False


def test_liquid_healthy_setup_becomes_watch_or_specific_candidate() -> None:
    setup = classify_entry_setup(liquid_row())

    assert setup in {"WATCH_ENTRY", "BREAKOUT_CANDIDATE", "PULLBACK_CANDIDATE", "REBOUND_CANDIDATE"}


def test_low_close_location_and_negative_return_is_not_watch_entry() -> None:
    setup = classify_entry_setup(
        liquid_row(close_location=0.0, return_1d=-0.02, trend_score=80, momentum_score=20)
    )

    assert setup != "WATCH_ENTRY"


def test_high_atr_pct_is_too_volatile() -> None:
    assert classify_entry_setup(liquid_row(atr_pct=0.07)) == "LIQUID_BUT_TOO_VOLATILE"


def test_low_value_and_volume_ratio_is_too_quiet() -> None:
    assert classify_entry_setup(
        liquid_row(
            value_ratio=0.4,
            volume_ratio=0.4,
            value_est=5_000_000_000,
            high_20d=200,
            distance_to_ma20=0.10,
        )
    ) == "LIQUID_BUT_TOO_QUIET"


def test_calculate_technical_features_adds_expected_columns() -> None:
    features = calculate_technical_features(make_ohlcv(days=250))

    for column in ["ma20", "ma50", "ma100", "ma200", "rsi14", "atr14", "volume_ratio", "value_ratio"]:
        assert column in features.columns
    assert len(features) == 250


def test_broad_technical_context_can_keep_liquid_weak_stock_for_bandar_watch() -> None:
    row = liquid_row(
        trend_score=10,
        momentum_score=30,
        value_est=100_000_000_000,
        high_20d=200,
        close=100,
        return_1d=-0.01,
    )
    row["technical_context"] = classify_technical_context(row)

    assert row["technical_context"] == "TECHNICALLY_WEAK_BUT_LIQUID"
    assert is_bandar_watch_eligible(row) is True


def test_big_cap_quiet_relative_activity_is_not_too_quiet() -> None:
    row = liquid_row(
        value_ratio=0.39,
        volume_ratio=0.38,
        value_est=841_000_000_000,
        trend_score=10,
        momentum_score=70,
        close=90,
        ma20=100,
        ma50=110,
        ma100=120,
        ma200=130,
    )

    assert classify_relative_activity(row) == "QUIET"
    assert classify_entry_setup(row) == "LIQUID_BUT_WEAK_TREND"


def test_weak_trend_and_momentum_label() -> None:
    assert classify_entry_setup(
        liquid_row(
            close=90,
            ma50=120,
            high_20d=150,
            rsi14=40,
            return_1d=-0.01,
            close_location=0.5,
            trend_score=0,
            momentum_score=0,
        )
    ) == "LIQUID_BUT_WEAK_TREND_AND_MOMENTUM"


def test_weak_trend_only_label() -> None:
    assert classify_entry_setup(
        liquid_row(close=90, ma50=120, high_20d=150, trend_score=10, momentum_score=70)
    ) == "LIQUID_BUT_WEAK_TREND"


def test_rebound_with_mild_support_uses_mild_reason() -> None:
    row = liquid_row(
        close=90,
        ma50=120,
        high_20d=130,
        distance_from_20d_low=0.05,
        return_1d=0.02,
        close_location=0.7,
        rsi14=50,
        value_ratio=0.81,
        volume_ratio=0.86,
    )
    row["entry_setup"] = classify_entry_setup(row)

    assert row["entry_setup"] == "REBOUND_CANDIDATE"
    assert "mild_activity_support" in build_technical_reason(row)
    assert "confirmation" not in build_technical_reason(row)


def test_rebound_with_confirmation_uses_confirmation_reason() -> None:
    row = liquid_row(
        close=90,
        ma50=120,
        high_20d=130,
        distance_from_20d_low=0.05,
        return_1d=0.02,
        close_location=0.7,
        rsi14=50,
        value_ratio=1.05,
        volume_ratio=0.86,
    )
    row["entry_setup"] = classify_entry_setup(row)

    assert row["entry_setup"] == "REBOUND_CANDIDATE"
    assert "activity_confirmation" in build_technical_reason(row)
