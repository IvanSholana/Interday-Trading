import React, { useState, useEffect } from 'react';
import { Sidebar } from './components/Sidebar';
import { ProgressVisualizer } from './components/ProgressVisualizer';
import { ResultsTable } from './components/ResultsTable';
import { ChartsDashboard } from './components/ChartsDashboard';
import { ReportViewer } from './components/ReportViewer';
import { Terminal, Database, Calendar, BarChart3, FileText, LayoutDashboard, DatabaseZap } from 'lucide-react';

interface RunSummary {
  run: string;
  formatted_date: string;
  stage1_rows: number;
  liquid_rows: number;
  valid_trade_plans: number;
  closed_trades: number;
  win_rate: number | null;
  report_available: boolean;
  error?: string;
}

export default function App() {
  // Sidebar config states
  const [runDate, setRunDate] = useState('2026-07-06');
  const [strategyMode, setStrategyMode] = useState<'interday' | 'bpjs'>('interday');
  const [universeKey, setUniverseKey] = useState('lq45');
  const [tickersText, setTickersText] = useState('');
  const [capital, setCapital] = useState(10000000);
  const [selectedStages, setSelectedStages] = useState<string[]>([
    'stage1', 'stage2', 'stage3a', 'stage3b', 'stage3c', 'stage4', 'hybrid', 'stage5', 'stage6'
  ]);
  const [dryRunLlm, setDryRunLlm] = useState(true);
  const [refreshMarketData, setRefreshMarketData] = useState(false);
  const [riskPerTradePct, setRiskPerTradePct] = useState(0.5);
  const [maxPositionPct, setMaxPositionPct] = useState(20.0);

  // Runs Explorer
  const [runsList, setRunsList] = useState<RunSummary[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string>('');

  // Active Pipeline Execution State
  const [isRunning, setIsRunning] = useState(false);
  const [pipelineStatus, setPipelineStatus] = useState('idle');
  const [pipelineProgress, setPipelineProgress] = useState(0);
  const [pipelineCurrentStage, setPipelineCurrentStage] = useState('');
  const [pipelineError, setPipelineError] = useState<string | null>(null);
  const [pipelineLogs, setPipelineLogs] = useState<string[]>([]);

  // Navigation tab
  const [activeTab, setActiveTab] = useState<'dashboard' | 'results' | 'charts' | 'report'>('dashboard');

  const fetchRunsList = async (selectLatest = false) => {
    try {
      const res = await fetch('/api/runs');
      const data = await res.json();
      setRunsList(data);
      if (data.length > 0 && (!selectedRunId || selectLatest)) {
        setSelectedRunId(data[0].run); // Auto-select latest run
      }
    } catch (err) {
      console.error('Error fetching runs list:', err);
    }
  };

  useEffect(() => {
    // Initial fetch of runs
    fetchRunsList();
    // Check if a pipeline is already running on page load
    (async () => {
      try {
        const res = await fetch('/api/status');
        const data = await res.json();
        if (data.status === 'running') {
          setIsRunning(true);
          setPipelineStatus(data.status);
          setPipelineProgress(data.progress);
          setPipelineCurrentStage(data.current_stage);
          setPipelineError(data.error);
          setPipelineLogs(data.logs || []);
          setActiveTab('dashboard');
        }
      } catch (err) {
        console.error('Error checking initial pipeline status:', err);
      }
    })();
  }, []);

  // Poll status while running
  useEffect(() => {
    let interval: any = null;
    if (isRunning) {
      interval = setInterval(async () => {
        try {
          const res = await fetch('/api/status');
          const data = await res.json();
          setPipelineStatus(data.status);
          setPipelineProgress(data.progress);
          setPipelineCurrentStage(data.current_stage);
          setPipelineError(data.error);
          setPipelineLogs(data.logs || []);

          if (data.status !== 'running') {
            setIsRunning(false);
            // Refresh runs list to include the new run and select it
            if (data.run_id) {
              await fetchRunsList(true);
              setSelectedRunId(data.run_id);
            } else {
              await fetchRunsList();
            }
          }
        } catch (err) {
          console.error('Error polling status:', err);
        }
      }, 1000);
    }
    return () => {
      if (interval) clearInterval(interval);
    };
  }, [isRunning]);

  const handleStartRun = async () => {
    if (isRunning) return;
    setIsRunning(true);
    setPipelineStatus('running');
    setPipelineProgress(0);
    setPipelineLogs(['[SYS] Inisialisasi pipeline request ke backend...']);
    setActiveTab('dashboard'); // Switch to dashboard to watch logs

    try {
      const res = await fetch('/api/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
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
          hybrid_capital_profile: capital <= 750000 ? 'capital_500k' : (capital <= 1250000 ? 'capital_1m' : 'capital_1_5m'),
        }),
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Failed to start pipeline');
      }
      const data = await res.json();
      setPipelineLogs((prev) => [...prev, `[SYS] Pipeline berhasil distart dengan ID: ${data.run_id}`]);
    } catch (err: any) {
      console.error(err);
      setIsRunning(false);
      setPipelineStatus('failed');
      setPipelineError(err.message || 'Error triggering run');
      setPipelineLogs((prev) => [...prev, `[ERR] Gagal menjalankan pipeline: ${err.message}`]);
    }
  };

  const handleCancelRun = async () => {
    try {
      setPipelineLogs((prev) => [...prev, '[SYS] Mengirim permintaan pembatalan pipeline...']);
      const res = await fetch('/api/cancel', { method: 'POST' });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Gagal membatalkan pipeline');
      }
      setPipelineLogs((prev) => [...prev, '[SYS] Permintaan pembatalan dikirim. Menunggu stage saat ini selesai...']);
    } catch (err: any) {
      console.error(err);
      setPipelineLogs((prev) => [...prev, `[ERR] Gagal membatalkan: ${err.message}`]);
    }
  };

  // Find currently selected run summary details
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
        isRunning={isRunning}
        onStartRun={handleStartRun}
        onCancelRun={handleCancelRun}
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
          <button
            onClick={() => setActiveTab('dashboard')}
            className={`btn-secondary`}
            style={{
              borderRadius: '8px 8px 0 0',
              borderBottom: 'none',
              background: activeTab === 'dashboard' ? 'var(--bg-card)' : 'transparent',
              borderColor: activeTab === 'dashboard' ? 'var(--border-glass)' : 'transparent',
              color: activeTab === 'dashboard' ? 'var(--primary)' : 'var(--text-secondary)',
              fontWeight: activeTab === 'dashboard' ? 600 : 400,
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              padding: '12px 20px'
            }}
          >
            <LayoutDashboard size={16} />
            Dashboard Run
          </button>

          {selectedRunId && (
            <>
              <button
                onClick={() => setActiveTab('results')}
                className={`btn-secondary`}
                style={{
                  borderRadius: '8px 8px 0 0',
                  borderBottom: 'none',
                  background: activeTab === 'results' ? 'var(--bg-card)' : 'transparent',
                  borderColor: activeTab === 'results' ? 'var(--border-glass)' : 'transparent',
                  color: activeTab === 'results' ? 'var(--primary)' : 'var(--text-secondary)',
                  fontWeight: activeTab === 'results' ? 600 : 400,
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                  padding: '12px 20px'
                }}
              >
                <Database size={16} />
                Results Explorer
              </button>

              <button
                onClick={() => setActiveTab('charts')}
                className={`btn-secondary`}
                style={{
                  borderRadius: '8px 8px 0 0',
                  borderBottom: 'none',
                  background: activeTab === 'charts' ? 'var(--bg-card)' : 'transparent',
                  borderColor: activeTab === 'charts' ? 'var(--border-glass)' : 'transparent',
                  color: activeTab === 'charts' ? 'var(--primary)' : 'var(--text-secondary)',
                  fontWeight: activeTab === 'charts' ? 600 : 400,
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                  padding: '12px 20px'
                }}
              >
                <BarChart3 size={16} />
                Charts & Analisis
              </button>

              <button
                onClick={() => setActiveTab('report')}
                className={`btn-secondary`}
                style={{
                  borderRadius: '8px 8px 0 0',
                  borderBottom: 'none',
                  background: activeTab === 'report' ? 'var(--bg-card)' : 'transparent',
                  borderColor: activeTab === 'report' ? 'var(--border-glass)' : 'transparent',
                  color: activeTab === 'report' ? 'var(--primary)' : 'var(--text-secondary)',
                  fontWeight: activeTab === 'report' ? 600 : 400,
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                  padding: '12px 20px'
                }}
              >
                <FileText size={16} />
                Laporan Analis AI
              </button>
            </>
          )}
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
