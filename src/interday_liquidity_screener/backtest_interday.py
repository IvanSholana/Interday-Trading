"""Legacy Stage-4 signal replay.

This module does not recompute the pipeline point-in-time. New research should
use ``backtest.walk_forward.WalkForwardPipelineBacktester``; the explicit
``SignalReplayBacktester`` wrapper preserves this legacy workflow.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

import pandas as pd

from .market_data_cache import DEFAULT_MARKET_DATA_DB, get_incremental_ohlcv, normalize_ohlcv_frame


VALID_ENTRY_MODES = {"next_open", "next_day_entry_zone"}
VALID_AMBIGUOUS_POLICIES = {"stop_first", "tp_first", "skip_trade"}
SUPPORT_COLUMNS = [
    "ticker",
    "yahoo_ticker",
    "signal_date",
    "strategy_mode",
    "trade_status_stage4",
    "backtest_status",
    "planned_entry_price",
    "planned_entry_trigger_price",
    "planned_entry_zone_low",
    "planned_entry_zone_high",
    "planned_stop_loss",
    "planned_take_profit_1",
    "planned_take_profit_2",
    "planned_time_stop_days",
    "entry_mode",
    "entry_date",
    "actual_entry_price",
    "exit_date",
    "exit_price",
    "exit_reason",
    "holding_days",
    "gross_return_pct",
    "net_return_pct",
    "net_pnl_amount",
    "position_size_lots",
    "shares",
    "position_value",
    "buy_fee_pct",
    "sell_fee_pct",
    "slippage_pct",
    "mfe_pct",
    "mae_pct",
    "max_favorable_price",
    "max_adverse_price",
    "tp1_hit",
    "tp2_hit",
    "sl_hit",
    "time_stop_exit",
    "same_day_ambiguous",
    "technical_context",
    "bandarmology_signal",
    "bandarmology_score",
    "orderbook_status",
    "orderbook_score",
    "trade_reason",
    "trade_summary",
]


@dataclass(frozen=True)
class InterdayBacktestConfig:
    price_cache_dir: str | Path = "data/cache/ohlcv"
    market_data_db: str | Path = DEFAULT_MARKET_DATA_DB
    period: str = "1y"
    entry_mode: str = "next_open"
    time_stop_days: int = 10
    buy_fee_pct: float = 0.0015
    sell_fee_pct: float = 0.0025
    slippage_pct: float = 0.001
    initial_capital: float = 10_000_000
    max_entry_gap_pct: float = 0.03
    reject_if_entry_gap_too_high: bool = True
    exit_policy: str = "tp1_exit"
    same_day_ambiguous_policy: str = "stop_first"
    lot_size: int = 100
    refresh_price_cache: bool = False

    def __post_init__(self) -> None:
        if self.entry_mode not in VALID_ENTRY_MODES:
            raise ValueError(f"entry_mode must be one of {', '.join(sorted(VALID_ENTRY_MODES))}")
        if self.exit_policy != "tp1_exit":
            raise ValueError("Only exit_policy='tp1_exit' is supported in Stage 5A MVP")
        if self.same_day_ambiguous_policy not in VALID_AMBIGUOUS_POLICIES:
            raise ValueError(f"same_day_ambiguous_policy must be one of {', '.join(sorted(VALID_AMBIGUOUS_POLICIES))}")


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


def _date(value: Any) -> pd.Timestamp | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    parsed = pd.to_datetime(value, errors="coerce")
    return None if pd.isna(parsed) else pd.Timestamp(parsed).normalize()


def _normalize_price_history(df: pd.DataFrame) -> pd.DataFrame:
    normalized = normalize_ohlcv_frame(df)
    keep = [column for column in ["open", "high", "low", "close", "volume"] if column in normalized.columns]
    return normalized[keep].copy()


def load_price_history_from_cache(ticker: str, cache_dir: str | Path) -> pd.DataFrame:
    path = Path(cache_dir) / f"{ticker}.csv"
    if not path.exists():
        return pd.DataFrame()
    return _normalize_price_history(pd.read_csv(path))


def save_price_history_to_cache(ticker: str, df: pd.DataFrame, cache_dir: str | Path) -> Path:
    path = Path(cache_dir)
    path.mkdir(parents=True, exist_ok=True)
    file_path = path / f"{ticker}.csv"
    output = _normalize_price_history(df).copy()
    output.index.name = "Date"
    output.to_csv(file_path)
    return file_path


def fetch_price_history(yahoo_ticker: str, period: str) -> pd.DataFrame:
    return get_incremental_ohlcv(yahoo_ticker, period, db_path=DEFAULT_MARKET_DATA_DB)


def get_price_history(
    yahoo_ticker: str,
    cache_dir: str | Path,
    period: str,
    refresh: bool = False,
    market_data_db: str | Path = DEFAULT_MARKET_DATA_DB,
) -> pd.DataFrame:
    history = get_incremental_ohlcv(yahoo_ticker, period, db_path=market_data_db, refresh=refresh)
    if not history.empty:
        return _normalize_price_history(history)

    if not refresh:
        cached = load_price_history_from_cache(yahoo_ticker, cache_dir)
        if not cached.empty:
            return cached
    return pd.DataFrame()


def is_stage4_signal_eligible(row: dict[str, Any] | pd.Series) -> bool:
    return (
        str(row.get("strategy_mode", "interday")).lower() == "interday"
        and _is_true(row.get("is_plan_valid"))
        and row.get("trade_status") == "VALID_TRADE_PLAN"
        and _int(row.get("executable_position_size_lots", row.get("position_size_lots"))) > 0
        and _float(row.get("entry_price")) is not None
        and _float(row.get("stop_loss")) is not None
        and _float(row.get("take_profit_1")) is not None
        and _float(row.get("take_profit_2")) is not None
    )


def _base_result(row: dict[str, Any] | pd.Series, config: InterdayBacktestConfig, status: str) -> dict[str, Any]:
    return {
        "ticker": row.get("ticker"),
        "yahoo_ticker": row.get("yahoo_ticker"),
        "signal_date": _date(row.get("last_date")),
        "strategy_mode": row.get("strategy_mode", "interday"),
        "trade_status_stage4": row.get("trade_status"),
        "backtest_status": status,
        "planned_entry_price": _float(row.get("entry_price")),
        "planned_entry_trigger_price": _float(row.get("entry_trigger_price")),
        "planned_entry_zone_low": _float(row.get("entry_zone_low")),
        "planned_entry_zone_high": _float(row.get("entry_zone_high")),
        "planned_stop_loss": _float(row.get("stop_loss")),
        "planned_take_profit_1": _float(row.get("take_profit_1")),
        "planned_take_profit_2": _float(row.get("take_profit_2")),
        "planned_time_stop_days": _int(row.get("time_stop_days"), config.time_stop_days),
        "entry_mode": config.entry_mode,
        "entry_date": pd.NA,
        "actual_entry_price": pd.NA,
        "exit_date": pd.NA,
        "exit_price": pd.NA,
        "exit_reason": pd.NA,
        "holding_days": pd.NA,
        "gross_return_pct": pd.NA,
        "net_return_pct": pd.NA,
        "net_pnl_amount": pd.NA,
        "position_size_lots": _int(row.get("executable_position_size_lots", row.get("position_size_lots"))),
        "shares": pd.NA,
        "position_value": pd.NA,
        "buy_fee_pct": config.buy_fee_pct,
        "sell_fee_pct": config.sell_fee_pct,
        "slippage_pct": config.slippage_pct,
        "mfe_pct": pd.NA,
        "mae_pct": pd.NA,
        "max_favorable_price": pd.NA,
        "max_adverse_price": pd.NA,
        "tp1_hit": False,
        "tp2_hit": False,
        "sl_hit": False,
        "time_stop_exit": False,
        "same_day_ambiguous": False,
        "technical_context": row.get("technical_context"),
        "bandarmology_signal": row.get("bandarmology_signal"),
        "bandarmology_score": _float(row.get("bandarmology_score")),
        "orderbook_status": row.get("orderbook_status"),
        "orderbook_score": _float(row.get("orderbook_score")),
        "trade_reason": row.get("trade_reason"),
        "trade_summary": row.get("trade_summary"),
    }


def _next_bar_after(history: pd.DataFrame, signal_date: pd.Timestamp) -> tuple[int | None, pd.Timestamp | None, pd.Series | None]:
    future = history[history.index > signal_date]
    if future.empty:
        return None, None, None
    date = future.index[0]
    return history.index.get_loc(date), date, future.iloc[0]


def _entry_from_signal(
    row: dict[str, Any] | pd.Series,
    history: pd.DataFrame,
    config: InterdayBacktestConfig,
) -> tuple[str, int | None, pd.Timestamp | None, float | None]:
    signal_date = _date(row.get("last_date"))
    if signal_date is None:
        return "NO_SIGNAL_DATE", None, None, None
    next_index, entry_date, bar = _next_bar_after(history, signal_date)
    if bar is None or entry_date is None or next_index is None:
        return "NO_FUTURE_PRICE_DATA", None, None, None

    if config.entry_mode == "next_open":
        actual_entry_price = float(bar["open"]) * (1 + config.slippage_pct)
    else:
        zone_low = _float(row.get("entry_zone_low"))
        zone_high = _float(row.get("entry_zone_high"))
        if zone_low is None or zone_high is None:
            return "ENTRY_NOT_TRIGGERED", None, None, None
        touched = float(bar["low"]) <= zone_high and float(bar["high"]) >= zone_low
        if not touched:
            return "ENTRY_NOT_TRIGGERED", None, entry_date, None
        raw_entry = min(max(float(bar["open"]), zone_low), zone_high)
        actual_entry_price = raw_entry * (1 + config.slippage_pct)

    planned_entry = _float(row.get("entry_price"))
    if (
        config.reject_if_entry_gap_too_high
        and planned_entry is not None
        and actual_entry_price > planned_entry * (1 + config.max_entry_gap_pct)
    ):
        return "ENTRY_REJECTED_GAP_TOO_HIGH", None, entry_date, actual_entry_price
    return "ENTRY_TRIGGERED", next_index, entry_date, actual_entry_price


def _exit_trade(
    history: pd.DataFrame,
    entry_index: int,
    actual_entry_price: float,
    row: dict[str, Any] | pd.Series,
    config: InterdayBacktestConfig,
) -> dict[str, Any]:
    stop_loss = float(_float(row.get("stop_loss"), 0.0))
    tp1 = float(_float(row.get("take_profit_1"), 0.0))
    tp2 = float(_float(row.get("take_profit_2"), 0.0))
    time_stop_days = max(1, _int(row.get("time_stop_days"), config.time_stop_days))
    exit_index_limit = min(len(history) - 1, entry_index + time_stop_days - 1)
    window = history.iloc[entry_index : exit_index_limit + 1]

    # Use trailing stop enhancement for improved exit logic
    from .enhancements.trailing_stop import TrailingStopExit
    trailing = TrailingStopExit(enabled=True)

    exit_reason = "TIME_STOP"
    exit_date = window.index[-1]
    exit_price = float(window.iloc[-1]["close"]) * (1 - config.slippage_pct) if not window.empty else actual_entry_price
    exit_position = len(window) - 1
    same_day_ambiguous = False
    highest_price = actual_entry_price
    current_sl = stop_loss

    for offset, (_, bar) in enumerate(window.iterrows()):
        high = float(bar["high"])
        low = float(bar["low"])
        holding_days = offset + 1

        # Update highest for trailing
        highest_price = max(highest_price, high)

        # Trailing stop: tighten SL as profit grows
        current_sl = trailing.compute_trailing_sl(current_sl, actual_entry_price, highest_price)

        # Time-decay TP: reduce TP target progressively
        current_tp1 = trailing.compute_decayed_tp(tp1, actual_entry_price, holding_days)

        tp1_hit = high >= current_tp1
        sl_hit = low <= current_sl

        if tp1_hit and sl_hit:
            same_day_ambiguous = True
            if config.same_day_ambiguous_policy == "stop_first":
                exit_reason = "SL_HIT_SAME_DAY_AMBIGUOUS"
                exit_price = current_sl * (1 - config.slippage_pct)
            elif config.same_day_ambiguous_policy == "tp_first":
                exit_reason = "TP1_HIT_SAME_DAY_AMBIGUOUS"
                exit_price = current_tp1 * (1 - config.slippage_pct)
            else:  # skip_trade
                exit_reason = "AMBIGUOUS_SKIPPED"
                exit_price = float(bar["close"]) * (1 - config.slippage_pct)
            exit_position = offset
            break
        if sl_hit:
            exit_reason = "TRAILING_SL_HIT" if current_sl > stop_loss else "SL_HIT"
            exit_price = current_sl * (1 - config.slippage_pct)
            exit_position = offset
            break
        if tp1_hit:
            exit_reason = "TP1_HIT_DECAYED" if current_tp1 < tp1 else "TP1_HIT"
            exit_price = current_tp1 * (1 - config.slippage_pct)
            exit_position = offset
            break

    exit_window = window.iloc[: exit_position + 1]
    exit_date = exit_window.index[-1]
    max_favorable_price = float(exit_window["high"].max())
    max_adverse_price = float(exit_window["low"].min())
    return {
        "exit_date": exit_date,
        "exit_price": exit_price,
        "exit_reason": exit_reason,
        "holding_days": len(exit_window),
        "mfe_pct": (max_favorable_price - actual_entry_price) / actual_entry_price,
        "mae_pct": (max_adverse_price - actual_entry_price) / actual_entry_price,
        "max_favorable_price": max_favorable_price,
        "max_adverse_price": max_adverse_price,
        "tp1_hit": bool((exit_window["high"] >= tp1).any()),
        "tp2_hit": bool((exit_window["high"] >= tp2).any()),
        "sl_hit": bool((exit_window["low"] <= stop_loss).any()) or bool(exit_window["low"].min() <= current_sl),
        "time_stop_exit": exit_reason == "TIME_STOP",
        "same_day_ambiguous": same_day_ambiguous,
    }


def simulate_interday_signal(
    row: dict[str, Any] | pd.Series,
    price_history: pd.DataFrame,
    config: InterdayBacktestConfig | None = None,
) -> dict[str, Any]:
    config = config or InterdayBacktestConfig()
    result = _base_result(row, config, "SKIPPED_INVALID_STAGE4")
    if not is_stage4_signal_eligible(row):
        return result

    history = _normalize_price_history(price_history)
    if history.empty:
        result["backtest_status"] = "NO_PRICE_DATA"
        return result

    entry_status, entry_index, entry_date, actual_entry_price = _entry_from_signal(row, history, config)
    result["backtest_status"] = entry_status
    result["entry_date"] = entry_date
    result["actual_entry_price"] = actual_entry_price if actual_entry_price is not None else pd.NA
    if entry_status != "ENTRY_TRIGGERED" or entry_index is None or actual_entry_price is None:
        return result

    lots = _int(row.get("executable_position_size_lots", row.get("position_size_lots")))
    shares = lots * config.lot_size
    position_value = shares * actual_entry_price
    exit_result = _exit_trade(history, entry_index, actual_entry_price, row, config)

    # Handle skip_trade policy: ambiguous trades get a special status
    if exit_result["exit_reason"] == "AMBIGUOUS_SKIPPED":
        result.update(exit_result)
        result.update(
            {
                "backtest_status": "AMBIGUOUS_SKIPPED",
                "gross_return_pct": pd.NA,
                "net_return_pct": pd.NA,
                "net_pnl_amount": pd.NA,
                "shares": shares,
                "position_value": position_value,
            }
        )
        return result

    gross_return_pct = (float(exit_result["exit_price"]) - actual_entry_price) / actual_entry_price
    net_return_pct = gross_return_pct - config.buy_fee_pct - config.sell_fee_pct

    result.update(exit_result)
    result.update(
        {
            "backtest_status": "CLOSED_TRADE",
            "gross_return_pct": gross_return_pct,
            "net_return_pct": net_return_pct,
            "net_pnl_amount": position_value * net_return_pct,
            "shares": shares,
            "position_value": position_value,
        }
    )
    return result


def calculate_backtest_metrics(trades: pd.DataFrame, initial_capital: float = 10_000_000) -> dict[str, Any]:
    total_signals = int(len(trades))
    closed = trades[trades["backtest_status"] == "CLOSED_TRADE"].copy() if not trades.empty else pd.DataFrame()
    triggered_count = int(len(closed))
    net_returns = pd.to_numeric(closed.get("net_return_pct", pd.Series(dtype=float)), errors="coerce").dropna()
    pnl = pd.to_numeric(closed.get("net_pnl_amount", pd.Series(dtype=float)), errors="coerce").fillna(0)
    wins = net_returns[net_returns > 0]
    losses = net_returns[net_returns < 0]
    positive_pnl = pnl[pnl > 0].sum()
    negative_pnl = pnl[pnl < 0].sum()
    profit_factor = float(positive_pnl / abs(negative_pnl)) if negative_pnl < 0 else (None if positive_pnl > 0 else 0.0)
    equity_curve = build_equity_curve(closed, initial_capital)
    max_drawdown = float(equity_curve["drawdown_pct"].min()) if not equity_curve.empty else 0.0

    def mean(column: str) -> float | None:
        values = pd.to_numeric(closed.get(column, pd.Series(dtype=float)), errors="coerce").dropna()
        return float(values.mean()) if not values.empty else None

    def median(column: str) -> float | None:
        values = pd.to_numeric(closed.get(column, pd.Series(dtype=float)), errors="coerce").dropna()
        return float(values.median()) if not values.empty else None

    return {
        "total_signals": total_signals,
        "evaluated_trades": int((trades["backtest_status"] != "SKIPPED_INVALID_STAGE4").sum()) if not trades.empty else 0,
        "skipped_invalid_stage4": int((trades["backtest_status"] == "SKIPPED_INVALID_STAGE4").sum()) if not trades.empty else 0,
        "entry_triggered_count": triggered_count,
        "entry_not_triggered_count": int((trades["backtest_status"] == "ENTRY_NOT_TRIGGERED").sum()) if not trades.empty else 0,
        "entry_rejected_gap_count": int((trades["backtest_status"] == "ENTRY_REJECTED_GAP_TOO_HIGH").sum()) if not trades.empty else 0,
        "ambiguous_trade_count": int(trades["same_day_ambiguous"].astype(bool).sum()) if not trades.empty and "same_day_ambiguous" in trades.columns else 0,
        "win_count": int(len(wins)),
        "loss_count": int(len(losses)),
        "win_rate": float(len(wins) / triggered_count) if triggered_count else 0.0,
        "tp1_hit_rate": float(closed["tp1_hit"].astype(bool).mean()) if triggered_count else 0.0,
        "tp2_hit_rate": float(closed["tp2_hit"].astype(bool).mean()) if triggered_count else 0.0,
        "sl_hit_rate": float(closed["sl_hit"].astype(bool).mean()) if triggered_count else 0.0,
        "time_stop_exit_rate": float(closed["time_stop_exit"].astype(bool).mean()) if triggered_count else 0.0,
        "average_return_pct": float(net_returns.mean()) if not net_returns.empty else None,
        "median_return_pct": float(net_returns.median()) if not net_returns.empty else None,
        "average_win_pct": float(wins.mean()) if not wins.empty else None,
        "average_loss_pct": float(losses.mean()) if not losses.empty else None,
        "payoff_ratio": float(wins.mean() / abs(losses.mean())) if not wins.empty and not losses.empty and losses.mean() < 0 else None,
        "profit_factor": profit_factor,
        "expectancy_pct": float(net_returns.mean()) if not net_returns.empty else None,
        "total_net_pnl_amount": float(pnl.sum()) if not pnl.empty else 0.0,
        "max_drawdown_pct": max_drawdown,
        "average_holding_days": mean("holding_days"),
        "median_holding_days": median("holding_days"),
        "average_mfe_pct": mean("mfe_pct"),
        "median_mfe_pct": median("mfe_pct"),
        "average_mae_pct": mean("mae_pct"),
        "median_mae_pct": median("mae_pct"),
        "best_trade_pct": float(net_returns.max()) if not net_returns.empty else None,
        "worst_trade_pct": float(net_returns.min()) if not net_returns.empty else None,
    }


def build_equity_curve(trades: pd.DataFrame, initial_capital: float = 10_000_000) -> pd.DataFrame:
    columns = [
        "date",
        "realized_pnl_amount",
        "cumulative_pnl_amount",
        "equity",
        "drawdown_amount",
        "drawdown_pct",
        "open_trades_count",
        "closed_trades_count",
    ]
    if trades is None or trades.empty:
        return pd.DataFrame(columns=columns)
    closed = trades[trades["backtest_status"] == "CLOSED_TRADE"].copy()
    if closed.empty:
        return pd.DataFrame(columns=columns)
    closed["exit_date"] = pd.to_datetime(closed["exit_date"], errors="coerce")
    closed = closed.dropna(subset=["exit_date"]).sort_values("exit_date")
    grouped = closed.groupby(closed["exit_date"].dt.normalize())["net_pnl_amount"].sum().reset_index()
    grouped = grouped.rename(columns={"exit_date": "date", "net_pnl_amount": "realized_pnl_amount"})
    grouped["cumulative_pnl_amount"] = grouped["realized_pnl_amount"].cumsum()
    grouped["equity"] = initial_capital + grouped["cumulative_pnl_amount"]
    grouped["peak_equity"] = grouped["equity"].cummax()
    grouped["drawdown_amount"] = grouped["equity"] - grouped["peak_equity"]
    grouped["drawdown_pct"] = grouped["drawdown_amount"] / grouped["peak_equity"]
    grouped["open_trades_count"] = 0
    closed_counts = closed.groupby(closed["exit_date"].dt.normalize()).size().reindex(grouped["date"]).fillna(0).astype(int).to_numpy()
    grouped["closed_trades_count"] = closed_counts
    return grouped[columns]


def run_stage5_backtest_interday(
    signals_path: str | Path,
    output_path: str | Path,
    metrics_output_path: str | Path,
    equity_output_path: str | Path,
    config: InterdayBacktestConfig | None = None,
) -> pd.DataFrame:
    config = config or InterdayBacktestConfig()
    signals = pd.read_csv(signals_path)
    histories: dict[str, pd.DataFrame] = {}
    results: list[dict[str, Any]] = []
    for _, row in signals.iterrows():
        yahoo_ticker = str(row.get("yahoo_ticker") or row.get("ticker") or "").strip()
        if yahoo_ticker and yahoo_ticker not in histories:
            histories[yahoo_ticker] = get_price_history(
                yahoo_ticker,
                config.price_cache_dir,
                config.period,
                refresh=config.refresh_price_cache,
                market_data_db=config.market_data_db,
            )
        results.append(simulate_interday_signal(row, histories.get(yahoo_ticker, pd.DataFrame()), config))

    output = pd.DataFrame(results)
    for column in SUPPORT_COLUMNS:
        if column not in output.columns:
            output[column] = pd.NA
    output = output[SUPPORT_COLUMNS]

    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output.to_csv(output_file, index=False)

    metrics = calculate_backtest_metrics(output, config.initial_capital)
    metrics_file = Path(metrics_output_path)
    metrics_file.parent.mkdir(parents=True, exist_ok=True)
    metrics_file.write_text(json.dumps(metrics, indent=2, allow_nan=False, default=str), encoding="utf-8")

    equity_curve = build_equity_curve(output, config.initial_capital)
    equity_file = Path(equity_output_path)
    equity_file.parent.mkdir(parents=True, exist_ok=True)
    equity_curve.to_csv(equity_file, index=False)

    print(f"Stage 5A signals loaded: {len(signals)}")
    print(f"Closed trades: {metrics['entry_triggered_count']}")
    print(f"Win rate: {metrics['win_rate']:.2%}")
    print(f"Trades output saved to: {output_file}")
    print(f"Metrics output saved to: {metrics_file}")
    print(f"Equity output saved to: {equity_file}")

    # P10 Signal Validation: compute statistical quality metrics and append to metrics
    from .enhancements.signal_validation import SignalValidator
    validator = SignalValidator(enabled=True)
    validation = validator.full_validation_report(output)
    metrics["signal_validation"] = validation
    # Re-write metrics with validation included
    metrics_file.write_text(json.dumps(metrics, indent=2, allow_nan=False, default=str), encoding="utf-8")
    if validation["assessment"] != "ROBUST":
        print(f"⚠️  Signal validation: {validation['assessment']} — {validation['recommendation']}")
    else:
        print(f"✅ Signal validation: ROBUST")

    return output
