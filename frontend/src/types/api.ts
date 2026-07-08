/**
 * api.ts — Centralized TypeScript type definitions for all API responses.
 *
 * All data shapes returned by the FastAPI backend (/api/*) are defined
 * here so that LLMs and developers can import them instead of using `any`.
 *
 * Usage:
 *   import type { RunSummary, PipelineStatus, RunCsvRow } from '../types/api';
 */

// ---------------------------------------------------------------------------
// GET /api/runs
// ---------------------------------------------------------------------------

/** Summary card for a single completed or in-progress pipeline run. */
export interface RunSummary {
  /** Unique run ID, formatted as YYYYMMDD_HHMMSS (e.g. "20260708_091500"). */
  run: string;
  /** Human-readable date label (e.g. "Mon, 08 Jul 2026"). */
  formatted_date: string;
  /** Total rows passing Stage 1 liquidity screen. */
  stage1_rows: number;
  /** Rows flagged as liquid (GOOD_LIQUIDITY or HIGH_LIQUIDITY). */
  liquid_rows: number;
  /** Count of rows in Stage 4 with a valid, actionable trade plan. */
  valid_trade_plans: number;
  /** Count of simulated trades with a closed P&L in the backtest output. */
  closed_trades: number;
  /** Win rate 0-1 from backtest, or null if no closed trades exist. */
  win_rate: number | null;
  /** Whether a Stage 6 AI report markdown file exists for this run. */
  report_available: boolean;
  /** Error message if this run ended in failure. */
  error?: string;
}

// ---------------------------------------------------------------------------
// GET /api/status
// ---------------------------------------------------------------------------

/**
 * Possible status values for the currently active pipeline run.
 * Mirrors the `PipelineState.status` field in server.py.
 */
export type PipelineStatusValue =
  | 'idle'
  | 'running'
  | 'success'
  | 'failed'
  | 'cancelled';

/** Real-time pipeline execution state, polled from GET /api/status. */
export interface PipelineStatus {
  /** Current execution status. */
  status: PipelineStatusValue;
  /** Run ID of the active or most recently completed run. Empty string if idle. */
  run_id: string;
  /** Display name of the stage currently executing (e.g. "Stage 3A - Stockbit Broker"). */
  current_stage: string;
  /** Completion percentage, 0.0 – 100.0. */
  progress: number;
  /** Timestamped log lines streamed from the backend worker thread. */
  logs: string[];
  /** Error message string if status is "failed", otherwise null. */
  error: string | null;
}

// ---------------------------------------------------------------------------
// GET /api/run-details/{run_id}
// ---------------------------------------------------------------------------

/** Per-stage availability map for a given run directory. */
export interface RunDetails {
  run_id: string;
  /** Maps stage key (e.g. "stage1") to whether the output CSV file exists. */
  available_stages: Record<string, boolean>;
  /** Aggregated summary metrics, mirrors RunSummary structure. */
  summary: RunSummary;
}

// ---------------------------------------------------------------------------
// GET /api/run-csv/{run_id}/{stage}
// ---------------------------------------------------------------------------

/** Paginated CSV response from a pipeline stage output file. */
export interface RunCsvResponse {
  run_id: string;
  stage: string;
  /** Total rows available before pagination (after filtering). */
  total_rows: number;
  /** Current page index, 0-based. */
  page: number;
  /** Max rows per page. */
  limit: number;
  /** Column names in display order. */
  columns: string[];
  /** Data rows — each row is a map of column name → value (string | number | null). */
  rows: Record<string, string | number | null>[];
}

// ---------------------------------------------------------------------------
// GET /api/report/{run_id}
// ---------------------------------------------------------------------------

/** AI report content for a completed run. */
export interface RunReport {
  run_id: string;
  /** Raw markdown string from the Stage 6 LLM output file. */
  content: string;
  /** True if the report file exists; false if Stage 6 was not run. */
  available: boolean;
}

// ---------------------------------------------------------------------------
// GET /api/presets
// ---------------------------------------------------------------------------

/** A ticker universe preset (e.g. LQ45, IDX80, Syariah). */
export interface UniversePreset {
  /** Machine-readable key used in API payloads (e.g. "lq45"). */
  key: string;
  /** Human-readable label shown in the UI dropdown. */
  label: string;
  /** Approximate number of tickers in this preset. */
  ticker_count: number;
  /** Short description shown as tooltip or subtitle. */
  description: string;
}

// ---------------------------------------------------------------------------
// GET /api/settings
// ---------------------------------------------------------------------------

/** API token configuration state returned by the settings endpoint. */
export interface SettingsState {
  /** Whether the Stockbit bearer token is configured. */
  stockbit_configured: boolean;
  /** Masked preview of the Stockbit token (e.g. "Bearer sk-...xxxx"). */
  stockbit_token_preview: string;
  /** Whether the DeepSeek API key is configured. */
  deepseek_configured: boolean;
  /** Masked preview of the DeepSeek key. */
  deepseek_key_preview: string;
}

// ---------------------------------------------------------------------------
// POST /api/run  (request payload)
// ---------------------------------------------------------------------------

/**
 * Capital profile keys accepted by the hybrid screener.
 * Determines position sizing constraints based on available capital.
 */
export type CapitalProfile = 'capital_500k' | 'capital_1m' | 'capital_1_5m';

/**
 * Hybrid screener execution mode.
 * Controls which scoring weights and filters are active.
 */
export type HybridMode =
  | 'normal_execution'
  | 'bpjs_live'
  | 'interday_swing'
  | 'weekend_preparation'
  | 'smart_money_first'
  | 'hybrid_dual_flow';

/** Request body for POST /api/run to start or resume a pipeline. */
export interface RunRequest {
  /** Free-text ticker list, comma or newline separated (e.g. "BBRI\nTLKM"). */
  tickers?: string;
  /** Universe preset key (e.g. "lq45"). Ignored if `tickers` is non-empty. */
  universe_key?: string;
  /** Analysis date in YYYY-MM-DD format. */
  run_date?: string;
  /** Trading strategy mode — affects Stage 5 (backtest vs paper-BPJS). */
  strategy_mode?: 'interday' | 'bpjs';
  /** List of stage keys to execute. See PipelineStage enum in constants.py. */
  stages?: string[];
  /** Total capital in IDR for position sizing (e.g. 1_000_000). */
  capital?: number;
  /** Risk fraction per trade, 0 – 1 (e.g. 0.005 = 0.5%). */
  risk_per_trade_pct?: number;
  /** Max fraction of capital per single position, 0 – 1 (e.g. 0.20 = 20%). */
  max_position_pct?: number;
  /** Minimum bandarmology net-buy score to pass Stage 3B filter. */
  bandarmology_min_score?: number;
  /** If true, skip the live LLM API call and write a placeholder report. */
  dry_run_llm?: boolean;
  /** If true, re-download OHLCV price data even if cached locally. */
  refresh_market_data?: boolean;
  /**
   * If true, allow a trade plan to be generated even when no broker-flow
   * (Stage 3A/3B) data was fetched (e.g. Stockbit token not set).
   */
  allow_trade_without_broker_data?: boolean;
  /**
   * If true, reject stocks with active corporate actions (rights issue,
   * stock split, etc.) that may cause erratic price movements.
   */
  strict_corporate_action_filter?: boolean;
  /**
   * If true, require Stage 3C orderbook confirmation before marking a stock
   * as ``EXECUTION_READY``. Defaults to ``true`` for BPJS mode.
   */
  require_orderbook_confirmation?: boolean | null;
  /** Hybrid screener mode. Defaults to "normal_execution". */
  hybrid_mode?: HybridMode;
  /** Capital profile for position size constraints. */
  hybrid_capital_profile?: CapitalProfile;
  /** Enable P1: Market Regime filter (IHSG trend check). */
  enable_market_regime?: boolean;
  /** Enable P2: Multi-bar confirmation before final status assignment. */
  enable_multibar_confirm?: boolean;
  /** Enable P3: Adaptive Take Profit adjustment based on volatility. */
  enable_adaptive_tp?: boolean;
  /** Enable P4: Liquidity-based position sizer. */
  enable_liquidity_sizer?: boolean;
  /** Enable P5: Blackout filter (ex-date, high-risk notation guard). */
  enable_blackout?: boolean;
  /**
   * If set, resume a previously failed run instead of starting fresh.
   * The backend will skip stages whose output files already exist in
   * the given run's directory.
   */
  resume_run_id?: string | null;
}
