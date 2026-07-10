"""Deterministic backtest experiment manifest."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ExperimentManifest:
    start_date: str
    end_date: str
    initial_capital: float
    universe_version: str
    configuration: dict[str, Any]
    config_hash: str
    code_commit_hash: str
    data_version: str
    random_seed: int
    feature_version: str
    strategy_version: str
    artifact_path: str
    metrics: dict[str, Any]

    @classmethod
    def create(
        cls,
        *,
        start_date: str,
        end_date: str,
        initial_capital: float,
        universe_version: str,
        configuration: dict[str, Any],
        code_commit_hash: str = "UNKNOWN",
        data_version: str = "UNKNOWN",
        random_seed: int = 42,
        feature_version: str = "UNKNOWN",
        strategy_version: str = "UNKNOWN",
        artifact_path: str = "",
        metrics: dict[str, Any] | None = None,
    ) -> "ExperimentManifest":
        encoded = json.dumps(configuration, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
        config_hash = hashlib.sha256(encoded).hexdigest()
        return cls(start_date, end_date, initial_capital, universe_version, configuration, config_hash,
                   code_commit_hash, data_version, random_seed, feature_version, strategy_version, artifact_path,
                   dict(metrics or {}))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def write_json(self, path: str | Path) -> Path:
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(self.to_dict(), indent=2, sort_keys=True, default=str), encoding="utf-8")
        return output


__all__ = ["ExperimentManifest"]
