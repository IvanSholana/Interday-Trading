from __future__ import annotations

import json
import time
from datetime import datetime, date
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .pipeline import PipelineOptions, run_pipeline, build_run_paths

@dataclass
class ScheduledTask:
    name: str
    time_str: str  # "HH:MM"
    strategy_mode: str
    tickers_file: str
    capital: float
    max_position_pct: float
    stages: list[str]
    last_run_date: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ScheduledTask:
        strategy_mode = str(data.get("strategy_mode", "interday"))
        default_max_position_pct = 1.0 if strategy_mode == "bpjs" else 0.2
        return cls(
            name=data["name"],
            time_str=data["time"],
            strategy_mode=strategy_mode,
            tickers_file=data["tickers_file"],
            capital=float(data.get("capital", 500_000)),
            max_position_pct=float(data.get("max_position_pct", default_max_position_pct)),
            stages=data.get("stages", ["stage1", "stage2", "stage3a", "stage3b", "stage4"]),
        )


class PipelineScheduler:
    def __init__(self, config_path: str | Path):
        self.config_path = Path(config_path)
        self.tasks: list[ScheduledTask] = []
        self.load_config()

    def load_config(self) -> None:
        if not self.config_path.exists():
            raise FileNotFoundError(f"Scheduler config not found at: {self.config_path}")
        with open(self.config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.tasks = [ScheduledTask.from_dict(t) for t in data.get("tasks", [])]
        print(f"Loaded {len(self.tasks)} scheduled tasks from {self.config_path}")

    def run_task(self, task: ScheduledTask, run_date_str: str) -> bool:
        print(f"\n=============================================================")
        print(f"TRIGGERING TASK: '{task.name}' at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Strategy: {task.strategy_mode}, Tickers: {task.tickers_file}")
        print(f"Capital: {task.capital}, Stages: {task.stages}")
        print(f"=============================================================")

        tickers_path = Path(task.tickers_file)
        if not tickers_path.is_absolute():
            # Resolve relative to project root
            tickers_path = Path(".").resolve() / tickers_path

        # Build options
        options = PipelineOptions(
            tickers_file=tickers_path,
            run_date=run_date_str,
            strategy_mode=task.strategy_mode,
            capital=task.capital,
            max_position_pct=task.max_position_pct,
            refresh_market_data=True,
            dry_run_llm=True,
            allow_trade_without_broker_data=False,
            require_orderbook_confirmation=True if task.strategy_mode == "bpjs" else None,
        )

        run_id = f"auto_{task.name}_{run_date_str.replace('-', '')}"
        paths = build_run_paths(run_id=run_id)

        try:
            paths, results = run_pipeline(options, stage_names=task.stages, paths=paths, resume=False)
            ok = all(r.ok for r in results)
            print(f"Task '{task.name}' completed. Success: {ok}")
            for r in results:
                print(f"  - {r.name}: {'OK' if r.ok else 'FAIL'}")
            return ok
        except Exception as e:
            print(f"Error executing task '{task.name}': {e}")
            return False

    def check_and_run(self, one_shot: bool = False) -> bool:
        now = datetime.now()
        current_time_str = now.strftime("%H:%M")
        current_date_str = now.date().isoformat()
        
        triggered_any = False
        for task in self.tasks:
            if one_shot:
                success = self.run_task(task, current_date_str)
                if success:
                    task.last_run_date = current_date_str
                triggered_any = True
            else:
                if task.time_str == current_time_str:
                    if task.last_run_date != current_date_str:
                        success = self.run_task(task, current_date_str)
                        if success:
                            task.last_run_date = current_date_str
                        triggered_any = True
        return triggered_any

    def start_loop(self, check_interval_seconds: float = 30.0) -> None:
        print(f"Starting scheduler daemon loop (checking every {check_interval_seconds}s). Press Ctrl+C to exit.")
        try:
            while True:
                self.check_and_run()
                time.sleep(check_interval_seconds)
        except KeyboardInterrupt:
            print("Scheduler daemon stopped by user.")
