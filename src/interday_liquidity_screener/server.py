from __future__ import annotations

import asyncio
from dataclasses import asdict
from datetime import date, datetime
import io
import json
import math
import os
from pathlib import Path
import sys
import threading
import traceback
import webbrowser
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, BackgroundTasks, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
import pandas as pd

# Handle sys.path setups
try:
    from .pipeline import (
        DEFAULT_RUN_ROOT,
        DEFAULT_MARKET_DATA_DB,
        DEFAULT_INPUT_ROOT,
        apply_runtime_api_keys,
        build_run_paths,
        create_run_id,
        discover_run_dirs,
        resolve_artifact_path,
        summarize_run,
        token_available,
        PipelineOptions,
        run_pipeline,
    )
    from .recommendation import build_recommendation_pack
    from .run_audit import build_run_audit_report
    from .ticker_universe import UNIVERSE_PRESETS, read_universe_text
    from .tickers import load_tickers, normalize_ticker
except ImportError:
    package_root = Path(__file__).resolve().parents[1]
    if str(package_root) not in sys.path:
        sys.path.insert(0, str(package_root))
    from interday_liquidity_screener.pipeline import (
        DEFAULT_RUN_ROOT,
        DEFAULT_MARKET_DATA_DB,
        DEFAULT_INPUT_ROOT,
        apply_runtime_api_keys,
        build_run_paths,
        create_run_id,
        discover_run_dirs,
        resolve_artifact_path,
        summarize_run,
        token_available,
        PipelineOptions,
        run_pipeline,
    )
    from interday_liquidity_screener.recommendation import build_recommendation_pack
    from interday_liquidity_screener.run_audit import build_run_audit_report
    from interday_liquidity_screener.ticker_universe import UNIVERSE_PRESETS
    from interday_liquidity_screener.tickers import load_tickers, normalize_ticker

app = FastAPI(title="IDX Interday Trading API", version="1.0.0")

# Enable CORS for development (Vite dev server)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global state for current running pipeline
class PipelineState:
    def __init__(self):
        self.lock = threading.Lock()
        self.status = "idle"  # idle, running, success, failed, cancelled
        self.run_id = ""
        self.current_stage = ""
        self.progress = 0.0  # 0.0 to 100.0
        self.logs: List[str] = []
        self.error_message: Optional[str] = None
        self.original_stdout = sys.stdout
        self.cancel_event = threading.Event()

pipeline_state = PipelineState()

class LiveLogCapture:
    def __init__(self, original_stdout, on_log):
        self.original_stdout = original_stdout
        self.on_log = on_log

    def write(self, s):
        self.original_stdout.write(s)
        self.original_stdout.flush()
        if s.strip():
            self.on_log(s.strip())

    def flush(self):
        self.original_stdout.flush()

def append_state_log(msg: str):
    with pipeline_state.lock:
        timestamp = datetime.now().strftime("%H:%M:%S")
        pipeline_state.logs.append(f"[{timestamp}] {msg}")

# Background worker for pipeline
def run_pipeline_thread(
    options: PipelineOptions,
    stages: List[str],
    run_paths: Any,
    resume: bool = False,
    auto_start_monitor: bool = True,
    monitor_interval_seconds: float = 300.0,
):
    global pipeline_state
    
    with pipeline_state.lock:
        pipeline_state.status = "running"
        pipeline_state.progress = 0.0
        pipeline_state.current_stage = "Stage 1 - Liquidity"
        pipeline_state.logs = []
        pipeline_state.error_message = None
    
    append_state_log(f"Starting pipeline run. Run ID: {run_paths.run_id}{' (Resuming from failure)' if resume else ''}")
    append_state_log(f"Target Date: {options.run_date}, Strategy: {options.strategy_mode}")
    append_state_log(f"Selected Stages: {', '.join(stages)}")
    
    original_stdout = sys.stdout
    capturer = LiveLogCapture(original_stdout, append_state_log)
    sys.stdout = capturer
    
    STAGE_DISPLAY_NAMES = {
        "stage1": "Stage 1 - Liquidity",
        "stage2": "Stage 2 - Technical",
        "stage3a": "Stage 3A - Stockbit Broker",
        "stage3b": "Stage 3B - Bandarmology",
        "stage3c": "Stage 3C - Orderbook",
        "stage4": "Stage 4 - Trade Plan",
        "hybrid": "Stage Hybrid",
        "stage5": "Stage 5 - Backtest",
        "stage6": "Stage 6 - AI Report"
    }
    
    try:
        # Import stage runner functions
        from interday_liquidity_screener.pipeline import (
            capture_stage,
            run_stage1_screening,
            run_stage_2_technical_screening,
            run_stage3a_broker_collector_multi_window,
            run_stage3b_bandarmology_scoring,
            run_stage3c_orderbook_filter,
            run_stage_4_trade_plan,
            run_hybrid_screener,
            run_stage5_backtest_interday,
            run_stage5_paper_bpjs,
            run_stage6_build_evidence,
            run_llm_report,
            _last_failed,
            StockbitCollectorConfig,
            parse_windows_arg,
            OrderbookFilterConfig,
            TradePlanConfig,
            InterdayBacktestConfig,
            BpjsPaperConfig,
        )
        
        results = []
        paths = run_paths
        total_stages = len(stages)
        
        for idx, stage in enumerate(stages):
            # Check for cancellation before starting each stage
            if pipeline_state.cancel_event.is_set():
                append_state_log("Pipeline dibatalkan oleh user.")
                with pipeline_state.lock:
                    pipeline_state.status = "cancelled"
                    pipeline_state.current_stage = "Dibatalkan"
                sys.stdout = original_stdout
                return
            display_name = STAGE_DISPLAY_NAMES.get(stage, stage)
            with pipeline_state.lock:
                pipeline_state.current_stage = display_name
                pipeline_state.progress = round((idx / total_stages) * 100, 1)
                
            append_state_log(f"--- Running stage: {display_name} ({idx+1}/{total_stages}) ---")
            
            if stage == "stage1":
                results.append(capture_stage("Stage 1 - Liquidity", paths.stage1, lambda: run_stage1_screening(options.tickers_file, paths.stage1, options), resume=resume))
            elif stage == "stage2":
                results.append(
                    capture_stage(
                        "Stage 2 - Technical",
                        paths.stage2,
                        lambda: run_stage_2_technical_screening(
                            paths.stage1,
                            paths.stage2,
                            period=options.period_stage2,
                            market_data_db=options.market_data_db,
                            refresh_market_data=options.refresh_market_data,
                        ),
                        resume=resume,
                    )
                )
            elif stage == "stage3a":
                config = StockbitCollectorConfig(sleep_seconds=options.stockbit_sleep_seconds)
                results.append(
                    capture_stage(
                        "Stage 3A - Stockbit Broker",
                        paths.stage3a_broker,
                        lambda: run_stage3a_broker_collector_multi_window(
                            paths.stage2,
                            paths.stage3a_dir,
                            paths.raw_stockbit,
                            options.run_date,
                            parse_windows_arg(options.windows),
                            config,
                        ),
                        resume=resume,
                    )
                )
            elif stage == "stage3b":
                results.append(
                    capture_stage(
                        "Stage 3B - Bandarmology",
                        paths.stage3b,
                        lambda: run_stage3b_bandarmology_scoring(paths.stage2, paths.stage3a_detector, paths.stage3a_broker, paths.stage3b),
                        resume=resume,
                    )
                )
            elif stage == "stage3c":
                config = OrderbookFilterConfig(sleep_seconds=options.orderbook_sleep_seconds)
                results.append(
                    capture_stage(
                        "Stage 3C - Orderbook",
                        paths.stage3c,
                        lambda: run_stage3c_orderbook_filter(paths.stage2, paths.stage3b, paths.stage3c, paths.raw_orderbook, config),
                        resume=resume,
                    )
                )
            elif stage == "stage4":
                config = TradePlanConfig(
                    strategy_mode=options.strategy_mode,
                    capital=options.capital,
                    risk_per_trade_pct=options.risk_per_trade_pct,
                    max_position_pct=options.max_position_pct,
                    bandarmology_min_score=options.bandarmology_min_score,
                    allow_trade_without_broker_data=options.allow_trade_without_broker_data,
                    require_orderbook_confirmation=options.require_orderbook_confirmation,
                    strict_corporate_action_filter=options.strict_corporate_action_filter,
                )
                results.append(
                    capture_stage(
                        "Stage 4 - Trade Plan",
                        paths.stage4,
                        lambda: run_stage_4_trade_plan(paths.stage2, paths.stage3b, paths.stage4, config=config, orderbook_path=paths.stage3c),
                        resume=resume,
                    )
                )
            elif stage == "hybrid":
                broker_path = paths.stage3b if paths.stage3b.exists() else None
                orderbook_path = paths.stage3c if paths.stage3c.exists() else None
                results.append(
                    capture_stage(
                        "Stage Hybrid - Dual Flow Watchlist",
                        paths.hybrid_watchlist,
                        lambda: run_hybrid_screener(
                            input_path=paths.stage2,
                            output_path=paths.hybrid_watchlist,
                            mode=options.hybrid_mode,
                            capital_profile=options.hybrid_capital_profile,
                            config_path=options.hybrid_config_path,
                            broker_flow_path=broker_path,
                            orderbook_path=orderbook_path,
                            date=options.run_date,
                            max_candidates=options.hybrid_max_candidates,
                            enable_market_regime=options.enable_market_regime,
                            enable_multibar_confirm=options.enable_multibar_confirm,
                            enable_adaptive_tp=options.enable_adaptive_tp,
                            enable_liquidity_sizer=options.enable_liquidity_sizer,
                            enable_blackout=options.enable_blackout,
                        ),
                        resume=resume,
                    )
                )
            elif stage == "stage5":
                backtest_config = InterdayBacktestConfig(
                    period=options.period_stage2,
                    initial_capital=options.capital,
                    market_data_db=options.market_data_db,
                    refresh_price_cache=options.refresh_market_data,
                )
                results.append(
                    capture_stage(
                        "Stage 5A - Interday Backtest",
                        paths.stage5_trades,
                        lambda: run_stage5_backtest_interday(
                            paths.stage4,
                            paths.stage5_trades,
                            paths.stage5_metrics,
                            paths.stage5_equity,
                            backtest_config,
                        ),
                        resume=resume,
                    )
                )
                bpjs_config = BpjsPaperConfig(date=options.run_date)
                results.append(
                    capture_stage(
                        "Stage 5B - BPJS Paper",
                        paths.stage5_bpjs_paper,
                        lambda: run_stage5_paper_bpjs(
                            paths.stage4,
                            paths.stage3c if paths.stage3c.exists() else None,
                            paths.stage5_bpjs_paper,
                            bpjs_config,
                            summary_output_path=paths.stage5_bpjs_summary,
                        ),
                        resume=resume,
                    )
                )
            elif stage == "stage6":
                results.append(
                    capture_stage(
                        "Stage 6A - Evidence",
                        paths.stage6_evidence,
                        lambda: run_stage6_build_evidence(
                            paths.stage2,
                            paths.stage3b if paths.stage3b.exists() else None,
                            paths.stage3c if paths.stage3c.exists() else None,
                            paths.stage4,
                            paths.stage5_metrics if paths.stage5_metrics.exists() else None,
                            paths.stage5_bpjs_summary if paths.stage5_bpjs_summary.exists() else None,
                            paths.stage6_evidence,
                            options.strategy_mode,
                            options.run_date,
                            options.hybrid_max_candidates or 30,
                        ),
                        resume=resume,
                    )
                )
                if not _last_failed(results):
                    results.append(
                        capture_stage(
                            "Stage 6B - Report",
                            paths.stage6_report,
                            lambda: run_llm_report(
                                paths.stage6_evidence,
                                paths.stage6_report,
                                paths.stage6_ranking,
                                paths.stage6_watchlist,
                                paths.stage6_raw,
                                options.strategy_mode,
                                dry_run=options.dry_run_llm,
                            ),
                            resume=resume,
                        )
                    )
            
            # Check results of current stage
            if _last_failed(results):
                break
                
        sys.stdout = original_stdout
        
        # Final result check
        failed_stage = None
        for res in results:
            if not res.ok:
                failed_stage = res
                break
                
        if failed_stage:
            with pipeline_state.lock:
                pipeline_state.status = "failed"
                pipeline_state.error_message = f"Failed in {failed_stage.name}: {failed_stage.error}"
            append_state_log(f"Pipeline Execution Failed: {failed_stage.name}. Error: {failed_stage.error}")
        else:
            with pipeline_state.lock:
                pipeline_state.status = "success"
                pipeline_state.progress = 100.0
                pipeline_state.current_stage = "Completed"
            append_state_log("Pipeline Execution Completed Successfully.")
            if auto_start_monitor:
                monitor_path = paths.hybrid_watchlist if paths.hybrid_watchlist.exists() else paths.stage4
                if monitor_path.exists():
                    started = _start_live_monitor(
                        str(monitor_path),
                        max(30.0, float(monitor_interval_seconds)),
                        bypass_market_hours=False,
                        replace_running=True,
                    )
                    if started:
                        append_state_log(f"Telegram live monitor auto-started: {monitor_path}")
                    else:
                        append_state_log("Telegram live monitor auto-start skipped: Telegram/Stockbit credentials are incomplete.")
                else:
                    append_state_log("Telegram live monitor auto-start skipped: no watchlist artifact found.")
            
    except Exception as e:
        sys.stdout = original_stdout
        error_trace = traceback.format_exc()
        with pipeline_state.lock:
            pipeline_state.status = "failed"
            pipeline_state.error_message = str(e)
        append_state_log(f"Exception during pipeline run: {e}")
        append_state_log(error_trace)

# Pydantic models
class RunRequest(BaseModel):
    tickers: str  # text box input
    universe_key: str  # manual, all_idx, etc.
    run_date: str
    strategy_mode: str
    stages: List[str]
    capital: float
    risk_per_trade_pct: float
    max_position_pct: float
    bandarmology_min_score: int
    dry_run_llm: bool
    refresh_market_data: bool
    allow_trade_without_broker_data: bool
    require_orderbook_confirmation: Optional[bool] = None
    strict_corporate_action_filter: bool
    hybrid_mode: str
    hybrid_capital_profile: str
    enable_market_regime: Optional[bool] = None
    enable_multibar_confirm: Optional[bool] = None
    enable_adaptive_tp: Optional[bool] = None
    enable_liquidity_sizer: Optional[bool] = None
    enable_blackout: Optional[bool] = None
    auto_start_monitor: bool = True
    monitor_interval_seconds: float = 300.0
    resume_run_id: Optional[str] = None

class SettingsUpdate(BaseModel):
    stockbit_token: str
    deepseek_api_key: str

@app.get("/api/presets")
def get_presets():
    """List all available ticker universe presets.

    Returns a list of preset objects, each with:
    - ``key``: machine-readable identifier (e.g. ``"lq45"``).
    - ``label``: human-readable name shown in the UI dropdown.
    - ``description``: short description.
    - ``ticker_count``: number of tickers in the preset file (0 if file missing).
    """
    from .ticker_universe import load_universe_tickers
    presets_data = []
    for p in UNIVERSE_PRESETS:
        ticker_count = 0
        if p.key != "manual":
            try:
                tickers = load_universe_tickers(p.key)
                ticker_count = len(tickers)
            except Exception:
                pass
        presets_data.append({
            "key": p.key,
            "label": p.label,
            "filename": p.filename,
            "description": p.description,
            "ticker_count": ticker_count
        })
    return presets_data

@app.get("/api/presets/{key}")
def get_preset_tickers(key: str):
    """Return the ticker list for a specific universe preset.

    Args:
        key: Preset key, e.g. ``"lq45"``, ``"idx80"``, ``"syariah"``.
             Pass ``"manual"`` to get an empty list (user-defined tickers).

    Returns:
        ``{"tickers": ["BBCA.JK", "TLKM.JK", ...]}``. Empty list if the
        preset file does not exist on disk.

    Raises:
        404: If the preset key is not found in ``UNIVERSE_PRESETS``.
    """
    if key == "manual":
        return {"tickers": []}
    preset = [p for p in UNIVERSE_PRESETS if p.key == key]
    if not preset:
        raise HTTPException(status_code=404, detail="Preset not found")
    from .ticker_universe import load_universe_tickers
    tickers = load_universe_tickers(key)
    return {"tickers": tickers}

@app.get("/api/settings")
def get_settings():
    """Return current API token configuration status.

    Reads environment variables ``STOCKBIT_TOKEN`` and ``DEEPSEEK_API_KEY``
    (from process env or ``.env`` file) and reports whether each is set.
    Never returns the full token — only a masked preview (last 4 chars).

    Returns:
        ``SettingsState``-compatible dict with keys:
        ``stockbit_configured``, ``stockbit_token_preview``,
        ``deepseek_configured``, ``deepseek_key_preview``,
        ``run_root``, ``market_db``.
    """
    stockbit_env = token_available("STOCKBIT_TOKEN")
    deepseek_env = token_available("DEEPSEEK_API_KEY")
    
    stockbit_val = os.environ.get("STOCKBIT_TOKEN", "")
    deepseek_val = os.environ.get("DEEPSEEK_API_KEY", "")
    
    return {
        "stockbit_configured": bool(stockbit_val or stockbit_env),
        "stockbit_token_preview": f"...{stockbit_val[-4:]}" if len(stockbit_val) > 4 else "Not configured",
        "deepseek_configured": bool(deepseek_val or deepseek_env),
        "deepseek_key_preview": f"...{deepseek_val[-4:]}" if len(deepseek_val) > 4 else "Not configured",
        "run_root": str(DEFAULT_RUN_ROOT),
        "market_db": str(DEFAULT_MARKET_DATA_DB)
    }

@app.post("/api/settings")
def update_settings(payload: SettingsUpdate):
    """Persist API tokens to the local ``.env`` file and activate them.

    Tokens are written to ``.env`` in the working directory and immediately
    applied to ``os.environ`` for the current process via
    ``apply_runtime_api_keys``.

    Args:
        payload: ``SettingsUpdate`` with ``stockbit_token`` (full Bearer string
                 or raw token) and ``deepseek_api_key``.

    Returns:
        ``{"message": "Settings updated and saved to local .env file."}``
    """
    apply_runtime_api_keys(payload.stockbit_token, payload.deepseek_api_key)
    
    env_path = Path(".env")
    env_content = {}
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                env_content[k.strip()] = v.strip()
                
    if payload.stockbit_token:
        token = payload.stockbit_token.strip()
        if token.lower().startswith("bearer "):
            token = token[7:].strip()
        env_content["STOCKBIT_TOKEN"] = f'"{token}"'
    if payload.deepseek_api_key:
        env_content["DEEPSEEK_API_KEY"] = f'"{payload.deepseek_api_key.strip()}"'
        
    lines = []
    for k, v in env_content.items():
        lines.append(f"{k}={v}")
    
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"message": "Settings updated and saved to local .env file."}

@app.get("/api/runs")
def get_runs():
    """List all completed and in-progress pipeline runs.

    Scans ``DEFAULT_RUN_ROOT`` (``data/output/ui_runs/``) for run directories
    named ``YYYYMMDD_HHMMSS`` and returns a summary for each.

    Returns:
        List of ``RunSummary``-compatible dicts ordered newest-first, each with:
        ``run``, ``formatted_date``, ``stage1_rows``, ``liquid_rows``,
        ``valid_trade_plans``, ``closed_trades``, ``win_rate``,
        ``report_available``. On per-run read errors, ``error`` is included.

    Raises:
        500: If the runs root directory cannot be scanned at all.
    """
    try:
        run_dirs = discover_run_dirs(DEFAULT_RUN_ROOT)
        summaries = []
        for d in run_dirs:
            try:
                info = summarize_run(d)
                try:
                    dt = datetime.strptime(d.name, "%Y%m%d_%H%M%S")
                    formatted_date = dt.strftime("%Y-%m-%d %H:%M:%S")
                except ValueError:
                    formatted_date = "Unknown date"
                info["formatted_date"] = formatted_date
                summaries.append(info)
            except Exception as e:
                summaries.append({
                    "run": d.name,
                    "error": str(e),
                    "formatted_date": "Error reading"
                })
        return summaries
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to scan runs: {e}")

@app.get("/api/run-details/{run_id}")
def get_run_details(run_id: str):
    """Return stage availability and summary metrics for a specific run.

    Args:
        run_id: Run directory name, e.g. ``"20260708_091500"``.

    Returns:
        Dict with:
        - ``run_id``: echo of the requested ID.
        - ``summary``: same shape as ``RunSummary``.
        - ``stages``: mapping of stage key → bool (True if output file exists).

    Raises:
        404: If the run directory does not exist.
    """
    run_dir = DEFAULT_RUN_ROOT / run_id
    if not run_dir.exists():
        raise HTTPException(status_code=404, detail="Run not found")
        
    available_stages = {}
    from .pipeline import STAGE_FILES
    for stage, filename in STAGE_FILES.items():
        if stage.startswith("stage3a_"):
            p = run_dir / "stockbit" / filename
        else:
            p = run_dir / filename
        available_stages[stage] = p.exists()
        
    summary = summarize_run(run_dir)
    return {
        "run_id": run_id,
        "summary": summary,
        "stages": available_stages
    }

@app.get("/api/run-csv/{run_id}/{stage}")
def get_run_csv(
    run_id: str,
    stage: str,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100000),
    search: str = Query("", description="Global search pattern"),
    sort_by: Optional[str] = None,
    sort_order: str = Query("asc", pattern="^(asc|desc)$"),
    trade_status: Optional[str] = None,
    liquidity_bucket: Optional[str] = None,
    bandarmology_signal: Optional[str] = None,
):
    """Return paginated, filtered, and sorted rows from a stage output CSV.

    Used by the Results Explorer tab to load and display pipeline output data.
    Supports server-side pagination, global text search, column sort, and
    filtering by ``trade_status``, ``liquidity_bucket``, and
    ``bandarmology_signal`` (only applied if the column exists in the CSV).

    Args:
        run_id: Run directory name (e.g. ``"20260708_091500"``).
        stage: Stage key (e.g. ``"stage1"``, ``"hybrid_watchlist"``, ``"stage4"``).
        page: 1-based page number.
        limit: Rows per page (1–100000).
        search: Case-insensitive substring match across all columns.
        sort_by: Column name to sort by.
        sort_order: ``"asc"`` or ``"desc"``.
        trade_status: Filter by ``trade_status`` column value.
        liquidity_bucket: Filter by ``liquidity_bucket`` column value.
        bandarmology_signal: Filter by ``bandarmology_signal`` column value.

    Returns:
        Dict with ``records`` (list of row dicts), ``total`` (pre-pagination
        count after filtering), ``page``, and ``limit``.

    Raises:
        404: If run directory or stage output file does not exist.
        500: If the CSV file cannot be parsed.
    """
    run_dir = DEFAULT_RUN_ROOT / run_id
    if not run_dir.exists():
        raise HTTPException(status_code=404, detail="Run not found")
        
    path = resolve_artifact_path(run_dir, stage)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Data for stage '{stage}' does not exist.")
        
    try:
        df = pd.read_csv(path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading file: {e}")
        
    df = df.fillna("")
    
    if search:
        mask = df.astype(str).apply(lambda x: x.str.contains(search, case=False, regex=False)).any(axis=1)
        df = df[mask]
        
    if trade_status and "trade_status" in df.columns:
        df = df[df["trade_status"] == trade_status]
        
    if liquidity_bucket and "liquidity_bucket" in df.columns:
        df = df[df["liquidity_bucket"] == liquidity_bucket]
        
    if bandarmology_signal and "bandarmology_signal" in df.columns:
        df = df[df["bandarmology_signal"] == bandarmology_signal]
        
    total_records = len(df)
    
    if sort_by and sort_by in df.columns:
        if pd.api.types.is_numeric_dtype(df[sort_by]):
            df = df.sort_values(by=sort_by, ascending=(sort_order == "asc"))
        else:
            # Mixed or string column - check if it behaves mostly as numeric
            non_empty = df[df[sort_by] != ""]
            is_mostly_numeric = False
            if len(non_empty) > 0:
                converted = pd.to_numeric(non_empty[sort_by], errors='coerce')
                is_mostly_numeric = converted.notna().sum() > (len(non_empty) * 0.5)
                
            if is_mostly_numeric:
                df["_sort_tmp"] = pd.to_numeric(df[sort_by], errors='coerce')
                df = df.sort_values(by="_sort_tmp", ascending=(sort_order == "asc"), na_position='last')
                df = df.drop(columns=["_sort_tmp"])
            else:
                # String / Lexicographical sort
                df = df.sort_values(by=sort_by, ascending=(sort_order == "asc"))
            
    start = (page - 1) * limit
    end = start + limit
    paginated_df = df.iloc[start:end]
    records = paginated_df.to_dict(orient="records")
    
    return {
        "records": records,
        "total": total_records,
        "page": page,
        "limit": limit
    }

@app.get("/api/report/{run_id}")
def get_run_report(run_id: str):
    """Return the Stage 6 LLM-generated AI report for a run.

    Args:
        run_id: Run directory name (e.g. ``"20260708_091500"``).

    Returns:
        ``{"report": "<markdown string>"}`` containing the full report text.

    Raises:
        404: If the run directory or report file does not exist.
        500: If the report file cannot be read.
    """
    run_dir = DEFAULT_RUN_ROOT / run_id
    if not run_dir.exists():
        raise HTTPException(status_code=404, detail="Run not found")
        
    path = resolve_artifact_path(run_dir, "stage6_report")
    if not path.exists():
        raise HTTPException(status_code=404, detail="Report not generated for this run")
        
    try:
        content = path.read_text(encoding="utf-8")
        return {"report": content}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading report: {e}")

@app.get("/api/recommendation/{run_id}")
def get_run_recommendation(
    run_id: str,
    capital: float = Query(1_000_000.0, gt=0),
    max_tp_pct: float = Query(0.05, gt=0, le=1),
    max_position_pct: float = Query(1.0, gt=0, le=1),
    limit: int = Query(5, ge=1, le=20),
):
    """Return capital-aware trade recommendation data for a completed run.

    This endpoint reads the hybrid watchlist and derives a professional
    decision-support pack: primary candidate, shortlist, lot sizing, TP/SL
    percentages, estimated gross profit/loss, status readiness, and next
    action. It does not create new signals or mutate run artifacts.

    Args:
        run_id: Run directory name (e.g. ``"20260708_091500"``).
        capital: Available capital in IDR for sizing context.
        max_tp_pct: Maximum TP percentage allowed by the user's plan.
        max_position_pct: Maximum capital allocation for a single candidate.
        limit: Maximum shortlist rows returned.

    Raises:
        404: If the run directory or hybrid watchlist file does not exist.
        500: If the watchlist CSV cannot be parsed.
    """
    run_dir = DEFAULT_RUN_ROOT / run_id
    if not run_dir.exists():
        raise HTTPException(status_code=404, detail="Run not found")

    path = resolve_artifact_path(run_dir, "hybrid_watchlist")
    if not path.exists():
        raise HTTPException(status_code=404, detail="Hybrid watchlist not generated for this run")

    try:
        df = pd.read_csv(path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading watchlist: {e}")

    pack = build_recommendation_pack(
        df,
        run_id=run_id,
        capital=capital,
        max_tp_pct=max_tp_pct,
        max_position_pct=max_position_pct,
        limit=limit,
    )
    return pack.to_dict()

@app.get("/api/run-audit/{run_id}")
def get_run_audit(
    run_id: str,
    capital: float = Query(1_000_000.0, gt=0),
    max_tp_pct: float = Query(0.05, gt=0, le=1),
    max_position_pct: float = Query(1.0, gt=0, le=1),
):
    """Return artifact health and decision-readiness audit for a run.

    The audit combines stage artifact existence/row checks, run summary, and
    the capital-aware recommendation pack. It is read-only and never mutates
    pipeline artifacts.
    """
    run_dir = DEFAULT_RUN_ROOT / run_id
    report = build_run_audit_report(
        run_dir,
        resolve_artifact_path=resolve_artifact_path,
        summarize_run=summarize_run,
        capital=capital,
        max_tp_pct=max_tp_pct,
        max_position_pct=max_position_pct,
    )
    if report.overall_status == "MISSING_RUN":
        raise HTTPException(status_code=404, detail="Run not found")
    return report.to_dict()

class BandarScanRequest(BaseModel):
    config_path: str = "config/bandar_tracker.json"
    output_path: str = "data/output/bandar_scan_results.csv"
    force_refresh: bool = False
    investor_type: Optional[str] = None
    period: Optional[str] = None

class LiveMonitorStartRequest(BaseModel):
    watchlist_path: str = ""
    interval_seconds: float = 300.0
    bypass_market_hours: bool = False

def make_json_safe(value: Any) -> Any:
    """Return a JSON-compatible value, replacing NaN/Infinity with null."""
    if value is None:
        return None
    if isinstance(value, float) and not math.isfinite(value):
        return None
    try:
        if not isinstance(value, (dict, list, tuple, set)) and pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, dict):
        return {str(key): make_json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [make_json_safe(item) for item in value]
    if isinstance(value, (pd.Timestamp, datetime, date)):
        return value.isoformat()
    return value

def to_json_safe_records(df: pd.DataFrame) -> list[dict[str, Any]]:
    """Convert a DataFrame to JSON-safe records for FastAPI responses."""
    return make_json_safe(df.to_dict(orient="records"))

class LiveMonitorRuntime:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.thread: threading.Thread | None = None
        self.stop_event = threading.Event()
        self.running = False
        self.watchlist_path = ""
        self.interval_seconds = 300.0
        self.bypass_market_hours = False
        self.started_at: str | None = None
        self.last_scan_at: str | None = None
        self.last_error: str | None = None
        self.last_result_count = 0
        self.logs: list[str] = []

    def append_log(self, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        with self.lock:
            self.logs.append(f"[{timestamp}] {message}")
            self.logs = self.logs[-100:]

live_monitor_state = LiveMonitorRuntime()

def _latest_monitor_watchlist_path() -> str:
    candidates = list(Path("data/output/ui_runs").glob("*/hybrid_watchlist.csv"))
    candidates += list(Path("data/output").glob("*watchlist*.csv"))
    existing = [path for path in candidates if path.exists()]
    if not existing:
        return "data/output/stage4_today.csv"
    return str(max(existing, key=lambda path: path.stat().st_mtime))

def _read_live_monitor_results() -> list[dict[str, Any]]:
    path = Path("data/output/live_monitor_status.json")
    if not path.exists():
        return []
    try:
        return make_json_safe(json.loads(path.read_text(encoding="utf-8")))
    except Exception:
        return []

def _telegram_and_stockbit_configured() -> bool:
    return bool(
        (os.getenv("TELEGRAM_TOKEN") or token_available("TELEGRAM_TOKEN"))
        and (os.getenv("TELEGRAM_CHAT_ID") or token_available("TELEGRAM_CHAT_ID"))
        and (os.getenv("STOCKBIT_TOKEN") or token_available("STOCKBIT_TOKEN"))
    )

def _live_monitor_status_payload() -> dict[str, Any]:
    with live_monitor_state.lock:
        payload = {
            "running": live_monitor_state.running,
            "watchlist_path": live_monitor_state.watchlist_path or _latest_monitor_watchlist_path(),
            "interval_seconds": live_monitor_state.interval_seconds,
            "bypass_market_hours": live_monitor_state.bypass_market_hours,
            "started_at": live_monitor_state.started_at,
            "last_scan_at": live_monitor_state.last_scan_at,
            "last_error": live_monitor_state.last_error,
            "last_result_count": live_monitor_state.last_result_count,
            "logs": list(live_monitor_state.logs),
            "telegram_configured": bool(
                (os.getenv("TELEGRAM_TOKEN") or token_available("TELEGRAM_TOKEN"))
                and (os.getenv("TELEGRAM_CHAT_ID") or token_available("TELEGRAM_CHAT_ID"))
            ),
            "stockbit_configured": bool(os.getenv("STOCKBIT_TOKEN") or token_available("STOCKBIT_TOKEN")),
            "latest_watchlist_path": _latest_monitor_watchlist_path(),
            "last_results": _read_live_monitor_results()[:50],
        }
    return payload

def _start_live_monitor(
    watchlist_path: str,
    interval_seconds: float,
    bypass_market_hours: bool = False,
    replace_running: bool = False,
) -> bool:
    if not _telegram_and_stockbit_configured():
        return False

    watchlist = Path(watchlist_path)
    if not watchlist.exists():
        raise FileNotFoundError(f"Watchlist file not found: {watchlist_path}")

    with live_monitor_state.lock:
        if live_monitor_state.running and not replace_running:
            return True
        if live_monitor_state.running:
            live_monitor_state.stop_event.set()

        stop_event = threading.Event()
        live_monitor_state.stop_event = stop_event
        live_monitor_state.running = True
        live_monitor_state.watchlist_path = str(watchlist)
        live_monitor_state.interval_seconds = float(interval_seconds)
        live_monitor_state.bypass_market_hours = bool(bypass_market_hours)
        live_monitor_state.started_at = datetime.now().isoformat()
        live_monitor_state.last_error = None
        live_monitor_state.logs = []
        thread = threading.Thread(
            target=_run_live_monitor_loop,
            args=(str(watchlist), float(interval_seconds), bool(bypass_market_hours), stop_event),
            daemon=True,
        )
        live_monitor_state.thread = thread
        thread.start()
    return True

def _run_live_monitor_loop(
    watchlist_path: str,
    interval_seconds: float,
    bypass_market_hours: bool,
    stop_event: threading.Event,
) -> None:
    from .monitor import LiveTickerMonitor

    monitor = LiveTickerMonitor(watchlist_path=watchlist_path)
    live_monitor_state.append_log(f"Live monitor started for {watchlist_path} every {interval_seconds:.0f}s.")
    try:
        while not stop_event.is_set():
            try:
                results = monitor.monitor_once(bypass_market_hours=bypass_market_hours)
                with live_monitor_state.lock:
                    live_monitor_state.last_scan_at = datetime.now().isoformat()
                    live_monitor_state.last_error = None
                    live_monitor_state.last_result_count = len(results)
                live_monitor_state.append_log(f"Scan completed: {len(results)} monitored rows.")
            except Exception as exc:
                with live_monitor_state.lock:
                    live_monitor_state.last_scan_at = datetime.now().isoformat()
                    live_monitor_state.last_error = str(exc)
                live_monitor_state.append_log(f"Scan failed: {exc}")
            if stop_event.wait(interval_seconds):
                break
    finally:
        with live_monitor_state.lock:
            if live_monitor_state.stop_event is stop_event:
                live_monitor_state.running = False
        live_monitor_state.append_log("Live monitor stopped.")

@app.get("/api/bandar-scan")
def get_bandar_scan_results(output_path: str = "data/output/bandar_scan_results.csv"):
    """Return candidates from the last Bandar Scanner run."""
    path = Path(output_path)
    if not path.exists():
        from .bandar_tracker import run_bandar_scan
        try:
            df = run_bandar_scan("config/bandar_tracker.json", output_path)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error executing initial scan: {e}")
    else:
        try:
            df = pd.read_csv(path)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error reading scan results CSV: {e}")
            
    return to_json_safe_records(df)

@app.post("/api/bandar-scan/run")
def trigger_bandar_scan(payload: BandarScanRequest):
    """Run a fresh Bandar Scanner (Smart Money) scan and return results."""
    from .bandar_tracker import run_bandar_scan
    try:
        df = run_bandar_scan(
            config_path=payload.config_path,
            output_path=payload.output_path,
            force_refresh=payload.force_refresh,
            override_investor_type=payload.investor_type,
            override_period=payload.period
        )
        return to_json_safe_records(df)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error running bandar scan: {e}")

@app.get("/api/commodities")
def get_live_commodities(force_refresh: bool = False):
    """Return live global commodities prices and daily changes."""
    from .commodity_gate import fetch_live_commodities
    try:
        commodities = fetch_live_commodities(force_refresh=force_refresh)
        return list(commodities.values())
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching commodities: {e}")

@app.get("/api/live-monitor/status")
def get_live_monitor_status_api():
    """Return Telegram live monitor runtime state and recent scan output."""
    return _live_monitor_status_payload()

@app.post("/api/live-monitor/start")
def start_live_monitor_api(payload: LiveMonitorStartRequest):
    """Start the Telegram live monitor loop in the background."""
    watchlist_path = payload.watchlist_path.strip() or _latest_monitor_watchlist_path()
    watchlist = Path(watchlist_path)
    if not watchlist.exists():
        raise HTTPException(status_code=404, detail=f"Watchlist file not found: {watchlist_path}")
    if payload.interval_seconds < 30:
        raise HTTPException(status_code=400, detail="Interval minimal 30 detik agar tidak terlalu agresif ke Stockbit/Telegram.")

    started = _start_live_monitor(
        str(watchlist),
        float(payload.interval_seconds),
        bool(payload.bypass_market_hours),
        replace_running=True,
    )
    if not started:
        raise HTTPException(status_code=400, detail="TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, atau STOCKBIT_TOKEN belum lengkap.")
    return _live_monitor_status_payload()

@app.post("/api/live-monitor/stop")
def stop_live_monitor_api():
    """Request the Telegram live monitor loop to stop."""
    live_monitor_state.stop_event.set()
    with live_monitor_state.lock:
        live_monitor_state.running = False
    live_monitor_state.append_log("Stop requested from dashboard.")
    return _live_monitor_status_payload()

@app.get("/api/status")
def get_pipeline_status():
    """Return the real-time status of the currently active (or last) pipeline run.

    This endpoint is polled by the frontend every second while ``isRunning``
    is true. It is safe to call at any time (returns ``idle`` when no run
    is active).

    Returns:
        Dict matching ``PipelineStatus`` in ``frontend/src/types/api.ts``:
        ``status`` (idle/running/success/failed/cancelled), ``run_id``,
        ``progress`` (0–100), ``current_stage``, ``error``, ``logs``.
    """
    global pipeline_state
    with pipeline_state.lock:
        return {
            "status": pipeline_state.status,
            "run_id": pipeline_state.run_id,
            "progress": pipeline_state.progress,
            "current_stage": pipeline_state.current_stage,
            "error": pipeline_state.error_message,
            "logs": pipeline_state.logs
        }

@app.post("/api/cancel")
def cancel_pipeline():
    """Request cancellation of the currently running pipeline.

    Sets a threading ``Event`` that the pipeline worker thread checks between
    stages. The pipeline will complete the current stage before stopping —
    it does **not** hard-kill mid-stage.

    Returns:
        ``{"message": "..."}`` confirmation string.

    Raises:
        400: If no pipeline is currently running.
    """
    global pipeline_state
    with pipeline_state.lock:
        if pipeline_state.status != "running":
            raise HTTPException(status_code=400, detail="Tidak ada pipeline yang sedang berjalan")
        pipeline_state.cancel_event.set()
    return {"message": "Permintaan pembatalan dikirim. Pipeline akan berhenti setelah stage saat ini selesai."}

@app.post("/api/run")
def trigger_run(payload: RunRequest, background_tasks: BackgroundTasks):
    """Start a new pipeline run or resume a previously failed one.

    If ``resume_run_id`` is provided in the payload, the backend reuses the
    existing run directory and skips any stages whose output file already exists
    (see ``capture_stage`` in ``pipeline.py``). Otherwise a fresh ``run_id``
    is generated and a new directory is created.

    The pipeline runs in a background daemon thread. Poll ``GET /api/status``
    at ~1s intervals to track progress.

    Args:
        payload: ``RunRequest`` model (see ``frontend/src/types/api.ts``).
        background_tasks: FastAPI dependency (unused; thread is spawned directly
                          for compatibility with the cancel-event mechanism).

    Returns:
        ``{"message": "Pipeline started", "run_id": "20260708_091500"}``

    Raises:
        400: If a pipeline is already running, or the ticker list is empty.
    """
    global pipeline_state
    
    with pipeline_state.lock:
        if pipeline_state.status == "running":
            raise HTTPException(status_code=400, detail="A pipeline is already running")
            
    run_id = payload.resume_run_id if payload.resume_run_id else create_run_id()
    run_paths = build_run_paths(DEFAULT_RUN_ROOT, run_id)
    
    tickers_list = []
    if payload.universe_key != "manual":
        from .ticker_universe import load_universe_tickers
        tickers_list = load_universe_tickers(payload.universe_key)
    else:
        tickers_list = parse_ticker_text(payload.tickers)
        
    if not tickers_list:
        raise HTTPException(status_code=400, detail="Ticker list is empty. Please enter tickers or choose a preset.")
        
    ticker_file_path = DEFAULT_INPUT_ROOT / f"ui_tickers_{run_id}.txt"
    ticker_file_path.parent.mkdir(parents=True, exist_ok=True)
    ticker_file_path.write_text("\n".join(tickers_list) + "\n", encoding="utf-8")
    
    options = PipelineOptions(
        tickers_file=ticker_file_path,
        run_root=DEFAULT_RUN_ROOT,
        market_data_db=DEFAULT_MARKET_DATA_DB,
        run_date=payload.run_date,
        period_stage1="3mo",
        period_stage2="1y",
        windows="1D,3D,5D,10D,20D",
        strategy_mode=payload.strategy_mode,
        capital=payload.capital,
        risk_per_trade_pct=payload.risk_per_trade_pct,
        max_position_pct=payload.max_position_pct,
        bandarmology_min_score=payload.bandarmology_min_score,
        dry_run_llm=payload.dry_run_llm,
        refresh_market_data=payload.refresh_market_data,
        allow_trade_without_broker_data=payload.allow_trade_without_broker_data,
        require_orderbook_confirmation=payload.require_orderbook_confirmation,
        strict_corporate_action_filter=payload.strict_corporate_action_filter,
        hybrid_mode=payload.hybrid_mode,
        hybrid_capital_profile=payload.hybrid_capital_profile,
        hybrid_config_path=Path("config/screener.yml"),
        hybrid_max_candidates=30,
        enable_market_regime=payload.enable_market_regime,
        enable_multibar_confirm=payload.enable_multibar_confirm,
        enable_adaptive_tp=payload.enable_adaptive_tp,
        enable_liquidity_sizer=payload.enable_liquidity_sizer,
        enable_blackout=payload.enable_blackout,
    )
    
    with pipeline_state.lock:
        pipeline_state.run_id = run_id
        pipeline_state.status = "running"
        pipeline_state.progress = 0.0
        pipeline_state.current_stage = "Initialization"
        pipeline_state.logs = []
        pipeline_state.error_message = None
        pipeline_state.cancel_event.clear()
        
    thread = threading.Thread(
        target=run_pipeline_thread,
        args=(
            options,
            payload.stages,
            run_paths,
            bool(payload.resume_run_id),
            payload.auto_start_monitor,
            payload.monitor_interval_seconds,
        ),
        daemon=True
    )
    thread.start()
    
    return {
        "message": "Pipeline started",
        "run_id": run_id
    }

def parse_ticker_text(text: str) -> list[str]:
    tickers: set[str] = set()
    for raw in text.replace(",", "\n").splitlines():
        ticker = normalize_ticker(raw)
        if ticker:
            tickers.add(ticker)
    return sorted(tickers)

class ScheduledTaskModel(BaseModel):
    name: str
    time: str
    strategy_mode: str
    tickers_file: str
    universe_key: Optional[str] = None
    capital: float
    max_position_pct: float
    stages: list[str]

class ScheduleConfigModel(BaseModel):
    tasks: list[ScheduledTaskModel]

SCHEDULE_PATH = Path("config/schedule.json")

@app.get("/api/schedule", response_model=ScheduleConfigModel)
def get_schedule():
    """Read the scheduler config task list."""
    if not SCHEDULE_PATH.exists():
        return {"tasks": []}
    try:
        with open(SCHEDULE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read schedule: {e}")

@app.post("/api/schedule")
def update_schedule(config: ScheduleConfigModel):
    """Overwrite the scheduler config task list."""
    SCHEDULE_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(SCHEDULE_PATH, "w", encoding="utf-8") as f:
            json.dump(config.dict(), f, indent=2)
        return {"status": "success", "message": "Schedule updated successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to write schedule: {e}")

@app.post("/api/schedule/run-task")
def run_scheduled_task(task: ScheduledTaskModel, background_tasks: BackgroundTasks):
    """Trigger a scheduled task run immediately in the background."""
    from .scheduler import PipelineScheduler, ScheduledTask
    
    temp_task = ScheduledTask(
        name=task.name,
        time_str=task.time,
        strategy_mode=task.strategy_mode,
        tickers_file=task.tickers_file,
        capital=task.capital,
        max_position_pct=task.max_position_pct,
        stages=task.stages
    )
    
    def _run_bg():
        sched = PipelineScheduler(config_path=SCHEDULE_PATH)
        today = datetime.now().date().isoformat()
        sched.run_task(temp_task, today)
        
    background_tasks.add_task(_run_bg)
    return {"status": "started", "message": f"Task '{task.name}' triggered in background"}


# Serve compiled React static files (in production)
static_dir = Path(__file__).resolve().parent / "static"
if static_dir.exists():
    app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")
else:
    @app.get("/")
    def index_fallback():
        return {"message": "FastAPI is running. Compile React frontend to serve static assets here."}

def launch(port: int = 8000) -> None:
    import uvicorn
    def open_browser():
        webbrowser.open(f"http://localhost:{port}/")
    
    timer = threading.Timer(1.5, open_browser)
    timer.start()
    
    print(f"Starting server on http://localhost:{port}/...")
    uvicorn.run("interday_liquidity_screener.server:app", host="127.0.0.1", port=port, log_level="info")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
