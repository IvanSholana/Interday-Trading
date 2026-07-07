import React, { useState, useEffect } from 'react';
import { Settings, Key, HelpCircle, Shield, Sliders, Layers } from 'lucide-react';

interface Preset {
  key: string;
  label: string;
  ticker_count: number;
  description: string;
}

interface SettingsState {
  stockbit_configured: boolean;
  stockbit_token_preview: string;
  deepseek_configured: boolean;
  deepseek_key_preview: string;
}

interface SidebarProps {
  runDate: string;
  setRunDate: (d: string) => void;
  strategyMode: 'interday' | 'bpjs';
  setStrategyMode: (m: 'interday' | 'bpjs') => void;
  universeKey: string;
  setUniverseKey: (k: string) => void;
  tickersText: string;
  setTickersText: (t: string) => void;
  capital: number;
  setCapital: (c: number) => void;
  selectedStages: string[];
  setSelectedStages: (stages: string[]) => void;
  dryRunLlm: boolean;
  setDryRunLlm: (d: boolean) => void;
  refreshMarketData: boolean;
  setRefreshMarketData: (r: boolean) => void;
  riskPerTradePct: number;
  setRiskPerTradePct: (r: number) => void;
  maxPositionPct: number;
  setMaxPositionPct: (m: number) => void;
  isRunning: boolean;
  onStartRun: () => void;
  onCancelRun: () => void;
}

export const Sidebar: React.FC<SidebarProps> = ({
  runDate,
  setRunDate,
  strategyMode,
  setStrategyMode,
  universeKey,
  setUniverseKey,
  tickersText,
  setTickersText,
  capital,
  setCapital,
  selectedStages,
  setSelectedStages,
  dryRunLlm,
  setDryRunLlm,
  refreshMarketData,
  setRefreshMarketData,
  riskPerTradePct,
  setRiskPerTradePct,
  maxPositionPct,
  setMaxPositionPct,
  isRunning,
  onStartRun,
  onCancelRun,
}) => {
  const [presets, setPresets] = useState<Preset[]>([]);
  const [settings, setSettings] = useState<SettingsState>({
    stockbit_configured: false,
    stockbit_token_preview: '',
    deepseek_configured: false,
    deepseek_key_preview: '',
  });

  const [stockbitToken, setStockbitToken] = useState('');
  const [deepseekKey, setDeepseekKey] = useState('');
  const [showSecrets, setShowSecrets] = useState(false);

  useEffect(() => {
    // Fetch universes
    fetch('/api/presets')
      .then((res) => res.json())
      .then((data) => setPresets(data))
      .catch((err) => console.error('Error fetching presets:', err));

    // Fetch credentials status
    fetch('/api/settings')
      .then((res) => res.json())
      .then((data) => setSettings(data))
      .catch((err) => console.error('Error fetching settings:', err));
  }, []);

  // When universe changes, fetch default tickers to show in text editor
  useEffect(() => {
    if (universeKey !== 'manual') {
      fetch(`/api/presets/${universeKey}`)
        .then((res) => res.json())
        .then((data) => {
          if (data.tickers) {
            setTickersText(data.tickers.join('\n'));
          }
        })
        .catch((err) => console.error('Error fetching tickers for preset:', err));
    }
  }, [universeKey, setTickersText]);

  const handleUpdateSettings = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const res = await fetch('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          stockbit_token: stockbitToken,
          deepseek_api_key: deepseekKey,
        }),
      });
      const data = await res.json();
      alert(data.message);
      
      // Clear inputs
      setStockbitToken('');
      setDeepseekKey('');
      
      // Refresh status
      const statusRes = await fetch('/api/settings');
      const statusData = await statusRes.json();
      setSettings(statusData);
    } catch (err) {
      console.error(err);
      alert('Failed to update credentials');
    }
  };

  const allStages = [
    { key: 'stage1', label: 'Stage 1: Liquidity Screen' },
    { key: 'stage2', label: 'Stage 2: Technical Screen' },
    { key: 'stage3a', label: 'Stage 3A: Stockbit Broker Flow' },
    { key: 'stage3b', label: 'Stage 3B: Bandarmology Scoring' },
    { key: 'stage3c', label: 'Stage 3C: Orderbook Filter' },
    { key: 'stage4', label: 'Stage 4: Trade Planning' },
    { key: 'hybrid', label: 'Stage Hybrid: Watchlist Final' },
    { key: 'stage5', label: 'Stage 5: Backtest & Paper Journal' },
    { key: 'stage6', label: 'Stage 6: AI report' },
  ];

  const toggleStage = (stageKey: string) => {
    if (selectedStages.includes(stageKey)) {
      setSelectedStages(selectedStages.filter((s) => s !== stageKey));
    } else {
      setSelectedStages([...selectedStages, stageKey]);
    }
  };

  return (
    <div className="sidebar-wrapper">
      {/* Brand Header */}
      <div style={{ padding: '24px', borderBottom: '1px solid var(--border-glass)', display: 'flex', alignItems: 'center', gap: '12px' }}>
        <div style={{ padding: '8px', background: 'var(--primary-gradient)', borderRadius: '10px' }}>
          <Settings size={20} color="white" className="animate-spin-slow" />
        </div>
        <div>
          <h2 style={{ fontSize: '1.25rem', fontWeight: 700, color: 'white' }}>IDX Screener</h2>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>Vite + FastAPI local dashboard</span>
        </div>
      </div>

      {/* Sidebar Content Scroll Area */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '24px' }}>
        {/* Main Settings Section */}
        <div style={{ marginBottom: '24px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '16px', color: 'white' }}>
            <Sliders size={16} />
            <h3 style={{ fontSize: '0.95rem', fontWeight: 600 }}>Parameter Utama</h3>
          </div>

          <div className="form-group">
            <label className="form-label">Tanggal Analisis</label>
            <input
              type="date"
              className="form-input"
              value={runDate}
              onChange={(e) => setRunDate(e.target.value)}
            />
          </div>

          <div className="form-group">
            <label className="form-label">Strategi Mode</label>
            <div style={{ display: 'flex', gap: '8px' }}>
              <button
                type="button"
                className={`btn-secondary`}
                style={{
                  flex: 1,
                  background: strategyMode === 'interday' ? 'var(--primary-glow)' : '',
                  borderColor: strategyMode === 'interday' ? 'var(--primary)' : '',
                  fontWeight: 600
                }}
                onClick={() => setStrategyMode('interday')}
              >
                Swing Interday
              </button>
              <button
                type="button"
                className={`btn-secondary`}
                style={{
                  flex: 1,
                  background: strategyMode === 'bpjs' ? 'var(--primary-glow)' : '',
                  borderColor: strategyMode === 'bpjs' ? 'var(--primary)' : '',
                  fontWeight: 600
                }}
                onClick={() => setStrategyMode('bpjs')}
              >
                Fast BPJS
              </button>
            </div>
          </div>

          <div className="form-group">
            <label className="form-label">Modal Screening (IDR)</label>
            <input
              type="number"
              className="form-input"
              value={capital}
              onChange={(e) => setCapital(parseFloat(e.target.value) || 0)}
              placeholder="e.g. 500000"
            />
          </div>

          <div style={{ display: 'flex', gap: '12px' }}>
            <div className="form-group" style={{ flex: 1 }}>
              <label className="form-label" style={{ display: 'flex', alignItems: 'center', gap: '4px', whiteSpace: 'nowrap' }}>
                Risiko/Trade (%)
                <span title="Risiko maksimal kerugian per transaksi dari total modal (default: 0.5%)" style={{ cursor: 'help', color: 'var(--text-muted)' }}>
                  <HelpCircle size={12} />
                </span>
              </label>
              <input
                type="number"
                step="0.05"
                className="form-input"
                value={riskPerTradePct}
                onChange={(e) => setRiskPerTradePct(parseFloat(e.target.value) || 0)}
              />
            </div>
            <div className="form-group" style={{ flex: 1 }}>
              <label className="form-label" style={{ display: 'flex', alignItems: 'center', gap: '4px', whiteSpace: 'nowrap' }}>
                Max Posisi (%)
                <span title="Maksimal alokasi modal untuk satu emiten (default: 20%)" style={{ cursor: 'help', color: 'var(--text-muted)' }}>
                  <HelpCircle size={12} />
                </span>
              </label>
              <input
                type="number"
                step="1"
                className="form-input"
                value={maxPositionPct}
                onChange={(e) => setMaxPositionPct(parseFloat(e.target.value) || 0)}
              />
            </div>
          </div>
        </div>

        {/* Universe Preset Section */}
        <div style={{ marginBottom: '24px', borderTop: '1px solid var(--border-glass)', paddingTop: '20px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '16px', color: 'white' }}>
            <Layers size={16} />
            <h3 style={{ fontSize: '0.95rem', fontWeight: 600 }}>Daftar Saham</h3>
          </div>

          <div className="form-group">
            <label className="form-label">Pilih Preset Indeks</label>
            <select
              className="form-select"
              value={universeKey}
              onChange={(e) => setUniverseKey(e.target.value)}
            >
              {presets.map((p) => (
                <option key={p.key} value={p.key}>
                  {p.label} ({p.ticker_count} Ticker)
                </option>
              ))}
            </select>
          </div>

          <div className="form-group">
            <label className="form-label">Edit Ticker (1 per baris)</label>
            <textarea
              className="form-textarea"
              style={{ minHeight: '120px', fontSize: '0.8rem', fontFamily: 'var(--font-mono)' }}
              value={tickersText}
              onChange={(e) => setTickersText(e.target.value)}
              placeholder="Pilih preset atau tulis manual kode saham di sini"
            />
          </div>
        </div>

        {/* Stages Selection */}
        <div style={{ marginBottom: '24px', borderTop: '1px solid var(--border-glass)', paddingTop: '20px' }}>
          <h3 style={{ fontSize: '0.95rem', fontWeight: 600, color: 'white', marginBottom: '16px' }}>Tahapan Pipeline</h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
            {allStages.map((s) => (
              <label
                key={s.key}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '10px',
                  fontSize: '0.85rem',
                  color: 'var(--text-secondary)',
                  cursor: 'pointer',
                }}
              >
                <input
                  type="checkbox"
                  style={{ accentColor: 'var(--primary)' }}
                  checked={selectedStages.includes(s.key)}
                  onChange={() => toggleStage(s.key)}
                />
                {s.label}
              </label>
            ))}
          </div>
        </div>

        {/* Configurations Toggle */}
        <div style={{ marginBottom: '24px', borderTop: '1px solid var(--border-glass)', paddingTop: '20px' }}>
          <h3 style={{ fontSize: '0.95rem', fontWeight: 600, color: 'white', marginBottom: '16px' }}>Opsi Tambahan</h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
            <label style={{ display: 'flex', alignItems: 'center', gap: '10px', fontSize: '0.85rem', color: 'var(--text-secondary)', cursor: 'pointer' }}>
              <input
                type="checkbox"
                style={{ accentColor: 'var(--primary)' }}
                checked={refreshMarketData}
                onChange={() => setRefreshMarketData(!refreshMarketData)}
              />
              Ambil Ulang Harga (Bypass Cache)
            </label>
            <label style={{ display: 'flex', alignItems: 'center', gap: '10px', fontSize: '0.85rem', color: 'var(--text-secondary)', cursor: 'pointer' }}>
              <input
                type="checkbox"
                style={{ accentColor: 'var(--primary)' }}
                checked={dryRunLlm}
                onChange={() => setDryRunLlm(!dryRunLlm)}
              />
              Simulasi AI Laporan (Stage 6)
            </label>
          </div>
        </div>

        {/* Credentials updates */}
        <div style={{ borderTop: '1px solid var(--border-glass)', paddingTop: '20px', marginBottom: '20px' }}>
          <button
            type="button"
            className="btn-secondary"
            style={{ width: '100%', fontSize: '0.85rem', display: 'flex', justifyContent: 'space-between', padding: '10px 16px' }}
            onClick={() => setShowSecrets(!showSecrets)}
          >
            <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}><Key size={14} /> Token API & Kunci</span>
            <span>{showSecrets ? '▲' : '▼'}</span>
          </button>

          {showSecrets && (
            <form onSubmit={handleUpdateSettings} style={{ marginTop: '16px', background: 'rgba(0,0,0,0.2)', padding: '16px', borderRadius: '8px', border: '1px solid var(--border-glass)' }}>
              <div className="form-group" style={{ marginBottom: '12px' }}>
                <label className="form-label" style={{ fontSize: '0.75rem', display: 'flex', justifyContent: 'space-between' }}>
                  <span>Stockbit Token</span>
                  <span style={{ color: settings.stockbit_configured ? 'var(--color-success)' : 'var(--color-danger)' }}>
                    {settings.stockbit_configured ? 'Aktif' : 'Kosong'}
                  </span>
                </label>
                <input
                  type="password"
                  className="form-input"
                  style={{ fontSize: '0.8rem', padding: '6px 10px' }}
                  placeholder="Tempel Stockbit Bearer token..."
                  value={stockbitToken}
                  onChange={(e) => setStockbitToken(e.target.value)}
                />
              </div>

              <div className="form-group" style={{ marginBottom: '16px' }}>
                <label className="form-label" style={{ fontSize: '0.75rem', display: 'flex', justifyContent: 'space-between' }}>
                  <span>DeepSeek API Key</span>
                  <span style={{ color: settings.deepseek_configured ? 'var(--color-success)' : 'var(--color-danger)' }}>
                    {settings.deepseek_configured ? 'Aktif' : 'Kosong'}
                  </span>
                </label>
                <input
                  type="password"
                  className="form-input"
                  style={{ fontSize: '0.8rem', padding: '6px 10px' }}
                  placeholder="DeepSeek API key..."
                  value={deepseekKey}
                  onChange={(e) => setDeepseekKey(e.target.value)}
                />
              </div>

              <button type="submit" className="btn-primary" style={{ width: '100%', fontSize: '0.8rem', padding: '8px 16px' }}>
                Simpan Credentials
              </button>
            </form>
          )}
        </div>
      </div>

      {/* Bottom Run Action Buttons */}
      <div style={{ padding: '24px', borderTop: '1px solid var(--border-glass)', display: 'flex', flexDirection: 'column', gap: '10px' }}>
        {isRunning && (
          <button
            type="button"
            style={{
              width: '100%',
              padding: '14px 20px',
              fontWeight: 600,
              fontSize: '0.95rem',
              borderRadius: '12px',
              border: 'none',
              cursor: 'pointer',
              background: 'linear-gradient(135deg, #ef4444 0%, #dc2626 100%)',
              color: 'white',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '8px',
              transition: 'all 0.2s',
              boxShadow: '0 4px 15px rgba(239, 68, 68, 0.3)',
            }}
            onClick={onCancelRun}
            onMouseEnter={(e) => { (e.currentTarget as HTMLButtonElement).style.transform = 'scale(1.02)'; (e.currentTarget as HTMLButtonElement).style.boxShadow = '0 6px 20px rgba(239, 68, 68, 0.5)'; }}
            onMouseLeave={(e) => { (e.currentTarget as HTMLButtonElement).style.transform = 'scale(1)'; (e.currentTarget as HTMLButtonElement).style.boxShadow = '0 4px 15px rgba(239, 68, 68, 0.3)'; }}
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <rect x="3" y="3" width="18" height="18" rx="2" />
            </svg>
            Batalkan Pipeline
          </button>
        )}
        <button
          type="button"
          className="btn-primary"
          style={{ width: '100%' }}
          disabled={isRunning}
          onClick={onStartRun}
        >
          {isRunning ? 'Pipeline Berjalan...' : 'Jalankan Analisis'}
        </button>
      </div>
    </div>
  );
};
