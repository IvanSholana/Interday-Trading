import React, { useState, useEffect } from 'react';
import { Clock, Trash2, Play, Save, Plus, AlertCircle, CheckCircle } from 'lucide-react';
import type { ScheduledTask, UniversePreset } from '../types/api';

const AVAILABLE_STAGES = [
  { key: 'stage1', label: 'Stage 1: Liquidity Screen' },
  { key: 'stage2', label: 'Stage 2: Technical Context' },
  { key: 'stage3a', label: 'Stage 3A: Broker Flow' },
  { key: 'stage3b', label: 'Stage 3B: Bandar Score' },
  { key: 'stage3c', label: 'Stage 3C: Orderbook Filter' },
  { key: 'stage4', label: 'Stage 4: Trade Plan' },
  { key: 'hybrid', label: 'Stage Hybrid: Watchlist' },
  { key: 'stage5', label: 'Stage 5: Backtest & Paper' },
  { key: 'stage6', label: 'Stage 6: AI Report' },
];

export const SchedulerPanel: React.FC = () => {
  const [tasks, setTasks] = useState<ScheduledTask[]>([]);
  const [presets, setPresets] = useState<UniversePreset[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // New task form state
  const [name, setName] = useState('');
  const [time, setTime] = useState('09:00');
  const [strategyMode, setStrategyMode] = useState<'interday' | 'bpjs'>('interday');
  const [universeKey, setUniverseKey] = useState('lq45');
  const [capital, setCapital] = useState(1000000);
  const [maxPositionPct, setMaxPositionPct] = useState(0.2);
  const [stages, setStages] = useState<string[]>([
    'stage1', 'stage2', 'stage3a', 'stage3b', 'stage4', 'hybrid'
  ]);

  const fetchSchedule = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch('/api/schedule');
      if (res.ok) {
        const data = await res.json();
        setTasks(data.tasks || []);
      } else {
        setError('Gagal mengambil jadwal konfigurasi.');
      }
    } catch (err) {
      console.error(err);
      setError('Error koneksi ke server.');
    } finally {
      setLoading(false);
    }
  };

  const fetchPresets = async () => {
    try {
      const res = await fetch('/api/presets');
      if (res.ok) {
        const data = await res.json() as UniversePreset[];
        setPresets(data.filter((preset) => preset.key !== 'manual'));
      }
    } catch (err) {
      console.error(err);
    }
  };

  useEffect(() => {
    fetchSchedule();
    fetchPresets();
  }, []);

  const selectedPreset = presets.find((preset) => preset.key === universeKey);

  const tickerFileForPreset = (preset: UniversePreset | undefined) => {
    if (!preset?.filename) return 'data/input/universes/lq45.txt';
    return `data/input/universes/${preset.filename}`;
  };

  const handleSave = async (updatedTasks = tasks) => {
    setError(null);
    setSuccessMsg(null);
    try {
      const res = await fetch('/api/schedule', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tasks: updatedTasks }),
      });
      if (res.ok) {
        setSuccessMsg('Jadwal otomatis berhasil disimpan!');
        setTasks(updatedTasks);
        setTimeout(() => setSuccessMsg(null), 3000);
      } else {
        setError('Gagal menyimpan jadwal ke server.');
      }
    } catch (err) {
      console.error(err);
      setError('Koneksi bermasalah saat menyimpan.');
    }
  };

  const handleAddTask = (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;

    const newTask: ScheduledTask = {
      name: name.trim().replace(/\s+/g, '_').toLowerCase(),
      time,
      strategy_mode: strategyMode,
      universe_key: universeKey,
      tickers_file: tickerFileForPreset(selectedPreset),
      capital,
      max_position_pct: maxPositionPct,
      stages,
    };

    const newTasks = [...tasks, newTask];
    handleSave(newTasks);

    // Reset Form
    setName('');
    setTime('09:00');
  };

  const handleDeleteTask = (index: number) => {
    const newTasks = tasks.filter((_, idx) => idx !== index);
    handleSave(newTasks);
  };

  const handleRunTask = async (task: ScheduledTask) => {
    setError(null);
    setSuccessMsg(null);
    try {
      const res = await fetch('/api/schedule/run-task', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(task),
      });
      if (res.ok) {
        setSuccessMsg(`Tugas '${task.name}' berhasil dijalankan di background!`);
        setTimeout(() => setSuccessMsg(null), 4000);
      } else {
        setError('Gagal menjalankan tugas.');
      }
    } catch (err) {
      console.error(err);
      setError('Koneksi gagal saat memicu tugas.');
    }
  };

  const handleStageToggle = (stageKey: string) => {
    setStages(prev =>
      prev.includes(stageKey)
        ? prev.filter(k => k !== stageKey)
        : [...prev, stageKey]
    );
  };

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 360px', gap: '24px', alignItems: 'start' }}>
      
      {/* 1. Left Column: Scheduled Tasks List */}
      <div className="glass-card" style={{ padding: '24px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '20px' }}>
          <div style={{ padding: '8px', background: 'var(--color-info-bg)', borderRadius: '8px', color: 'var(--color-info)' }}>
            <Clock size={20} />
          </div>
          <div>
            <h3 style={{ fontSize: '1.1rem', color: 'white', margin: 0 }}>Jadwal Eksekusi Otomatis</h3>
            <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', margin: '4px 0 0' }}>Manajemen tugas otomatis harian bursa berdasarkan jam yang ditetapkan</p>
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

        {loading ? (
          <div style={{ color: 'var(--text-secondary)', textAlign: 'center', padding: '40px' }}>
            Memuat konfigurasi jadwal...
          </div>
        ) : tasks.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '60px', color: 'var(--text-secondary)', border: '1px dashed var(--border-glass)', borderRadius: '8px' }}>
            <Clock size={36} style={{ color: 'var(--text-muted)', marginBottom: '12px' }} />
            <h4 style={{ color: 'white', margin: '0 0 6px' }}>Belum Ada Jadwal Terdaftar</h4>
            <p style={{ fontSize: '0.8rem', margin: 0 }}>Gunakan panel di sebelah kanan untuk menambahkan tugas otomatis baru.</p>
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            {tasks.map((task, idx) => (
              <div 
                key={`${task.name}-${idx}`} 
                className="glass-card" 
                style={{ padding: '20px', background: 'rgba(255,255,255,0.015)', borderLeft: '3px solid var(--primary)' }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '12px' }}>
                  <div>
                    <h4 style={{ color: 'white', fontSize: '1.05rem', margin: 0, fontWeight: 700 }}>
                      {task.name.toUpperCase()}
                    </h4>
                    <div style={{ display: 'flex', gap: '12px', alignItems: 'center', marginTop: '6px', fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                      <span className="badge badge-info" style={{ textTransform: 'uppercase' }}>{task.strategy_mode}</span>
                      <span>Jam: <b>{task.time} JKT</b></span>
                      <span>Modal: Rp {task.capital.toLocaleString('id-ID')}</span>
                    </div>
                  </div>
                  
                  <div style={{ display: 'flex', gap: '8px' }}>
                    <button 
                      onClick={() => handleRunTask(task)} 
                      className="btn-secondary" 
                      style={{ padding: '6px 12px', display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.75rem', borderColor: 'var(--primary)' }}
                    >
                      <Play size={12} />
                      Uji Sekarang
                    </button>
                    <button 
                      onClick={() => handleDeleteTask(idx)} 
                      className="btn-secondary" 
                      style={{ padding: '6px', color: 'var(--color-danger)', borderColor: 'rgba(239, 68, 68, 0.2)' }}
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                </div>

                <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                  <div>Preset: <b style={{ color: 'white' }}>{task.universe_key?.toUpperCase() ?? 'CUSTOM'}</b></div>
                  <div style={{ marginTop: '8px', display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
                    {task.stages.map(st => (
                      <span key={st} style={{ background: 'rgba(255,255,255,0.05)', padding: '2px 8px', borderRadius: '4px', fontSize: '0.7rem' }}>
                        {st}
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* 2. Right Column: Add New Scheduled Task Form */}
      <div className="glass-card" style={{ padding: '24px' }}>
        <h3 style={{ fontSize: '1.05rem', color: 'white', margin: '0 0 16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Plus size={18} />
          Tambah Jadwal Baru
        </h3>

        <form onSubmit={handleAddTask} style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>Nama Sesi</span>
            <input 
              type="text" 
              className="form-control" 
              placeholder="e.g. sore_hari" 
              value={name} 
              onChange={e => setName(e.target.value)} 
              required 
            />
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>Waktu Eksekusi</span>
            <input 
              type="time" 
              className="form-control" 
              value={time} 
              onChange={e => setTime(e.target.value)} 
              required 
            />
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>Strategi</span>
            <select 
              className="form-select" 
              value={strategyMode} 
              onChange={e => setStrategyMode(e.target.value as 'interday' | 'bpjs')}
            >
              <option value="interday">Interday Swing</option>
              <option value="bpjs">BPJS (Beli Pagi Jual Siang)</option>
            </select>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>Preset Saham</span>
            <select
              className="form-select"
              value={universeKey}
              onChange={e => setUniverseKey(e.target.value)}
              required
            >
              {presets.map((preset) => (
                <option key={preset.key} value={preset.key}>
                  {preset.label} ({preset.ticker_count} ticker)
                </option>
              ))}
            </select>
            <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>
              Sistem otomatis memakai file universe sesuai preset; tidak perlu isi path manual.
            </span>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>Modal Simulasi (IDR)</span>
            <input 
              type="number" 
              className="form-control" 
              value={capital} 
              onChange={e => setCapital(Number(e.target.value))} 
              required 
            />
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>Maks Posisi Alokasi (0.0 - 1.0)</span>
            <input 
              type="number" 
              step="0.05" 
              className="form-control" 
              value={maxPositionPct} 
              onChange={e => setMaxPositionPct(Number(e.target.value))} 
              required 
            />
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginTop: '4px' }}>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>Tahapan Stage (Stages)</span>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', maxHeight: '180px', overflowY: 'auto', padding: '6px', border: '1px solid var(--border-glass)', borderRadius: '6px' }}>
              {AVAILABLE_STAGES.map(st => (
                <label key={st.key} style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '0.75rem', color: 'var(--text-secondary)', cursor: 'pointer' }}>
                  <input 
                    type="checkbox" 
                    checked={stages.includes(st.key)} 
                    onChange={() => handleStageToggle(st.key)} 
                  />
                  {st.label}
                </label>
              ))}
            </div>
          </div>

          <button 
            type="submit" 
            className="btn-primary" 
            style={{ width: '100%', padding: '10px', display: 'flex', justifyContent: 'center', alignItems: 'center', gap: '8px', fontSize: '0.85rem', marginTop: '10px' }}
          >
            <Save size={16} />
            Simpan Jadwal Baru
          </button>
        </form>
      </div>

    </div>
  );
};
