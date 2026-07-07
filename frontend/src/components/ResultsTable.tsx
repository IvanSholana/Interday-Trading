import React, { useState, useEffect } from 'react';
import { Search, Download, ArrowUpDown, ChevronLeft, ChevronRight, FileSpreadsheet } from 'lucide-react';

interface ResultsTableProps {
  runId: string;
}

export const ResultsTable: React.FC<ResultsTableProps> = ({ runId }) => {
  const [stage, setStage] = useState('stage4');
  const [data, setData] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [limit, setLimit] = useState(20);
  const [search, setSearch] = useState('');
  
  // Sorting
  const [sortBy, setSortBy] = useState<string | null>(null);
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('asc');
  
  // Specific Filters
  const [tradeStatus, setTradeStatus] = useState('');
  const [liquidityBucket, setLiquidityBucket] = useState('');
  const [bandarmologySignal, setBandarmologySignal] = useState('');

  const stagesList = [
    { key: 'stage1', label: 'Stage 1 - Liquidity Screening' },
    { key: 'stage2', label: 'Stage 2 - Technical Context' },
    { key: 'stage3b', label: 'Stage 3B - Bandarmology Score' },
    { key: 'stage3c', label: 'Stage 3C - Orderbook Execution Filter' },
    { key: 'stage4', label: 'Stage 4 - Final Trade Plan' },
    { key: 'hybrid_watchlist', label: 'Stage Hybrid - Combined Watchlist' },
    { key: 'stage5_trades', label: 'Stage 5A - Interday Trades' },
    { key: 'stage5_bpjs_paper', label: 'Stage 5B - BPJS Paper Trades' },
  ];

  const fetchCSVData = async () => {
    if (!runId) return;
    try {
      let url = `/api/run-csv/${runId}/${stage}?page=${page}&limit=${limit}&search=${search}`;
      if (sortBy) {
        url += `&sort_by=${sortBy}&sort_order=${sortOrder}`;
      }
      if (tradeStatus) {
        url += `&trade_status=${tradeStatus}`;
      }
      if (liquidityBucket) {
        url += `&liquidity_bucket=${liquidityBucket}`;
      }
      if (bandarmologySignal) {
        url += `&bandarmology_signal=${bandarmologySignal}`;
      }
      
      const res = await fetch(url);
      const result = await res.json();
      if (result.records) {
        setData(result.records);
        setTotal(result.total);
      } else {
        setData([]);
        setTotal(0);
      }
    } catch (err) {
      console.error(err);
      setData([]);
      setTotal(0);
    }
  };

  useEffect(() => {
    setPage(1); // Reset page on stage change
    fetchCSVData();
  }, [stage, runId, limit, search, sortBy, sortOrder, tradeStatus, liquidityBucket, bandarmologySignal]);

  // Separate trigger for page shifts
  useEffect(() => {
    fetchCSVData();
  }, [page]);

  const handleSort = (column: string) => {
    if (sortBy === column) {
      setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc');
    } else {
      setSortBy(column);
      setSortOrder('asc');
    }
    setPage(1);
  };

  const handleDownloadCSV = async () => {
    if (!runId) return;
    try {
      // Fetch everything without pagination limits, applying active filters and sorting
      let url = `/api/run-csv/${runId}/${stage}?page=1&limit=100000&search=${search}`;
      if (sortBy) {
        url += `&sort_by=${sortBy}&sort_order=${sortOrder}`;
      }
      if (tradeStatus) {
        url += `&trade_status=${tradeStatus}`;
      }
      if (liquidityBucket) {
        url += `&liquidity_bucket=${liquidityBucket}`;
      }
      if (bandarmologySignal) {
        url += `&bandarmology_signal=${bandarmologySignal}`;
      }

      const res = await fetch(url);
      const result = await res.json();
      const records = result.records;
      
      if (!records || records.length === 0) {
        alert('No data to export');
        return;
      }
      
      const headers = Object.keys(records[0]);
      const csvRows = [
        headers.join(','), // Header row
        ...records.map((row: any) =>
          headers
            .map((header) => {
              const val = row[header];
              const valStr = val === null || val === undefined ? '' : '' + val;
              const escaped = valStr.replace(/"/g, '""');
              return `"${escaped}"`;
            })
            .join(',')
        ),
      ];
      
      const csvContent = csvRows.join('\n');
      const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
      const urlObject = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.setAttribute('href', urlObject);
      link.setAttribute('download', `${stage}_run_${runId}.csv`);
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(urlObject);
    } catch (err) {
      console.error(err);
      alert('Error downloading CSV');
    }
  };

  // Cell Renderer for beautiful UI badges
  const renderCellContent = (col: string, val: any) => {
    if (val === null || val === undefined || val === '') return '-';
    
    // Status formatters
    if (col === 'trade_status' || col === 'status') {
      const isVal = val.toString();
      if (isVal === 'VALID_TRADE_PLAN' || isVal === 'ENTRY_READY' || isVal === 'EXECUTION_READY') {
        return <span className="badge badge-success">{isVal}</span>;
      }
      if (isVal.startsWith('REJECT') || isVal.startsWith('SKIP') || isVal === 'AVOID') {
        return <span className="badge badge-danger">{isVal}</span>;
      }
      return <span className="badge badge-warning">{isVal}</span>;
    }

    if (col === 'liquidity_bucket') {
      const b = val.toString();
      if (b.includes('HIGH') || b.includes('GOOD')) return <span className="badge badge-success">{b}</span>;
      if (b.includes('MEDIUM')) return <span className="badge badge-warning">{b}</span>;
      return <span className="badge badge-danger">{b}</span>;
    }

    if (col === 'bandarmology_signal' || col === 'signal') {
      const s = val.toString();
      if (s.includes('STRONG_ACCUM') || s === 'STRONG_ACCUMULATION') {
        return <span className="badge badge-success" style={{ background: '#059669', color: '#fff' }}>{s}</span>;
      }
      if (s.includes('ACCUM') || s === 'MILD_ACCUMULATION') {
        return <span className="badge badge-success">{s}</span>;
      }
      if (s.includes('DIST') || s.includes('STRONG_DISTRIBUTION')) {
        return <span className="badge badge-danger">{s}</span>;
      }
      return <span className="badge badge-neutral">{s}</span>;
    }

    if (col === 'entry_setup' || col === 'technical_context') {
      return <span className="badge badge-info">{val.toString()}</span>;
    }

    // Currency formatters
    const priceCols = ['entry_price', 'stop_loss', 'take_profit_1', 'take_profit_2', 'exit_price', 'capital', 'risk_value', 'position_size_value'];
    if (priceCols.includes(col)) {
      const num = parseFloat(val);
      if (!isNaN(num)) {
        if (num > 10000) {
          // Format as IDR currency
          return 'Rp ' + Math.round(num).toLocaleString('id-ID');
        }
        return num.toLocaleString('id-ID');
      }
    }

    // Percent values
    if (col.endsWith('_pct') || col === 'win_rate' || col === 'return_pct' || col === 'slippage_pct') {
      const num = parseFloat(val);
      if (!isNaN(num)) {
        // If values are ratios e.g. 0.05, format as 5%
        if (Math.abs(num) < 1 && num !== 0) {
          return (num * 100).toFixed(2) + '%';
        }
        return num.toFixed(2) + '%';
      }
    }

    // Format boolean
    if (val === true || val === 'True' || val === '1') {
      return <span style={{ color: 'var(--color-success)', fontWeight: 600 }}>✓</span>;
    }
    if (val === false || val === 'False' || val === '0') {
      return <span style={{ color: 'var(--text-muted)' }}>-</span>;
    }

    return val.toString();
  };

  const columns = data.length > 0 ? Object.keys(data[0]) : [];
  const totalPages = Math.ceil(total / limit);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      {/* Search & Export Header bar */}
      <div className="glass-card" style={{ display: 'flex', flexWrap: 'wrap', gap: '16px', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', gap: '12px', alignItems: 'center', flex: 1, minWidth: '300px' }}>
          <select
            className="form-select"
            style={{ width: '260px' }}
            value={stage}
            onChange={(e) => {
              setStage(e.target.value);
              setSortBy(null);
              setTradeStatus('');
              setLiquidityBucket('');
              setBandarmologySignal('');
            }}
          >
            {stagesList.map((s) => (
              <option key={s.key} value={s.key}>
                {s.label}
              </option>
            ))}
          </select>

          <div style={{ position: 'relative', flex: 1 }}>
            <Search size={16} style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)' }} />
            <input
              type="text"
              className="form-input"
              style={{ paddingLeft: '36px' }}
              placeholder="Cari kode saham atau status..."
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setPage(1);
              }}
            />
          </div>
        </div>

        <div style={{ display: 'flex', gap: '12px' }}>
          {/* Quick Filters based on columns */}
          {(stage === 'stage4' || stage === 'hybrid_watchlist') && (
            <select
              className="form-select"
              style={{ width: '160px' }}
              value={tradeStatus}
              onChange={(e) => {
                setTradeStatus(e.target.value);
                setPage(1);
              }}
            >
              <option value="">Semua Status</option>
              <option value="VALID_TRADE_PLAN">VALID_TRADE_PLAN</option>
              <option value="REJECT_HIGH_RISK">REJECT_HIGH_RISK</option>
              <option value="REJECT_NO_SETUP">REJECT_NO_SETUP</option>
              <option value="WAIT_PRICE_GAP">WAIT_PRICE_GAP</option>
              <option value="EXECUTION_READY">EXECUTION_READY</option>
            </select>
          )}

          {(stage === 'stage1' || stage === 'stage2') && (
            <select
              className="form-select"
              style={{ width: '160px' }}
              value={liquidityBucket}
              onChange={(e) => {
                setLiquidityBucket(e.target.value);
                setPage(1);
              }}
            >
              <option value="">Semua Likuiditas</option>
              <option value="HIGH_LIQUIDITY">HIGH_LIQUIDITY</option>
              <option value="GOOD_LIQUIDITY">GOOD_LIQUIDITY</option>
              <option value="MEDIUM_LIQUIDITY">MEDIUM_LIQUIDITY</option>
              <option value="LOW_LIQUIDITY">LOW_LIQUIDITY</option>
              <option value="ILLIQUID">ILLIQUID</option>
            </select>
          )}

          {(stage === 'stage3b' || stage === 'stage4' || stage === 'hybrid_watchlist') && (
            <select
              className="form-select"
              style={{ width: '180px' }}
              value={bandarmologySignal}
              onChange={(e) => {
                setBandarmologySignal(e.target.value);
                setPage(1);
              }}
            >
              <option value="">Semua Bandar Flow</option>
              <option value="STRONG_ACCUMULATION">STRONG_ACCUMULATION</option>
              <option value="MILD_ACCUMULATION">MILD_ACCUMULATION</option>
              <option value="NEUTRAL_FLOW">NEUTRAL_FLOW</option>
              <option value="MILD_DISTRIBUTION">MILD_DISTRIBUTION</option>
              <option value="STRONG_DISTRIBUTION">STRONG_DISTRIBUTION</option>
              <option value="NO_BROKER_DATA">NO_BROKER_DATA</option>
            </select>
          )}

          <button onClick={handleDownloadCSV} className="btn-secondary" style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
            <Download size={16} /> Export CSV
          </button>
        </div>
      </div>

      {/* Table grid */}
      <div className="glass-card" style={{ padding: '0px', overflowX: 'auto', border: '1px solid var(--border-glass)' }}>
        {data.length === 0 ? (
          <div style={{ padding: '60px', textAlign: 'center', color: 'var(--text-secondary)' }}>
            <FileSpreadsheet size={48} strokeWidth={1} style={{ margin: '0 auto 16px', color: 'var(--text-muted)' }} />
            <p>Tidak ada baris data yang ditemukan untuk filter/tahap ini.</p>
          </div>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', minWidth: '800px' }}>
            <thead>
              <tr style={{ background: 'rgba(0,0,0,0.35)', borderBottom: '1px solid var(--border-glass)' }}>
                {columns.map((col) => (
                  <th
                    key={col}
                    onClick={() => handleSort(col)}
                    style={{
                      padding: '16px',
                      fontSize: '0.85rem',
                      fontFamily: 'var(--font-header)',
                      fontWeight: 600,
                      color: 'white',
                      cursor: 'pointer',
                      userSelect: 'none',
                      whiteSpace: 'nowrap'
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                      {col.replace(/_/g, ' ')}
                      <ArrowUpDown size={12} color="var(--text-muted)" />
                    </div>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.map((row, rIdx) => (
                <tr
                  key={rIdx}
                  style={{
                    borderBottom: '1px solid var(--border-glass)',
                    background: rIdx % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.01)',
                  }}
                  className="table-row-hover"
                >
                  {columns.map((col) => (
                    <td
                      key={col}
                      style={{
                        padding: '14px 16px',
                        fontSize: '0.85rem',
                        color: col === 'ticker' ? 'white' : 'var(--text-secondary)',
                        fontWeight: col === 'ticker' ? 700 : 400,
                        whiteSpace: 'nowrap'
                      }}
                    >
                      {renderCellContent(col, row[col])}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Pagination controls */}
      {totalPages > 1 && (
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
            Menampilkan {data.length} dari {total} data
          </span>

          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            {/* Limit Selector */}
            <select
              className="form-select"
              style={{ width: '80px', padding: '6px 10px' }}
              value={limit}
              onChange={(e) => {
                setLimit(parseInt(e.target.value));
                setPage(1);
              }}
            >
              <option value={10}>10</option>
              <option value={20}>20</option>
              <option value={50}>50</option>
              <option value={100}>100</option>
            </select>

            <button
              className="btn-secondary"
              style={{ padding: '8px 12px' }}
              disabled={page === 1}
              onClick={() => setPage(page - 1)}
            >
              <ChevronLeft size={16} />
            </button>

            <span style={{ fontSize: '0.85rem', color: 'white', padding: '0 12px' }}>
              Halaman {page} dari {totalPages}
            </span>

            <button
              className="btn-secondary"
              style={{ padding: '8px 12px' }}
              disabled={page === totalPages}
              onClick={() => setPage(page + 1)}
            >
              <ChevronRight size={16} />
            </button>
          </div>
        </div>
      )}
    </div>
  );
};
