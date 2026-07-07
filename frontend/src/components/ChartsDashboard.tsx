import React, { useState, useEffect } from 'react';
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  BarChart,
  Bar,
  ReferenceLine,
  Legend
} from 'recharts';
import { TrendingUp, Award, AlertTriangle, Activity, Percent, Landmark } from 'lucide-react';

interface ChartsDashboardProps {
  runId: string;
}

export const ChartsDashboard: React.FC<ChartsDashboardProps> = ({ runId }) => {
  const [metrics, setMetrics] = useState<any>(null);
  const [equityData, setEquityData] = useState<any[]>([]);
  const [trades, setTrades] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchAnalytics = async () => {
    if (!runId) return;
    setLoading(true);
    try {
      // 1. Fetch metrics from stage5_metrics (or check if it is BPJS paper summary)
      // Since it is JSON, we can fetch it via /api/run-csv/run_id/stage5_metrics?limit=1
      // but since our api/run-csv returns CSV records as JSON, wait, does it read JSON?
      // Ah! In our server.py:
      // resolve_artifact_path returns the json file path for stage5_metrics, and then server.py pd.read_csv(path) will fail or read it as a strange single row.
      // Wait, is there a JSON endpoint?
      // Ah! In server.py, we have `GET /api/run-details/{run_id}` which returns the `summary` from `summarize_run(run_dir)`.
      // `summarize_run` reads `stage5_metrics` and puts it in the dictionary!
      // Let's check `summarize_run` in server.py:
      // "metrics": metrics.get("win_rate"), "closed_trades", etc.
      // Wait, we can load the metrics JSON by reading the detail, or we can add a tiny logic in our component,
      // or we can fetch stage5_metrics.
      // Wait! Let's see: in server.py, resolve_artifact_path(root, "stage5_metrics") is a JSON file.
      // Let's verify what details we get from `GET /api/run-details/{run_id}`.
      // It returns:
      // {
      //   "run_id": "...",
      //   "summary": {
      //      "run": "...",
      //      "stage1_rows": 20,
      //      "liquid_rows": 10,
      //      "valid_trade_plans": 2,
      //      "closed_trades": 5,
      //      "win_rate": 0.6,
      //      "report_available": true
      //   }
      // }
      // This is some summary.
      // Let's see if we can fetch stage5_equity as a CSV.
      // Yes, /api/run-csv/{run_id}/stage5_equity returns the equity curve rows!
      // And /api/run-csv/{run_id}/stage5_trades returns the trade log rows!
      // This is perfect! We can calculate all metrics directly from `stage5_trades` and plot the equity curve from `stage5_equity`.
      // This is incredibly robust, as we don't have to rely on the json parsing! We can recalculate stats in Javascript or fall back if the file doesn't exist.
      
      // Load equity curve
      const equityRes = await fetch(`/api/run-csv/${runId}/stage5_equity?limit=1000`);
      if (equityRes.ok) {
        const eqResult = await equityRes.json();
        setEquityData(eqResult.records || []);
      }
      
      // Load trades log
      const tradesRes = await fetch(`/api/run-csv/${runId}/stage5_trades?limit=1000`);
      if (tradesRes.ok) {
        const trResult = await tradesRes.json();
        const trRecords = trResult.records || [];
        setTrades(trRecords);
        
        // Recalculate metrics from trades if needed
        if (trRecords.length > 0) {
          const wins = trRecords.filter((t: any) => parseFloat(t.return_pct || t.net_profit_pct || 0) > 0);
          const losses = trRecords.filter((t: any) => parseFloat(t.return_pct || t.net_profit_pct || 0) <= 0);
          const totalProfit = trRecords.reduce((acc: number, t: any) => acc + parseFloat(t.net_profit || 0), 0);
          
          setMetrics({
            total_trades: trRecords.length,
            wins_count: wins.length,
            losses_count: losses.length,
            win_rate: wins.length / trRecords.length,
            net_profit: totalProfit,
            avg_return: trRecords.reduce((acc: number, t: any) => acc + parseFloat(t.return_pct || t.net_profit_pct || 0), 0) / trRecords.length
          });
        }
      }
    } catch (err) {
      console.error('Error fetching chart data:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAnalytics();
  }, [runId]); // eslint-disable-line react-hooks/exhaustive-deps

  if (loading) {
    return (
      <div className="glass-card" style={{ padding: '60px', textAlign: 'center', color: 'var(--text-secondary)' }}>
        <div className="animate-spin" style={{ display: 'inline-block', width: '30px', height: '30px', border: '3px solid rgba(255,255,255,0.1)', borderTopColor: 'var(--primary)', borderRadius: '50%', marginBottom: '16px' }} />
        <p>Memuat data grafik backtest...</p>
      </div>
    );
  }

  // Format IDR Currency
  const formatIDR = (val: number) => {
    return 'Rp ' + Math.round(val).toLocaleString('id-ID');
  };

  // Pie chart data
  const pieData = metrics ? [
    { name: 'Wins', value: metrics.wins_count, color: 'var(--color-success)' },
    { name: 'Losses', value: metrics.losses_count, color: 'var(--color-danger)' },
  ] : [];

  // Prepare Bar chart data mapping profit of individual trades
  const tradeBarData = trades.map((t, idx) => ({
    ticker: t.ticker || `Trade ${idx + 1}`,
    profit: parseFloat(t.net_profit || 0),
    profit_pct: parseFloat(t.return_pct || t.net_profit_pct || 0) * 100
  })).slice(0, 20); // show top 20 for readability

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
      
      {/* Metric Cards Grid */}
      {metrics ? (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '16px' }}>
          
          <div className="glass-card" style={{ display: 'flex', alignItems: 'center', gap: '16px', borderLeft: '4px solid var(--primary)' }}>
            <div style={{ padding: '10px', background: 'var(--primary-glow)', borderRadius: '8px' }}>
              <Landmark size={20} color="var(--primary)" />
            </div>
            <div>
              <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>Total Profit/Loss</span>
              <h3 style={{ fontSize: '1.25rem', color: metrics.net_profit >= 0 ? 'var(--color-success)' : 'var(--color-danger)', marginTop: '2px' }}>
                {formatIDR(metrics.net_profit)}
              </h3>
            </div>
          </div>

          <div className="glass-card" style={{ display: 'flex', alignItems: 'center', gap: '16px', borderLeft: '4px solid var(--color-success)' }}>
            <div style={{ padding: '10px', background: 'var(--color-success-bg)', borderRadius: '8px' }}>
              <Award size={20} color="var(--color-success)" />
            </div>
            <div>
              <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>Win Rate</span>
              <h3 style={{ fontSize: '1.25rem', color: 'white', marginTop: '2px' }}>
                {(metrics.win_rate * 100).toFixed(1)}%
              </h3>
            </div>
          </div>

          <div className="glass-card" style={{ display: 'flex', alignItems: 'center', gap: '16px', borderLeft: '4px solid var(--color-info)' }}>
            <div style={{ padding: '10px', background: 'var(--color-info-bg)', borderRadius: '8px' }}>
              <Activity size={20} color="var(--color-info)" />
            </div>
            <div>
              <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>Total Trades</span>
              <h3 style={{ fontSize: '1.25rem', color: 'white', marginTop: '2px' }}>
                {metrics.total_trades}
              </h3>
            </div>
          </div>

          <div className="glass-card" style={{ display: 'flex', alignItems: 'center', gap: '16px', borderLeft: '4px solid var(--color-warning)' }}>
            <div style={{ padding: '10px', background: 'var(--color-warning-bg)', borderRadius: '8px' }}>
              <Percent size={20} color="var(--color-warning)" />
            </div>
            <div>
              <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>Rata-rata Return</span>
              <h3 style={{ fontSize: '1.25rem', color: metrics.avg_return >= 0 ? 'var(--color-success)' : 'var(--color-danger)', marginTop: '2px' }}>
                {(metrics.avg_return * 100).toFixed(2)}%
              </h3>
            </div>
          </div>

        </div>
      ) : (
        <div className="glass-card" style={{ textAlign: 'center', padding: '30px', color: 'var(--text-secondary)' }}>
          Belum ada data transaksi backtest tersedia. Pastikan Stage 5 telah dijalankan dengan hasil valid trade plan.
        </div>
      )}

      {/* Row: Equity Curve and Win/Loss Distribution */}
      <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: '24px', flexWrap: 'wrap' }}>
        
        {/* Equity Curve Area Chart */}
        <div className="glass-card" style={{ minHeight: '380px', display: 'flex', flexDirection: 'column' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '20px' }}>
            <TrendingUp size={18} color="var(--primary)" />
            <h3 style={{ fontSize: '1.1rem', color: 'white' }}>Kurva Ekuitas Modal (Equity Curve)</h3>
          </div>
          
          <div style={{ flex: 1, width: '100%', minHeight: '280px' }}>
            {equityData.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={equityData} margin={{ top: 10, right: 10, left: 10, bottom: 0 }}>
                  <defs>
                    <linearGradient id="colorEquity" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="var(--primary)" stopOpacity={0.4}/>
                      <stop offset="95%" stopColor="var(--primary)" stopOpacity={0}/>
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                  <XAxis
                    dataKey="date"
                    stroke="var(--text-muted)"
                    fontSize={11}
                    tickLine={false}
                  />
                  <YAxis
                    stroke="var(--text-muted)"
                    fontSize={11}
                    tickLine={false}
                    tickFormatter={(v) => `Rp ${(v/1000000).toFixed(1)}M`}
                  />
                  <Tooltip
                    contentStyle={{ background: '#0b0f19', border: '1px solid var(--border-glass)', borderRadius: '8px' }}
                    labelStyle={{ color: 'white', fontWeight: 600 }}
                    formatter={(val: any) => [formatIDR(val), 'Ekuitas']}
                  />
                  <Area
                    type="monotone"
                    dataKey="capital"
                    stroke="var(--primary)"
                    strokeWidth={2}
                    fillOpacity={1}
                    fill="url(#colorEquity)"
                  />
                </AreaChart>
              </ResponsiveContainer>
            ) : (
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'var(--text-muted)' }}>
                Tidak ada data histori ekuitas. Silakan jalankan Stage 5.
              </div>
            )}
          </div>
        </div>

        {/* Win/Loss Pie chart */}
        <div className="glass-card" style={{ display: 'flex', flexDirection: 'column' }}>
          <h3 style={{ fontSize: '1.1rem', color: 'white', marginBottom: '20px' }}>Distribusi Profit/Loss</h3>
          
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}>
            {pieData.length > 0 ? (
              <>
                <div style={{ width: '100%', height: '180px' }}>
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie
                        data={pieData}
                        cx="50%"
                        cy="50%"
                        innerRadius={55}
                        outerRadius={75}
                        paddingAngle={5}
                        dataKey="value"
                      >
                        {pieData.map((entry, index) => (
                          <Cell key={`cell-${index}`} fill={entry.color} />
                        ))}
                      </Pie>
                      <Tooltip formatter={(val) => [`${val} Trades`, 'Jumlah']} />
                    </PieChart>
                  </ResponsiveContainer>
                </div>
                
                {/* Custom Legends */}
                <div style={{ display: 'flex', gap: '20px', marginTop: '16px' }}>
                  {pieData.map((entry, idx) => (
                    <div key={idx} style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <div style={{ width: '12px', height: '12px', borderRadius: '50%', background: entry.color }} />
                      <span style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                        {entry.name}: {entry.value} ({((entry.value / metrics.total_trades) * 100).toFixed(0)}%)
                      </span>
                    </div>
                  ))}
                </div>
              </>
            ) : (
              <div style={{ color: 'var(--text-muted)' }}>
                Belum ada statistik profit/loss.
              </div>
            )}
          </div>
        </div>

      </div>

      {/* Ticker outcomes bar chart */}
      <div className="glass-card" style={{ minHeight: '350px' }}>
        <h3 style={{ fontSize: '1.1rem', color: 'white', marginBottom: '20px' }}>Hasil Profit/Loss per Ticker Saham (Top 20)</h3>
        <div style={{ width: '100%', height: '250px' }}>
          {tradeBarData.length > 0 ? (
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={tradeBarData} margin={{ top: 10, bottom: 10 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                <XAxis dataKey="ticker" stroke="var(--text-muted)" fontSize={11} tickLine={false} />
                <YAxis
                  stroke="var(--text-muted)"
                  fontSize={11}
                  tickLine={false}
                  tickFormatter={(v) => `${v}%`}
                />
                <Tooltip
                  contentStyle={{ background: '#0b0f19', border: '1px solid var(--border-glass)', borderRadius: '8px' }}
                  labelStyle={{ color: 'white', fontWeight: 600 }}
                  formatter={(val: any) => [`${val.toFixed(2)}%`, 'Return']}
                />
                <ReferenceLine y={0} stroke="rgba(255,255,255,0.2)" />
                <Bar dataKey="profit_pct" radius={[4, 4, 0, 0]}>
                  {tradeBarData.map((entry, index) => (
                    <Cell
                      key={`cell-${index}`}
                      fill={entry.profit_pct >= 0 ? 'var(--color-success)' : 'var(--color-danger)'}
                    />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'var(--text-muted)' }}>
              Tidak ada data trades per ticker.
            </div>
          )}
        </div>
      </div>

    </div>
  );
};
