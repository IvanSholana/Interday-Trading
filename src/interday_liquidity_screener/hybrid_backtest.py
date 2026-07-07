from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from .backtest.config import CostModelConfig
from .backtest.cost_model import CostModel
from .backtest.simulator import TradeSimulation, TradeSimulator
from .hybrid_screener import HybridScreenerConfig, build_hybrid_watchlist, load_hybrid_config


BACKTEST_MODES = ("normal_execution", "smart_money_first", "hybrid_dual_flow")


@dataclass(frozen=True)
class HybridBacktestConfig:
    modes: tuple[str, ...] = BACKTEST_MODES
    time_stop_days: int = 10
    same_day_ambiguity: str = "worst_case"
    executable_statuses: tuple[str, ...] = ("EXECUTION_READY", "EXECUTION_CANDIDATE", "EXECUTION_DRAFT", "READY_SOON")


def _ticker_key(row: pd.Series) -> str:
    value = row.get("symbol", row.get("ticker", ""))
    return str(value).replace(".JK", "")


def _make_trade(row: pd.Series, date: pd.Timestamp, cost_model: CostModel) -> TradeSimulation | None:
    entry = row.get("entry_price")
    stop = row.get("stop_loss_price")
    tp1 = row.get("tp1_price")
    tp2 = row.get("tp2_price", tp1)
    if pd.isna(entry) or pd.isna(stop) or pd.isna(tp1):
        return None
    entry = float(entry)
    stop = float(stop)
    tp1 = float(tp1)
    tp2 = float(tp2) if not pd.isna(tp2) else tp1
    if entry <= 0 or stop <= 0 or stop >= entry or tp1 <= entry:
        return None
    slipped_entry = cost_model.apply_entry_slippage(entry)
    return TradeSimulation(
        ticker=_ticker_key(row),
        entry_date=date,
        entry_price=slipped_entry,
        raw_entry_price=entry,
        stop_loss=stop,
        take_profit_1=tp1,
        take_profit_2=tp2,
        entry_setup=str(row.get("final_status")),
        technical_context=str(row.get("flow_source")),
        bandarmology_signal=str(row.get("smart_money_score")),
    )


def _summarize_trades(trades: list[TradeSimulation], skipped: pd.DataFrame, screened: pd.DataFrame) -> dict[str, Any]:
    rows = [trade.__dict__ for trade in trades]
    trades_df = pd.DataFrame(rows)
    if trades_df.empty:
        status_distribution = screened["final_status"].value_counts().to_dict() if "final_status" in screened else {}
        return {
            "number_of_trades": 0,
            "tp1_hit_rate": 0.0,
            "tp2_hit_rate": 0.0,
            "stop_loss_rate": 0.0,
            "average_win": 0.0,
            "average_loss": 0.0,
            "expectancy": 0.0,
            "profit_factor": 0.0,
            "max_drawdown": 0.0,
            "average_holding_period": 0.0,
            "net_return_after_fee_slippage": 0.0,
            "gross_return": 0.0,
            "win_rate": 0.0,
            "average_risk_reward": 0.0,
            "skipped_candidates_by_reason": skipped["final_status"].value_counts().to_dict() if "final_status" in skipped else {},
            "status_distribution": status_distribution,
        }
    returns = pd.to_numeric(trades_df["return_net"], errors="coerce").fillna(0)
    gross_returns = pd.to_numeric(trades_df["return_gross"], errors="coerce").fillna(0)
    wins = returns[returns > 0]
    losses = returns[returns < 0]
    equity = (1 + returns).cumprod()
    running_max = equity.cummax()
    drawdown = (equity / running_max - 1).min() if not equity.empty else 0.0
    gross_profit = float(wins.sum())
    gross_loss = float(abs(losses.sum()))
    tp1_hits = (trades_df["exit_event"] == "TP1_HIT").sum()
    sl_hits = (trades_df["exit_event"] == "SL_HIT").sum()
    status_distribution = screened["final_status"].value_counts().to_dict() if "final_status" in screened else {}
    return {
        "number_of_trades": int(len(trades_df)),
        "tp1_hit_rate": float(tp1_hits / len(trades_df)),
        "tp2_hit_rate": 0.0,
        "stop_loss_rate": float(sl_hits / len(trades_df)),
        "average_win": float(wins.mean()) if not wins.empty else 0.0,
        "average_loss": float(losses.mean()) if not losses.empty else 0.0,
        "expectancy": float(returns.mean()),
        "profit_factor": gross_profit / gross_loss if gross_loss > 0 else (float("inf") if gross_profit > 0 else 0.0),
        "max_drawdown": float(drawdown),
        "average_holding_period": float(pd.to_numeric(trades_df["holding_days"], errors="coerce").mean()),
        "net_return_after_fee_slippage": float(returns.sum()),
        "gross_return": float(gross_returns.sum()),
        "win_rate": float(len(wins) / len(trades_df)),
        "average_risk_reward": float(pd.to_numeric(trades_df["r_multiple"], errors="coerce").mean()),
        "skipped_candidates_by_reason": skipped["final_status"].value_counts().to_dict() if "final_status" in skipped else {},
        "status_distribution": status_distribution,
    }


def compare_hybrid_modes(
    candidates: pd.DataFrame,
    price_data: dict[str, pd.DataFrame],
    screener_config: HybridScreenerConfig | None = None,
    backtest_config: HybridBacktestConfig | None = None,
    capital_profile: str = "capital_1m",
) -> pd.DataFrame:
    screener_config = screener_config or HybridScreenerConfig()
    backtest_config = backtest_config or HybridBacktestConfig()
    if backtest_config.same_day_ambiguity != "worst_case":
        raise ValueError("Only worst_case same-day ambiguity is implemented.")
    cost_model = CostModel(CostModelConfig())
    simulator = TradeSimulator(cost_model, time_stop_days=backtest_config.time_stop_days)
    summaries: list[dict[str, Any]] = []
    for mode in backtest_config.modes:
        screened = build_hybrid_watchlist(
            candidates,
            mode=mode,
            capital_profile=capital_profile,
            config=screener_config,
            max_candidates=0,
        )
        executable = screened[screened["final_status"].isin(backtest_config.executable_statuses)].copy()
        skipped = screened[~screened.index.isin(executable.index)].copy()
        trades: list[TradeSimulation] = []
        for _, row in executable.iterrows():
            ticker = _ticker_key(row)
            bars = price_data.get(ticker)
            if bars is None or bars.empty:
                continue
            decision_date = pd.Timestamp(row.get("date")) if pd.notna(row.get("date")) else pd.Timestamp(bars.index[0])
            trade = _make_trade(row, decision_date, cost_model)
            if trade is None:
                continue
            future_bars = bars[bars.index > decision_date]
            simulator.simulate(trade, future_bars)
            trades.append(trade)
        summary = _summarize_trades(trades, skipped, screened)
        summary["mode"] = mode
        summaries.append(summary)
    return pd.DataFrame(summaries)


def walk_forward_compare(
    candidates_by_period: list[tuple[str, str, pd.DataFrame, dict[str, pd.DataFrame]]],
    config_path: str | None = None,
    capital_profile: str = "capital_1m",
) -> pd.DataFrame:
    screener_config = load_hybrid_config(config_path)
    rows: list[pd.DataFrame] = []
    for train_period, test_period, candidates, price_data in candidates_by_period:
        result = compare_hybrid_modes(candidates, price_data, screener_config=screener_config, capital_profile=capital_profile)
        result["train_period"] = train_period
        result["test_period"] = test_period
        rows.append(result)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()

