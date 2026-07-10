"""Stable experiment artifact serialization."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from .audit_record import SignalTradeAuditRecord
from .manifest import ExperimentManifest


class ExperimentArtifactWriter:
    def __init__(self, output_dir: str | Path) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def write(self, *, manifest: ExperimentManifest, audit_records: list[SignalTradeAuditRecord],
              equity_curve: pd.DataFrame, closed_trades: list[dict]) -> dict[str, Path]:
        paths = {
            "manifest": self.output_dir / "experiment_manifest.json",
            "audit": self.output_dir / "signal_trade_audit.jsonl",
            "equity": self.output_dir / "equity_curve.csv",
            "closed_trades": self.output_dir / "closed_trades.csv",
        }
        manifest.write_json(paths["manifest"])
        audit_lines = [json.dumps(record.to_dict(), sort_keys=True, default=str) for record in audit_records]
        paths["audit"].write_text("\n".join(audit_lines) + ("\n" if audit_lines else ""), encoding="utf-8")
        equity_curve.to_csv(paths["equity"], index=False)
        pd.DataFrame(closed_trades).to_csv(paths["closed_trades"], index=False)
        return paths


__all__ = ["ExperimentArtifactWriter"]
