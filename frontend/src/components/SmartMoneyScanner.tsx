import React, { useState, useEffect } from 'react';
import { Coins, Play, RefreshCw, AlertCircle, TrendingUp, Info } from 'lucide-react';

interface Commodity {
  symbol: string;
  name: string;
  last: number;
  percent: number;
}

interface BandarCandidate {
  ticker: string;
  net_buy_value: number;
  net_buy_lot: number;
  frequency: number;
  corp_action_active: boolean;
  special_notations: string;
  avg_price: number;
}

export const SmartMoneyScanner: React.FC = () => {
  const [commodities, setCommodities] = useState<Commodity[]>([]);
  const [candidates, setCandidates] = useState<BandarCandidate[]>([]);
  const [loadingCommodities, setLoadingCommodities] = useState(true);
  const [loadingScan, setLoadingScan] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Scan config state
  const [investorType, setInvestorType] = useState('INVESTOR_TYPE_FOREIGN');
  const [period, setPeriod] = useState('RT_PERIOD_LAST_7_DAYS');
  const [forceRefresh, setForceRefresh] = useState(false);

  const fetchCommodities = async () => {
    setLoadingCommodities(true);
    try {
      const res = await fetch('/api/commodities');
      if (res.ok) {
        const data = await res.json();
        setCommodities(data);
      }
    } catch (err) {
      console.error('Error fetching commodities:', err);
    } finally {
      setLoadingCommodities(false);
    }
  };

  const fetchScanResults = async (runScan = false) => {
    setLoadingScan(true);
    setError(null);
    try {
      let res;
      if (runScan) {
        res = await fetch('/api/bandar-scan/run', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            investor_type: investorType,
            period: period,
            force_refresh: forceRefresh,
          }),
        });
      } else {
        res = await fetch('/api/bandar-scan');
      }

      if (res.ok) {
        const data = await res.json();
        setCandidates(data);
      } else {
        const errData = await res.json();
        setError(errData.detail || 'Failed to retrieve scan results.');
      }
    } catch (err) {
      console.error(err);
      setError('Connection error while fetching scan results.');
    } finally {
      setLoadingScan(false);
    }
  };

  useEffect(() => {
    fetchCommodities();
    fetchScanResults(false);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const handleRunScan = () => {
    fetchScanResults(true);
  };

  const formatIDR = (val: number) => {
    if (val >= 1e12) {
      return `Rp ${(val / 1e12).toFixed(2)} T`;
    }
    if (val >= 1e9) {
      return `Rp ${(val / 1e9).toFixed(2)} M`;
    }
    if (val >= 1e6) {
      return `Rp ${(val / 1e6).toFixed(2)} Jt`;
    }
    return `Rp ${val.toLocaleString('id-ID')}`;
  };

  const getCommBadgeColor = (pct: number) => {
    if (pct > 0) return 'badge-success';
    if (pct < -1.5) return 'badge-danger';
    return 'badge-warning';
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
      
      {/* 1. Commodities Prices Widget */}
      <div className="glass-card" style={{ padding: '24px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <div style={{ padding: '8px', background: 'var(--color-info-bg)', borderRadius: '8px', color: 'var(--color-info)' }}>
              <Coins size={20} />
            </div>
            <div>
              <h3 style={{ fontSize: '1.1rem', color: 'white', margin: 0 }}>Harga Komoditas Global (Real-Time)</h3>
              <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', margin: '4px 0 0' }}>Sentimen makro penentu pergerakan sektor batu bara, emas, nikel, minyak, & CPO</p>
            </div>
          </div>
          <button 
            onClick={fetchCommodities} 
            className="btn-secondary" 
            style={{ padding: '8px 12px', display: 'flex', gap: '6px', alignItems: 'center', fontSize: '0.8rem' }}
            disabled={loadingCommodities}
          >
            <RefreshCw size={14} className={loadingCommodities ? 'animate-spin' : ''} />
            Refresh Komoditas
          </button>
        </div>

        {loadingCommodities ? (
          <div style={{ color: 'var(--text-secondary)', textAlign: 'center', padding: '20px' }}>
            Loading global commodity prices...
          </div>
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '14px' }}>
            {commodities.map((c) => (
              <div 
                key={c.symbol} 
                className="glass-card" 
                style={{ 
                  padding: '16px', 
                  background: 'rgba(255,255,255,0.02)', 
                  borderLeft: `3px solid ${c.percent > 0 ? 'var(--color-success)' : c.percent < -1.5 ? 'var(--color-danger)' : 'var(--color-warning)'}` 
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                  <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>{c.symbol}</span>
                  <span className={`badge ${getCommBadgeColor(c.percent)}`} style={{ fontSize: '0.7rem', padding: '2px 6px' }}>
                    {c.percent > 0 ? '+' : ''}{c.percent.toFixed(2)}%
                  </span>
                </div>
                <div style={{ color: 'white', fontWeight: 700, fontSize: '1.05rem', marginTop: '6px' }}>
                  {c.last.toLocaleString('id-ID', { maximumFractionDigits: 2 })}
                </div>
                <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', marginTop: '2px' }}>
                  {c.name}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* 2. Smart Money Scanner Configuration & Action */}
      <div className="glass-card" style={{ padding: '24px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: '16px', flexWrap: 'wrap', alignItems: 'center', marginBottom: '20px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <div style={{ padding: '8px', background: 'var(--color-success-bg)', borderRadius: '8px', color: 'var(--color-success)' }}>
              <TrendingUp size={20} />
            </div>
            <div>
              <h3 style={{ fontSize: '1.1rem', color: 'white', margin: 0 }}>Smart Money Flow Scanner (Bandar Tracker)</h3>
              <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', margin: '4px 0 0' }}>Bottom-Up scanner mendeteksi saham terakumulasi broker asing/lokal di seluruh bursa</p>
            </div>
          </div>

          <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap', alignItems: 'center' }}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
              <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Investor Type</span>
              <select 
                className="form-select" 
                style={{ padding: '6px 10px', fontSize: '0.8rem', width: '150px' }}
                value={investorType}
                onChange={(e) => setInvestorType(e.target.value)}
              >
                <option value="INVESTOR_TYPE_FOREIGN">Foreign (Asing)</option>
                <option value="INVESTOR_TYPE_DOMESTIC">Domestic (Lokal)</option>
              </select>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
              <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Period</span>
              <select 
                className="form-select" 
                style={{ padding: '6px 10px', fontSize: '0.8rem', width: '130px' }}
                value={period}
                onChange={(e) => setPeriod(e.target.value)}
              >
                <option value="RT_PERIOD_LAST_1_DAY">1 Hari</option>
                <option value="RT_PERIOD_LAST_3_DAYS">3 Hari</option>
                <option value="RT_PERIOD_LAST_7_DAYS">7 Hari</option>
              </select>
            </div>

            <label style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '0.8rem', color: 'var(--text-secondary)', cursor: 'pointer', marginTop: '16px' }}>
              <input 
                type="checkbox" 
                checked={forceRefresh}
                onChange={(e) => setForceRefresh(e.target.checked)}
              />
              Bypass Cache
            </label>

            <button 
              onClick={handleRunScan} 
              className="btn-primary" 
              style={{ padding: '10px 18px', display: 'flex', gap: '8px', alignItems: 'center', fontSize: '0.85rem', marginTop: '16px' }}
              disabled={loadingScan}
            >
              <Play size={14} />
              {loadingScan ? 'Scanning...' : 'Mulai Scan Bandar'}
            </button>
          </div>
        </div>

        {error && (
          <div className="glass-card" style={{ borderColor: 'var(--color-danger-border)', background: 'rgba(239, 68, 68, 0.05)', padding: '12px 16px', marginBottom: '20px', display: 'flex', gap: '10px', alignItems: 'center', color: 'var(--color-danger)' }}>
            <AlertCircle size={18} />
            <span style={{ fontSize: '0.85rem' }}>{error}</span>
          </div>
        )}

        {/* 3. Scan Results Table */}
        {loadingScan ? (
          <div style={{ textAlign: 'center', padding: '60px', color: 'var(--text-secondary)' }}>
            <div className="animate-spin" style={{ display: 'inline-block', width: '30px', height: '30px', border: '3px solid rgba(255,255,255,0.1)', borderTopColor: 'var(--primary)', borderRadius: '50%', marginBottom: '16px' }} />
            <p style={{ fontSize: '0.9rem' }}>Memindai akumulasi broker di server Stockbit... Mohon tunggu.</p>
          </div>
        ) : candidates.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '40px', color: 'var(--text-secondary)', border: '1px dashed var(--border-glass)', borderRadius: '8px' }}>
            <Info size={32} style={{ color: 'var(--text-muted)', marginBottom: '12px' }} />
            <h4 style={{ color: 'white', margin: '0 0 6px' }}>Belum Ada Hasil Scan</h4>
            <p style={{ fontSize: '0.8rem', margin: 0 }}>Klik tombol "Mulai Scan Bandar" untuk memulai pencarian dana asing/lokal.</p>
          </div>
        ) : (
          <div style={{ overflowX: 'auto', border: '1px solid var(--border-glass)', borderRadius: '8px' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left' }}>
              <thead>
                <tr style={{ background: 'rgba(0,0,0,0.3)', borderBottom: '1px solid var(--border-glass)', color: 'white', fontSize: '0.8rem' }}>
                  <th style={{ padding: '12px 16px' }}>No</th>
                  <th style={{ padding: '12px 16px' }}>Ticker</th>
                  <th style={{ padding: '12px 16px' }}>Net Buy Value (IDR)</th>
                  <th style={{ padding: '12px 16px' }}>Net Buy Lot</th>
                  <th style={{ padding: '12px 16px' }}>Avg Price</th>
                  <th style={{ padding: '12px 16px' }}>Frequency</th>
                  <th style={{ padding: '12px 16px' }}>Aksi Korporasi</th>
                  <th style={{ padding: '12px 16px' }}>Notasi Khusus</th>
                </tr>
              </thead>
              <tbody>
                {candidates.map((item, index) => (
                  <tr 
                    key={item.ticker} 
                    style={{ 
                      borderBottom: '1px solid var(--border-glass)', 
                      background: index % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.01)',
                      fontSize: '0.85rem'
                    }}
                  >
                    <td style={{ padding: '12px 16px', color: 'var(--text-muted)' }}>{index + 1}</td>
                    <td style={{ padding: '12px 16px', color: 'white', fontWeight: 700 }}>{item.ticker}</td>
                    <td style={{ padding: '12px 16px', color: 'var(--primary)', fontWeight: 600 }}>{formatIDR(item.net_buy_value)}</td>
                    <td style={{ padding: '12px 16px', color: 'var(--text-secondary)' }}>{Math.round(item.net_buy_lot).toLocaleString('id-ID')} Lot</td>
                    <td style={{ padding: '12px 16px', color: 'var(--text-secondary)' }}>Rp {Math.round(item.avg_price).toLocaleString('id-ID')}</td>
                    <td style={{ padding: '12px 16px', color: 'var(--text-secondary)' }}>{item.frequency.toLocaleString('id-ID')}</td>
                    <td style={{ padding: '12px 16px' }}>
                      {item.corp_action_active ? (
                        <span className="badge badge-danger" style={{ fontSize: '0.7rem' }}>ADA</span>
                      ) : (
                        <span className="badge badge-neutral" style={{ fontSize: '0.7rem' }}>TIDAK</span>
                      )}
                    </td>
                    <td style={{ padding: '12px 16px' }}>
                      {item.special_notations ? (
                        <span className="badge badge-warning" style={{ fontSize: '0.7rem' }}>{item.special_notations}</span>
                      ) : (
                        <span style={{ color: 'var(--text-muted)' }}>-</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

    </div>
  );
};
