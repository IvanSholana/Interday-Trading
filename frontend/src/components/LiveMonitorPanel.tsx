import React, { useEffect, useState } from 'react';
import { AlertCircle, BellRing, CheckCircle, Play, Square, RefreshCw } from 'lucide-react';
import type { LiveMonitorStatus, LiveMonitorStartRequest, RunSummary } from '../types/api';

export const LiveMonitorPanel: React.FC = () => {
  const [status, setStatus] = useState<LiveMonitorStatus | null>(null);
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [selectedRunId, setSelectedRunId] = useState('latest');
  const [intervalMinutes, setIntervalMinutes] = useState(5);
  const [bypassMarketHours, setBypassMarketHours] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  const fetchStatus = async () => {
    setError(null);
    try {
      const res = await fetch('/api/live-monitor/status');
      if (!res.ok) {
        const payload = await res.json();
        throw new Error(payload.detail ?? 'Gagal mengambil status Telegram monitor.');
      }
      const payload = await res.json() as LiveMonitorStatus;
      setStatus(payload);
      if (payload.running) {
        setIntervalMinutes(Math.max(1, Math.round(payload.interval_seconds / 60)));
        setBypassMarketHours(payload.bypass_market_hours);
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Koneksi ke backend gagal.';
      setError(message);
    }
  };

  const fetchRuns = async () => {
    try {
      const res = await fetch('/api/runs');
      if (res.ok) {
        const payload = await res.json() as RunSummary[];
        setRuns(payload);
      }
    } catch (err) {
      console.error(err);
    }
  };

  useEffect(() => {
    fetchStatus();
    fetchRuns();
    const timer = window.setInterval(fetchStatus, 5000);
    return () => window.clearInterval(timer);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const handleStart = async () => {
    setLoading(true);
    setError(null);
    setSuccessMsg(null);
    const selectedWatchlistPath = selectedRunId === 'latest'
      ? ''
      : `data/output/ui_runs/${selectedRunId}/hybrid_watchlist.csv`;
    const payload: LiveMonitorStartRequest = {
      watchlist_path: selectedWatchlistPath,
      interval_seconds: Math.max(30, intervalMinutes * 60),
      bypass_market_hours: bypassMarketHours,
    };
    try {
      const res = await fetch('/api/live-monitor/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        const body = await res.json();
        throw new Error(body.detail ?? 'Gagal menjalankan live monitor.');
      }
      const nextStatus = await res.json() as LiveMonitorStatus;
      setStatus(nextStatus);
      setSuccessMsg('Telegram live monitor aktif.');
      setTimeout(() => setSuccessMsg(null), 3000);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Gagal menjalankan live monitor.';
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  const handleStop = async () => {
    setLoading(true);
    setError(null);
    setSuccessMsg(null);
    try {
      const res = await fetch('/api/live-monitor/stop', { method: 'POST' });
      if (!res.ok) {
        const body = await res.json();
        throw new Error(body.detail ?? 'Gagal menghentikan live monitor.');
      }
      const nextStatus = await res.json() as LiveMonitorStatus;
      setStatus(nextStatus);
      setSuccessMsg('Telegram live monitor dihentikan.');
      setTimeout(() => setSuccessMsg(null), 3000);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Gagal menghentikan live monitor.';
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  const formatPrice = (value: number | null) => {
    if (value === null || Number.isNaN(value)) return '-';
    return `Rp ${Math.round(value).toLocaleString('id-ID')}`;
  };

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 360px', gap: '24px', alignItems: 'start' }}>
      <div className="glass-card" style={{ padding: '24px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '20px' }}>
          <div style={{ padding: '8px', background: 'var(--color-info-bg)', borderRadius: '8px', color: 'var(--color-info)' }}>
            <BellRing size={20} />
          </div>
          <div>
            <h3 style={{ fontSize: '1.1rem', color: 'white', margin: 0 }}>Telegram Live Monitor</h3>
            <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', margin: '4px 0 0' }}>
              Scan watchlist berkala dan kirim alert Telegram saat entry zone, TP, atau stop-loss tersentuh.
            </p>
          </div>
        </div>

        {error && (
          <div className="glass-card" style={{ borderColor: 'var(--color-danger-border)', background: 'rgba(239, 68, 68, 0.05)', padding: '12px 16px', marginBottom: '20px', display: 'flex', gap: '10px', alignItems: 'center', color: 'var(--color-danger)' }}>
            <AlertCircle size={18} />
            <span style={{ fontSize: '0.85rem' }}>{error}</span>
          </div>
        )}

        {successMsg && (
          <div className="glass-card" style={{ borderColor: 'var(--color-success-border)', background: 'rgba(16, 185, 129, 0.05)', padding: '12px 16px', marginBottom: '20px', display: 'flex', gap: '10px', alignItems: 'center', color: 'var(--color-success)' }}>
            <CheckCircle size={18} />
            <span style={{ fontSize: '0.85rem' }}>{successMsg}</span>
          </div>
        )}

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '16px', marginBottom: '20px' }}>
          <div className="glass-card" style={{ padding: '16px', background: 'rgba(255,255,255,0.02)' }}>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>Status</span>
            <h3 style={{ color: 'white', marginTop: '8px' }}>
              {status?.running ? <span className="badge badge-success">RUNNING</span> : <span className="badge badge-neutral">STOPPED</span>}
            </h3>
          </div>
          <div className="glass-card" style={{ padding: '16px', background: 'rgba(255,255,255,0.02)' }}>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>Telegram</span>
            <h3 style={{ color: 'white', marginTop: '8px' }}>
              {status?.telegram_configured ? <span className="badge badge-success">Configured</span> : <span className="badge badge-danger">Missing Token</span>}
            </h3>
          </div>
          <div className="glass-card" style={{ padding: '16px', background: 'rgba(255,255,255,0.02)' }}>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>Last Scan</span>
            <h3 style={{ color: 'white', fontSize: '0.9rem', marginTop: '8px' }}>{status?.last_scan_at ?? '-'}</h3>
          </div>
        </div>

        {status?.last_error && (
          <div className="glass-card" style={{ borderColor: 'var(--color-danger-border)', background: 'rgba(239, 68, 68, 0.04)', padding: '12px 16px', marginBottom: '16px', color: 'var(--color-danger)', fontSize: '0.85rem' }}>
            Error terakhir: {status.last_error}
          </div>
        )}

        <div style={{ overflowX: 'auto', border: '1px solid var(--border-glass)', borderRadius: '8px' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left' }}>
            <thead>
              <tr style={{ background: 'rgba(0,0,0,0.3)', borderBottom: '1px solid var(--border-glass)', color: 'white', fontSize: '0.8rem' }}>
                <th style={{ padding: '12px 16px' }}>Ticker</th>
                <th style={{ padding: '12px 16px' }}>Live</th>
                <th style={{ padding: '12px 16px' }}>Entry</th>
                <th style={{ padding: '12px 16px' }}>Orderbook</th>
                <th style={{ padding: '12px 16px' }}>Alerts</th>
              </tr>
            </thead>
            <tbody>
              {(status?.last_results ?? []).length === 0 ? (
                <tr>
                  <td colSpan={5} style={{ padding: '32px', color: 'var(--text-secondary)', textAlign: 'center' }}>
                    Belum ada hasil live monitor.
                  </td>
                </tr>
              ) : (
                status?.last_results.map((row) => (
                  <tr key={row.ticker} style={{ borderBottom: '1px solid var(--border-glass)', fontSize: '0.85rem' }}>
                    <td style={{ padding: '12px 16px', color: 'white', fontWeight: 700 }}>{row.ticker}</td>
                    <td style={{ padding: '12px 16px', color: 'var(--text-secondary)' }}>{formatPrice(row.live_price)}</td>
                    <td style={{ padding: '12px 16px', color: 'var(--text-secondary)' }}>{formatPrice(row.entry_price)}</td>
                    <td style={{ padding: '12px 16px', color: 'var(--text-secondary)' }}>{row.orderbook_status}</td>
                    <td style={{ padding: '12px 16px' }}>
                      {row.alerts.length > 0 ? row.alerts.map((alert) => (
                        <span key={alert} className="badge badge-warning" style={{ marginRight: '6px', fontSize: '0.7rem' }}>{alert}</span>
                      )) : <span style={{ color: 'var(--text-muted)' }}>-</span>}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="glass-card" style={{ padding: '24px' }}>
        <h3 style={{ fontSize: '1.05rem', color: 'white', margin: '0 0 16px' }}>Pengaturan Monitor</h3>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>Sumber Watchlist</span>
            <select
              className="form-select"
              value={selectedRunId}
              onChange={(event) => setSelectedRunId(event.target.value)}
            >
              <option value="latest">Otomatis: watchlist run terbaru</option>
              {runs.map((run) => (
                <option key={run.run} value={run.run}>
                  {run.formatted_date} ({run.run})
                </option>
              ))}
            </select>
            <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>
              Aktif sekarang: {status?.watchlist_path ?? '-'}
            </span>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>Interval Scan (menit)</span>
            <input
              type="number"
              min={1}
              className="form-control"
              value={intervalMinutes}
              onChange={(event) => setIntervalMinutes(Number(event.target.value))}
            />
          </div>

          <label style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '0.8rem', color: 'var(--text-secondary)', cursor: 'pointer' }}>
            <input
              type="checkbox"
              checked={bypassMarketHours}
              onChange={(event) => setBypassMarketHours(event.target.checked)}
            />
            Bypass jam bursa untuk testing
          </label>

          <div style={{ display: 'flex', gap: '10px', marginTop: '8px' }}>
            <button
              className="btn-primary"
              onClick={handleStart}
              disabled={loading || status?.running}
              style={{ flex: 1, display: 'flex', justifyContent: 'center', alignItems: 'center', gap: '8px' }}
            >
              <Play size={14} />
              Start
            </button>
            <button
              className="btn-secondary"
              onClick={handleStop}
              disabled={loading || !status?.running}
              style={{ flex: 1, display: 'flex', justifyContent: 'center', alignItems: 'center', gap: '8px', color: 'var(--color-danger)' }}
            >
              <Square size={14} />
              Stop
            </button>
          </div>

          <button className="btn-secondary" onClick={fetchStatus} style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', gap: '8px' }}>
            <RefreshCw size={14} />
            Refresh Status
          </button>

          <div style={{ marginTop: '8px', fontSize: '0.75rem', color: 'var(--text-muted)', lineHeight: 1.6 }}>
            Monitor ini hanya alert Telegram. Tidak ada auto-order. Default-nya mengikuti jam bursa; aktifkan bypass hanya untuk testing.
          </div>
        </div>

        <div style={{ marginTop: '20px' }}>
          <h4 style={{ color: 'white', fontSize: '0.9rem', marginBottom: '10px' }}>Log Monitor</h4>
          <div style={{ background: 'rgba(0,0,0,0.25)', border: '1px solid var(--border-glass)', borderRadius: '8px', padding: '12px', maxHeight: '220px', overflowY: 'auto', fontFamily: 'monospace', fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
            {(status?.logs ?? []).length === 0 ? 'Belum ada log.' : status?.logs.map((line) => <div key={line}>{line}</div>)}
          </div>
        </div>
      </div>
    </div>
  );
};
