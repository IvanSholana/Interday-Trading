"""ReportWriter — outputs trade ledger and metrics to CSV/report files."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any

import pandas as pd

from interday_liquidity_screener.backtest.metrics import EdgeMetrics, EdgeMetricsResult
from interday_liquidity_screener.backtest.runner import TradeLedger


class ReportWriter:
    """Write backtest results to files."""

    def __init__(self, output_dir: str | Path) -> None:
        self._output_dir = Path(output_dir)
        self._output_dir.mkdir(parents=True, exist_ok=True)

    @property
    def output_dir(self) -> Path:
        return self._output_dir

    def write_trade_ledger(self, ledger: TradeLedger) -> Path:
        """Write trade ledger to CSV."""
        path = self._output_dir / "trade_ledger.csv"
        df = ledger.to_dataframe()
        df.to_csv(path, index=False)
        return path

    def write_aggregate_metrics(self, result: EdgeMetricsResult) -> Path:
        """Write aggregate metrics summary to JSON."""
        path = self._output_dir / "aggregate_metrics.json"
        data = dataclasses.asdict(result)
        path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        return path

    def write_segmented_metrics(
        self, segmented: dict[str, EdgeMetricsResult], segment_name: str
    ) -> Path:
        """Write segmented metrics to CSV."""
        path = self._output_dir / f"segmented_metrics_{segment_name}.csv"
        rows = []
        for segment_value, result in segmented.items():
            row = dataclasses.asdict(result)
            row["segment_key"] = segment_name
            row["segment_value"] = segment_value
            rows.append(row)
        pd.DataFrame(rows).to_csv(path, index=False)
        return path

    def write_full_report(
        self, ledger: TradeLedger, metrics: EdgeMetrics
    ) -> dict[str, Path]:
        """Write complete report: ledger + aggregate + segmented metrics."""
        paths: dict[str, Path] = {}
        paths["ledger"] = self.write_trade_ledger(ledger)

        all_trades = [t for t in ledger.trades if t.exit_event is not None]
        aggregate = metrics.compute(all_trades)
        paths["aggregate"] = self.write_aggregate_metrics(aggregate)

        for segment_key in ["entry_setup", "technical_context", "bandarmology_signal"]:
            segmented = metrics.compute_segmented(all_trades, segment_key)
            paths[f"segmented_{segment_key}"] = self.write_segmented_metrics(
                segmented, segment_key
            )

        return paths


__all__ = ["ReportWriter"]
