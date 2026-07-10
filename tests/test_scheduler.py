import json
from pathlib import Path
from unittest.mock import MagicMock, patch
from datetime import datetime

import pytest

from interday_liquidity_screener.scheduler import ScheduledTask, PipelineScheduler

def test_scheduled_task_from_dict():
    data = {
        "name": "test_task",
        "time": "09:00",
        "strategy_mode": "bpjs",
        "tickers_file": "dummy.txt",
        "capital": 1000000,
        "max_position_pct": 1.0,
        "stages": ["stage1"]
    }
    task = ScheduledTask.from_dict(data)
    assert task.name == "test_task"
    assert task.time_str == "09:00"
    assert task.strategy_mode == "bpjs"
    assert task.tickers_file == "dummy.txt"
    assert task.capital == 1000000.0
    assert task.max_position_pct == 1.0
    assert task.stages == ["stage1"]
    assert task.last_run_date is None

def test_scheduler_load_config(tmp_path):
    config_file = tmp_path / "schedule.json"
    config_data = {
        "tasks": [
            {
                "name": "morning",
                "time": "09:00",
                "tickers_file": "dummy.txt"
            }
        ]
    }
    config_file.write_text(json.dumps(config_data), encoding="utf-8")
    
    sched = PipelineScheduler(config_file)
    assert len(sched.tasks) == 1
    assert sched.tasks[0].name == "morning"
    assert sched.tasks[0].time_str == "09:00"

def test_scheduler_check_and_run_one_shot(tmp_path):
    config_file = tmp_path / "schedule.json"
    config_data = {
        "tasks": [
            {
                "name": "test_task",
                "time": "09:00",
                "tickers_file": "dummy.txt"
            }
        ]
    }
    config_file.write_text(json.dumps(config_data), encoding="utf-8")
    
    sched = PipelineScheduler(config_file)
    
    sched.run_task = MagicMock(return_value=True)
    
    triggered = sched.check_and_run(one_shot=True)
    
    assert triggered is True
    sched.run_task.assert_called_once()
    assert sched.tasks[0].last_run_date is not None

def test_scheduler_check_and_run_daemon_matches_time(tmp_path):
    config_file = tmp_path / "schedule.json"
    config_data = {
        "tasks": [
            {
                "name": "morning",
                "time": "09:00",
                "tickers_file": "dummy.txt"
            }
        ]
    }
    config_file.write_text(json.dumps(config_data), encoding="utf-8")
    
    sched = PipelineScheduler(config_file)
    sched.run_task = MagicMock(return_value=True)
    
    class MockDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 7, 9, 9, 0, 0)
            
    with patch("interday_liquidity_screener.scheduler.datetime", MockDateTime):
        triggered = sched.check_and_run(one_shot=False)
        
    assert triggered is True
    sched.run_task.assert_called_once()
    assert sched.tasks[0].last_run_date == "2026-07-09"

def test_scheduler_check_and_run_prevents_double_trigger(tmp_path):
    config_file = tmp_path / "schedule.json"
    config_data = {
        "tasks": [
            {
                "name": "morning",
                "time": "09:00",
                "tickers_file": "dummy.txt"
            }
        ]
    }
    config_file.write_text(json.dumps(config_data), encoding="utf-8")
    
    sched = PipelineScheduler(config_file)
    sched.run_task = MagicMock(return_value=True)
    
    sched.tasks[0].last_run_date = "2026-07-09"
    
    class MockDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 7, 9, 9, 0, 0)
            
    with patch("interday_liquidity_screener.scheduler.datetime", MockDateTime):
        triggered = sched.check_and_run(one_shot=False)
        
    assert triggered is False
    sched.run_task.assert_not_called()
