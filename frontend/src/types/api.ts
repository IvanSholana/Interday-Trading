/**
 * api.ts — Centralized TypeScript type definitions for all API responses.
 *
 * All data shapes returned by the FastAPI backend (/api/*) are defined
 * here so that LLMs and developers can import them instead of untyped values.
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

/** Primitive value returned from CSV-backed stage artifacts. */
export type RunCsvCellValue = string | number | boolean | null;

/** One CSV-backed stage artifact row. */
export type RunCsvRow = Record<string, RunCsvCellValue>;

/** Paginated CSV response from a pipeline stage output file. */
export interface RunCsvResponse {
  /** Total rows available before pagination (after filtering). */
  total: number;
  /** Current page index, 1-based. */
  page: number;
  /** Max rows per page. */
  limit: number;
  /** Data rows — each row is a map of column name → value (string | number | null). */
  records: RunCsvRow[];
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
// GET /api/recommendation/{run_id}
// ---------------------------------------------------------------------------

/** Readiness bucket assigned by the recommendation layer. */
export type RecommendationReadiness =
  | 'READY'
  | 'NEEDS_LIVE_CONFIRMATION'
  | 'WATCH_ONLY'
  | 'REJECTED_OR_LOW_PRIORITY';

/** Explicit execution interpretation for agents and UI. */
export type ExecutionDecision =
  | 'REVIEW_BUY'
  | 'WAIT_CONFIRMATION'
  | 'WATCH_ONLY'
  | 'AVOID';

/** One capital-aware candidate derived from hybrid_watchlist.csv. */
export interface CandidateRecommendation {
  symbol: string;
  name: string;
  final_status: string;
  readiness: RecommendationReadiness;
  execution_decision: ExecutionDecision;
  final_score: number;
  rank: number | null;
  entry_price: number | null;
  tp1_price: number | null;
  stop_loss_price: number | null;
  target_tp_pct: number | null;
  stop_loss_pct: number | null;
  risk_reward_ratio: number | null;
  position_value: number;
  lots: number;
  capital_usage_pct: number;
  expected_gross_profit: number | null;
  estimated_buy_fee: number | null;
  estimated_sell_fee: number | null;
  estimated_slippage: number | null;
  expected_net_profit: number | null;
  max_loss_amount: number | null;
  confidence_score: number;
  confidence_components: Record<string, number>;
  decision_grade: string;
  audit_flags: string[];
  primary_reason: string;
  next_action: string;
  warnings: string;
  skip_reasons: string;
}

/** Professional decision-support pack for a completed run. */
export interface RecommendationPack {
  run_id: string;
  schema_version: string;
  policy_version: string;
  policy: Record<string, number | string>;
  capital: number;
  portfolio_target_profit_pct: number;
  portfolio_target_profit_amount: number;
  portfolio_expected_net_return_pct: number | null;
  portfolio_target_progress_pct: number;
  portfolio_profit_shortfall_amount: number;
  portfolio_target_reached: boolean;
  /** Backward-compatible alias; since schema v2 this is the portfolio profit target. */
  max_tp_pct: number;
  max_position_pct: number;
  portfolio_decision: string;
  portfolio_flags: string[];
  total_selected_position_value: number;
  total_selected_capital_usage_pct: number;
  total_selected_expected_gross_profit: number | null;
  total_selected_expected_net_profit: number | null;
  total_selected_max_loss_amount: number | null;
  total_selected_max_loss_pct: number | null;
  selected_count: number;
  ready_count: number;
  draft_count: number;
  watch_count: number;
  rejected_count: number;
  excluded_by_tp_limit_count: number;
  primary: CandidateRecommendation | null;
  candidates: CandidateRecommendation[];
  next_action: string;
  caveat: string;
}

// ---------------------------------------------------------------------------
// GET /api/run-audit/{run_id}
// ---------------------------------------------------------------------------

/** Stage artifact health row returned by the run audit endpoint. */
export interface StageArtifactAudit {
  key: string;
  path: string;
  exists: boolean;
  size_bytes: number;
  row_count: number | null;
  status: 'OK' | 'MISSING' | 'EMPTY' | 'NO_ROWS' | string;
}

/** Run-level artifact and decision-readiness audit. */
export interface RunAuditReport {
  schema_version: string;
  run_id: string;
  overall_status: string;
  summary: Record<string, RunCsvCellValue>;
  artifacts: StageArtifactAudit[];
  missing_artifacts: string[];
  recommendation: RecommendationPack | null;
  next_action: string;
  caveat: string;
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
  /** Source filename under data/input/universes, when applicable. */
  filename?: string;
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
  /** If true, start Telegram live monitor automatically after pipeline success. */
  auto_start_monitor?: boolean;
  /** Telegram live monitor interval after pipeline success, in seconds. */
  monitor_interval_seconds?: number;
  /**
   * If set, resume a previously failed run instead of starting fresh.
   * The backend will skip stages whose output files already exist in
   * the given run's directory.
   */
  resume_run_id?: string | null;
}

// ---------------------------------------------------------------------------
// GET/POST /api/schedule
// ---------------------------------------------------------------------------

export interface ScheduledTask {
  name: string;
  time: string; // "HH:MM"
  strategy_mode: 'interday' | 'bpjs';
  tickers_file: string;
  universe_key?: string;
  capital: number;
  max_position_pct: number;
  stages: string[];
}

export interface ScheduleConfig {
  tasks: ScheduledTask[];
}

// ---------------------------------------------------------------------------
// GET/POST /api/live-monitor
// ---------------------------------------------------------------------------

export interface LiveMonitorResult {
  ticker: string;
  live_price: number | null;
  entry_price: number | null;
  stop_loss: number | null;
  take_profit_1: number | null;
  take_profit_2: number | null;
  orderbook_status: string;
  alerts: string[];
  error?: string | null;
  fetched_at?: string | null;
}

export interface LiveMonitorStatus {
  running: boolean;
  watchlist_path: string;
  interval_seconds: number;
  bypass_market_hours: boolean;
  started_at: string | null;
  last_scan_at: string | null;
  last_error: string | null;
  last_result_count: number;
  logs: string[];
  telegram_configured: boolean;
  stockbit_configured: boolean;
  latest_watchlist_path: string;
  last_results: LiveMonitorResult[];
}

export interface LiveMonitorStartRequest {
  watchlist_path: string;
  interval_seconds: number;
  bypass_market_hours: boolean;
}
