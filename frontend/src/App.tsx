import React, { useState } from 'react';
import { Sidebar } from './components/Sidebar';
import { ProgressVisualizer } from './components/ProgressVisualizer';
import { ResultsTable } from './components/ResultsTable';
import { ChartsDashboard } from './components/ChartsDashboard';
import { ReportViewer } from './components/ReportViewer';
import { Terminal, Database, Calendar, BarChart3, FileText, LayoutDashboard, DatabaseZap } from 'lucide-react';
import { usePipeline } from './hooks/usePipeline';
import type { RunRequest, CapitalProfile } from './types/api';

/** Active navigation tab options. */
type ActiveTab = 'dashboard' | 'results' | 'charts' | 'report';

export default function App() {
  // ── Sidebar / pipeline config state ──────────────────────────────────────
  const [runDate, setRunDate] = useState<string>('2026-07-06');
  const [strategyMode, setStrategyMode] = useState<'interday' | 'bpjs'>('interday');
  const [universeKey, setUniverseKey] = useState<string>('lq45');
  const [tickersText, setTickersText] = useState<string>('');
  const [capital, setCapital] = useState<number>(10000000);
  const [selectedStages, setSelectedStages] = useState<string[]>([
    'stage1', 'stage2', 'stage3a', 'stage3b', 'stage3c', 'stage4', 'hybrid', 'stage5', 'stage6',
  ]);
  const [dryRunLlm, setDryRunLlm] = useState<boolean>(true);
  const [refreshMarketData, setRefreshMarketData] = useState<boolean>(false);
  const [riskPerTradePct, setRiskPerTradePct] = useState<number>(0.5);
  const [maxPositionPct, setMaxPositionPct] = useState<number>(20.0);

  // Peningkatan Edge (P1–P5) Toggles
  const [enableMarketRegime, setEnableMarketRegime] = useState<boolean>(false);
  const [enableMultibarConfirm, setEnableMultibarConfirm] = useState<boolean>(false);
  const [enableAdaptiveTp, setEnableAdaptiveTp] = useState<boolean>(false);
  const [enableLiquiditySizer, setEnableLiquiditySizer] = useState<boolean>(false);
  const [enableBlackout, setEnableBlackout] = useState<boolean>(false);

  // ── Navigation tab ────────────────────────────────────────────────────────
  const [activeTab, setActiveTab] = useState<ActiveTab>('dashboard');

  // ── All API + pipeline state via custom hook ───────────────────────────────
  const {
    isRunning,
    pipelineStatus,
    pipelineProgress,
    pipelineCurrentStage,
    pipelineError,
    pipelineLogs,
    runsList,
    selectedRunId,
    setSelectedRunId,
    fetchRunsList,
    handleStartRun,
    handleCancelRun,
  } = usePipeline();

  // ── Derive capital profile from capital amount ────────────────────────────
  const resolveCapitalProfile = (cap: number): CapitalProfile => {
    if (cap <= 750_000) return 'capital_500k';
    if (cap <= 1_250_000) return 'capital_1m';
    return 'capital_1_5m';
  };

  // ── Build RunRequest payload and delegate to hook ─────────────────────────
  const onStartRun = async (resumeRunId?: string): Promise<void> => {
    const payload: RunRequest = {
      tickers: tickersText,
      universe_key: universeKey,
      run_date: runDate,
      strategy_mode: strategyMode,
      stages: selectedStages,
      capital,
      risk_per_trade_pct: riskPerTradePct / 100,
      max_position_pct: maxPositionPct / 100,
      bandarmology_min_score: 60,
      dry_run_llm: dryRunLlm,
      refresh_market_data: refreshMarketData,
      allow_trade_without_broker_data: false,
      require_orderbook_confirmation: strategyMode === 'bpjs' ? true : null,
      strict_corporate_action_filter: false,
      hybrid_mode: strategyMode === 'bpjs' ? 'bpjs_live' : 'normal_execution',
      hybrid_capital_profile: resolveCapitalProfile(capital),
      enable_market_regime: enableMarketRegime,
      enable_multibar_confirm: enableMultibarConfirm,
      enable_adaptive_tp: enableAdaptiveTp,
      enable_liquidity_sizer: enableLiquiditySizer,
      enable_blackout: enableBlackout,
    };
    setActiveTab('dashboard');
    await handleStartRun(payload, resumeRunId);
  };

  // ── Derived values ────────────────────────────────────────────────────────
  const selectedRunSummary = runsList.find((r) => r.run === selectedRunId);

  return (
    <div className="app-container">
      {/* Settings control panel */}
      <Sidebar
        runDate={runDate}
        setRunDate={setRunDate}
        strategyMode={strategyMode}
        setStrategyMode={setStrategyMode}
        universeKey={universeKey}
        setUniverseKey={setUniverseKey}
        tickersText={tickersText}
        setTickersText={setTickersText}
        capital={capital}
        setCapital={setCapital}
        selectedStages={selectedStages}
        setSelectedStages={setSelectedStages}
        dryRunLlm={dryRunLlm}
        setDryRunLlm={setDryRunLlm}
        refreshMarketData={refreshMarketData}
        setRefreshMarketData={setRefreshMarketData}
        riskPerTradePct={riskPerTradePct}
        setRiskPerTradePct={setRiskPerTradePct}
        maxPositionPct={maxPositionPct}
        setMaxPositionPct={setMaxPositionPct}
        enableMarketRegime={enableMarketRegime}
        setEnableMarketRegime={setEnableMarketRegime}
        enableMultibarConfirm={enableMultibarConfirm}
        setEnableMultibarConfirm={setEnableMultibarConfirm}
        enableAdaptiveTp={enableAdaptiveTp}
        setEnableAdaptiveTp={setEnableAdaptiveTp}
        enableLiquiditySizer={enableLiquiditySizer}
        setEnableLiquiditySizer={setEnableLiquiditySizer}
        enableBlackout={enableBlackout}
        setEnableBlackout={setEnableBlackout}
        isRunning={isRunning}
        onStartRun={onStartRun}
        onCancelRun={handleCancelRun}
        selectedRunId={selectedRunId}
      />

      {/* Main dashboard content area */}
      <div className="content-wrapper">

        {/* Top Header / Run Selector */}
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '20px', justifyContent: 'space-between', alignItems: 'center', marginBottom: '32px' }}>
          <div>
            <h1 style={{ fontSize: '2rem', color: 'white' }}>IDX Interday Trading Dashboard</h1>
            <p style={{ color: 'var(--text-secondary)', marginTop: '4px', fontSize: '0.9rem' }}>
              Analisis likuiditas, teknikal, bandarmology, antrean orderbook, dan visualisasi strategi trading.
            </p>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <span style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>Hasil Analisis Run:</span>
            <select
              className="form-select"
              style={{ width: '220px', background: 'rgba(99, 102, 241, 0.1)', borderColor: 'var(--primary)' }}
              value={selectedRunId}
              onChange={(e) => setSelectedRunId(e.target.value)}
              disabled={isRunning}
            >
              {runsList.map((r) => (
                <option key={r.run} value={r.run}>
                  {r.formatted_date} ({r.run})
                </option>
              ))}
            </select>
            <button onClick={() => fetchRunsList()} className="btn-secondary" style={{ padding: '10px 14px' }} disabled={isRunning}>
              Refresh
            </button>
          </div>
        </div>

        {/* Selected Run Quick Stats Cards */}
        {selectedRunSummary && !isRunning && (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '16px', marginBottom: '32px' }}>
            <div className="glass-card" style={{ padding: '16px 20px', borderLeft: '3px solid var(--primary)' }}>
              <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>Emiten Lolos Stage 1</span>
              <h3 style={{ fontSize: '1.5rem', color: 'white', marginTop: '4px' }}>
                {selectedRunSummary.liquid_rows} <span style={{ fontSize: '0.85rem', fontWeight: 400, color: 'var(--text-muted)' }}>/ {selectedRunSummary.stage1_rows}</span>
              </h3>
            </div>
            <div className="glass-card" style={{ padding: '16px 20px', borderLeft: '3px solid var(--color-success)' }}>
              <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>Rencana Trade Valid</span>
              <h3 style={{ fontSize: '1.5rem', color: 'white', marginTop: '4px' }}>{selectedRunSummary.valid_trade_plans}</h3>
            </div>
            <div className="glass-card" style={{ padding: '16px 20px', borderLeft: '3px solid var(--color-info)' }}>
              <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>Sinyal Terisi (Backtest)</span>
              <h3 style={{ fontSize: '1.5rem', color: 'white', marginTop: '4px' }}>{selectedRunSummary.closed_trades}</h3>
            </div>
            <div className="glass-card" style={{ padding: '16px 20px', borderLeft: '3px solid var(--color-neutral)' }}>
              <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>Laporan AI</span>
              <h3 style={{ fontSize: '0.9rem', color: 'white', marginTop: '10px' }}>
                {selectedRunSummary.report_available ? (
                  <span className="badge badge-success">Tersedia</span>
                ) : (
                  <span className="badge badge-neutral">Kosong</span>
                )}
              </h3>
            </div>
          </div>
        )}

        {/* Navigation Tabs */}
        <div style={{ display: 'flex', gap: '8px', borderBottom: '1px solid var(--border-glass)', paddingBottom: '1px', marginBottom: '24px' }}>
          {(['dashboard', 'results', 'charts', 'report'] as const).map((tab) => {
            const icons: Record<ActiveTab, React.ReactNode> = {
              dashboard: <LayoutDashboard size={16} />,
              results: <Database size={16} />,
              charts: <BarChart3 size={16} />,
              report: <FileText size={16} />,
            };
            const labels: Record<ActiveTab, string> = {
              dashboard: 'Dashboard Run',
              results: 'Results Explorer',
              charts: 'Charts & Analisis',
              report: 'Laporan Analis AI',
            };
            if (tab !== 'dashboard' && !selectedRunId) return null;
            return (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className="btn-secondary"
                style={{
                  borderRadius: '8px 8px 0 0',
                  borderBottom: 'none',
                  background: activeTab === tab ? 'var(--bg-card)' : 'transparent',
                  borderColor: activeTab === tab ? 'var(--border-glass)' : 'transparent',
                  color: activeTab === tab ? 'var(--primary)' : 'var(--text-secondary)',
                  fontWeight: activeTab === tab ? 600 : 400,
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                  padding: '12px 20px',
                }}
              >
                {icons[tab]}
                {labels[tab]}
              </button>
            );
          })}
        </div>

        {/* Tab Contents */}
        <div style={{ marginTop: '12px' }}>
          {activeTab === 'dashboard' && (
            <ProgressVisualizer
              status={pipelineStatus}
              progress={pipelineProgress}
              currentStage={pipelineCurrentStage}
              error={pipelineError}
              logs={pipelineLogs}
            />
          )}
          {activeTab === 'results' && selectedRunId && (
            <ResultsTable runId={selectedRunId} />
          )}
          {activeTab === 'charts' && selectedRunId && (
            <ChartsDashboard runId={selectedRunId} />
          )}
          {activeTab === 'report' && selectedRunId && (
            <ReportViewer runId={selectedRunId} />
          )}
        </div>

      </div>
    </div>
  );
}
