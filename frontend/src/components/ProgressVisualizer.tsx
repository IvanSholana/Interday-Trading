import React, { useState, useEffect, useRef } from 'react';
import { Loader2, CheckCircle2, XCircle, PlayCircle, Clock, Copy, Terminal, ArrowDown, Ban } from 'lucide-react';

interface ProgressVisualizerProps {
  status: string; // idle, running, success, failed
  progress: number;
  currentStage: string;
  error: string | null;
  logs: string[];
}

export const ProgressVisualizer: React.FC<ProgressVisualizerProps> = ({
  status,
  progress,
  currentStage,
  error,
  logs,
}) => {
  const terminalRef = useRef<HTMLDivElement>(null);
  const [autoScroll, setAutoScroll] = useState(true);
  const isNearBottomRef = useRef(true);

  // Force auto-scroll when a new run starts
  useEffect(() => {
    if (status === 'running') {
      isNearBottomRef.current = true;
      setAutoScroll(true);
      if (terminalRef.current) {
        terminalRef.current.scrollTop = terminalRef.current.scrollHeight;
      }
    }
  }, [status]);

  // Smart scroll effect on new logs
  useEffect(() => {
    if (isNearBottomRef.current && terminalRef.current) {
      terminalRef.current.scrollTop = terminalRef.current.scrollHeight;
    }
  }, [logs]);

  // Detect user scroll action
  const handleScroll = (e: React.UIEvent<HTMLDivElement>) => {
    const target = e.currentTarget;
    // Check if user is near the bottom within a 45px threshold
    const isNearBottom = target.scrollHeight - target.scrollTop - target.clientHeight < 45;
    isNearBottomRef.current = isNearBottom;
    if (autoScroll !== isNearBottom) {
      setAutoScroll(isNearBottom);
    }
  };

  // Scroll to bottom helper
  const scrollToBottom = () => {
    isNearBottomRef.current = true;
    setAutoScroll(true);
    if (terminalRef.current) {
      terminalRef.current.scrollTop = terminalRef.current.scrollHeight;
    }
  };

  const stages = [
    { name: 'Stage 1 - Liquidity', desc: 'Screening transaksi ramai' },
    { name: 'Stage 2 - Technical', desc: 'Analisis chart, trend & momentum' },
    { name: 'Stage 3A - Stockbit Broker', desc: 'Koleksi broker summary' },
    { name: 'Stage 3B - Bandarmology', desc: 'Skor akumulasi/distribusi' },
    { name: 'Stage 3C - Orderbook', desc: 'Check antrean bid/offer & notasi' },
    { name: 'Stage 4 - Trade Plan', desc: 'Kalkulasi level entry & stoploss' },
    { name: 'Stage Hybrid', desc: 'Menggabungkan Smart Money & Safety flow' },
    { name: 'Stage 5 - Backtest', desc: 'Simulasi trades historis / paper BPJS' },
    { name: 'Stage 6 - AI Report', desc: 'Membuat bukti & ringkasan analis LLM' },
  ];

  // Helper to determine step status
  const getStageStatus = (stageName: string, idx: number) => {
    if (status === 'idle') return 'pending';
    
    // Find index of current stage
    const currentIdx = stages.findIndex((s) => s.name === currentStage);
    
    if (status === 'failed') {
      if (idx === currentIdx) return 'failed';
      if (idx < currentIdx) return 'success';
      return 'pending';
    }

    if (status === 'cancelled') {
      if (idx < currentIdx) return 'success';
      if (idx === currentIdx) return 'cancelled';
      return 'pending';
    }
    
    if (status === 'success') return 'success';
    
    if (idx < currentIdx) return 'success';
    if (idx === currentIdx) return 'running';
    return 'pending';
  };

  const copyLogs = () => {
    navigator.clipboard.writeText(logs.join('\n'));
    alert('Logs copied to clipboard!');
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
      {/* Header Status Card */}
      <div className="glass-card" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderLeft: '4px solid var(--primary)' }}>
        <div>
          <span style={{ fontSize: '0.8rem', textTransform: 'uppercase', color: 'var(--text-secondary)' }}>Status Pipeline</span>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginTop: '4px' }}>
            <h2 style={{ color: 'white', fontSize: '1.5rem' }}>
              {status === 'idle' && 'Siap Dijalankan'}
              {status === 'running' && 'Pipeline Sedang Berjalan'}
              {status === 'success' && 'Pipeline Selesai'}
              {status === 'failed' && 'Pipeline Gagal'}
              {status === 'cancelled' && 'Pipeline Dibatalkan'}
            </h2>
            {status === 'running' && <Loader2 className="animate-spin" color="var(--primary)" size={20} />}
            {status === 'cancelled' && <Ban color="#f59e0b" size={20} />}
          </div>
        </div>

        {status === 'running' && (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', width: '200px' }}>
            <span style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginBottom: '4px' }}>Progres: {Math.round(progress)}%</span>
            <div style={{ width: '100%', height: '8px', background: 'rgba(255,255,255,0.1)', borderRadius: '4px', overflow: 'hidden' }}>
              <div style={{ width: `${progress}%`, height: '100%', background: 'var(--primary-gradient)', transition: 'width 0.4s ease' }} />
            </div>
          </div>
        )}
      </div>

      {/* Progress flow map */}
      <div className="glass-card">
        <h3 style={{ fontSize: '1.1rem', color: 'white', marginBottom: '20px' }}>Alur Proses Pipeline</h3>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '16px' }}>
          {stages.map((stage, idx) => {
            const stepStatus = getStageStatus(stage.name, idx);
            return (
              <div
                key={stage.name}
                className="glass-card"
                style={{
                  padding: '16px',
                  background: stepStatus === 'running' ? 'rgba(99, 102, 241, 0.08)' : stepStatus === 'cancelled' ? 'rgba(245, 158, 11, 0.08)' : 'rgba(255, 255, 255, 0.01)',
                  borderColor: stepStatus === 'running' ? 'var(--primary)' : stepStatus === 'cancelled' ? '#f59e0b' : 'var(--border-glass)',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '12px'
                }}
              >
                <div>
                  {stepStatus === 'pending' && <PlayCircle size={24} color="var(--text-muted)" />}
                  {stepStatus === 'running' && <Loader2 size={24} color="var(--primary)" className="animate-spin pulse-active" style={{ borderRadius: '50%' }} />}
                  {stepStatus === 'success' && <CheckCircle2 size={24} color="var(--color-success)" />}
                  {stepStatus === 'failed' && <XCircle size={24} color="var(--color-danger)" />}
                  {stepStatus === 'cancelled' && <Ban size={24} color="#f59e0b" />}
                </div>

                <div>
                  <h4 style={{ fontSize: '0.9rem', color: stepStatus === 'pending' ? 'var(--text-secondary)' : 'white' }}>
                    {stage.name}
                  </h4>
                  <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>{stage.desc}</p>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Logs Terminal */}
      <div className="glass-card" style={{ padding: '0px', overflow: 'hidden', display: 'flex', flexDirection: 'column', position: 'relative' }}>
        {/* Terminal Header */}
        <div style={{ padding: '12px 20px', background: 'rgba(0,0,0,0.4)', borderBottom: '1px solid var(--border-glass)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--text-secondary)', fontSize: '0.85rem' }}>
            <Terminal size={16} />
            <span style={{ fontFamily: 'var(--font-mono)' }}>Console Output Logs</span>
          </div>

          {logs.length > 0 && (
            <button
              onClick={copyLogs}
              style={{ background: 'none', border: 'none', color: 'var(--text-secondary)', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.8rem' }}
            >
              <Copy size={12} /> Copy logs
            </button>
          )}
        </div>

        {/* Terminal Body */}
        <div
          ref={terminalRef}
          onScroll={handleScroll}
          style={{
            height: '350px',
            background: '#020617',
            padding: '20px',
            overflowY: 'auto',
            fontFamily: 'var(--font-mono)',
            fontSize: '0.8rem',
            lineHeight: '1.6',
            color: '#cbd5e1'
          }}
        >
          {logs.length === 0 ? (
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'var(--text-muted)' }}>
              <Terminal size={40} strokeWidth={1} style={{ marginBottom: '12px' }} />
              <span>Belum ada log yang berjalan. Klik "Jalankan Analisis" untuk memulai pipeline.</span>
            </div>
          ) : (
            logs.map((log, i) => {
              let logColor = '#cbd5e1';
              if (log.includes('Failed') || log.includes('Exception') || log.includes('Error')) {
                logColor = 'var(--color-danger)';
              } else if (log.includes('Completed') || log.includes('Success')) {
                logColor = 'var(--color-success)';
              } else if (log.includes('Warning') || log.includes('Rate limit')) {
                logColor = 'var(--color-warning)';
              } else if (log.includes('[') && log.includes('Stage')) {
                logColor = '#a78bfa'; // Purple for stage headers
              }
              
              return (
                <div key={i} style={{ color: logColor }}>
                  {log}
                </div>
              );
            })
          )}
        </div>

        {/* Floating Scroll to Bottom Button */}
        {!autoScroll && logs.length > 0 && (
          <button
            onClick={scrollToBottom}
            className="btn-primary"
            style={{
              position: 'absolute',
              bottom: '20px',
              right: '24px',
              padding: '8px 16px',
              borderRadius: '20px',
              fontSize: '0.75rem',
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              boxShadow: '0 4px 20px rgba(99, 102, 241, 0.4)',
              border: '1px solid rgba(255,255,255,0.1)',
              zIndex: 5
            }}
          >
            <ArrowDown size={14} /> Scroll ke Bawah
          </button>
        )}
      </div>
    </div>
  );
};
