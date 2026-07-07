import React, { useState, useEffect } from 'react';
import { FileText, Cpu, AlertCircle, Copy, Check } from 'lucide-react';

interface ReportViewerProps {
  runId: string;
}

export const ReportViewer: React.FC<ReportViewerProps> = ({ runId }) => {
  const [report, setReport] = useState<string>('');
  const [loading, setLoading] = useState(true);
  const [copied, setCopied] = useState(false);

  const fetchReport = async () => {
    if (!runId) return;
    setLoading(true);
    try {
      const res = await fetch(`/api/report/${runId}`);
      if (res.ok) {
        const data = await res.json();
        setReport(data.report || '');
      } else {
        setReport('');
      }
    } catch (err) {
      console.error(err);
      setReport('');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchReport();
  }, [runId]); // eslint-disable-line react-hooks/exhaustive-deps

  const copyToClipboard = () => {
    navigator.clipboard.writeText(report);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  // Simple and robust Markdown parser for standard report elements
  const parseMarkdown = (md: string) => {
    if (!md) return null;

    const lines = md.split('\n');
    const elements: React.ReactNode[] = [];
    let key = 0;
    
    // For parsing tables
    let inTable = false;
    let tableHeaders: string[] = [];
    let tableRows: string[][] = [];

    const flushTable = () => {
      if (tableRows.length > 0 || tableHeaders.length > 0) {
        elements.push(
          <div key={`table-${key++}`} className="glass-card" style={{ padding: '0px', overflowX: 'auto', margin: '20px 0', border: '1px solid var(--border-glass)' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left' }}>
              <thead>
                <tr style={{ background: 'rgba(0,0,0,0.3)', borderBottom: '1px solid var(--border-glass)' }}>
                  {tableHeaders.map((h, i) => (
                    <th key={i} style={{ padding: '12px 16px', fontSize: '0.85rem', color: 'white' }}>{h.trim()}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {tableRows.map((row, rIdx) => (
                  <tr key={rIdx} style={{ borderBottom: '1px solid var(--border-glass)', background: rIdx % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.01)' }}>
                    {row.map((cell, cIdx) => (
                      <td key={cIdx} style={{ padding: '12px 16px', fontSize: '0.85rem', color: 'var(--text-secondary)' }}>{cell.trim()}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        );
        tableHeaders = [];
        tableRows = [];
        inTable = false;
      }
    };

    for (let i = 0; i < lines.length; i++) {
      const line = lines[i].trim();

      // Check table rows
      if (line.startsWith('|')) {
        inTable = true;
        const cells = line.split('|').slice(1, -1); // remove empty outer cells
        if (line.includes('---')) {
          // Divider row, skip
          continue;
        }
        if (tableHeaders.length === 0) {
          tableHeaders = cells;
        } else {
          tableRows.push(cells);
        }
        continue;
      } else if (inTable) {
        flushTable();
      }

      // Headers
      if (line.startsWith('# ')) {
        elements.push(<h2 key={key++} style={{ fontSize: '1.75rem', color: 'white', margin: '28px 0 16px', borderBottom: '1px solid var(--border-glass)', paddingBottom: '8px' }}>{line.substring(2)}</h2>);
      } else if (line.startsWith('## ')) {
        elements.push(<h3 key={key++} style={{ fontSize: '1.4rem', color: '#a78bfa', margin: '24px 0 12px' }}>{line.substring(3)}</h3>);
      } else if (line.startsWith('### ')) {
        elements.push(<h4 key={key++} style={{ fontSize: '1.15rem', color: 'white', margin: '20px 0 8px' }}>{line.substring(4)}</h4>);
      }
      // Blockquotes / Callouts
      else if (line.startsWith('>')) {
        elements.push(
          <div key={key++} className="glass-card" style={{ borderLeft: '4px solid var(--primary)', background: 'rgba(99, 102, 241, 0.05)', padding: '14px 20px', margin: '16px 0', fontSize: '0.9rem', color: 'var(--text-secondary)', fontStyle: 'italic' }}>
            {line.substring(1).trim()}
          </div>
        );
      }
      // Unordered lists
      else if (line.startsWith('- ') || line.startsWith('* ')) {
        const itemText = line.substring(2);
        elements.push(
          <li key={key++} style={{ marginLeft: '24px', marginBottom: '8px', color: 'var(--text-secondary)', fontSize: '0.9rem' }}>
            {itemText}
          </li>
        );
      }
      // Numbered lists
      else if (/^\d+\.\s/.test(line)) {
        const itemText = line.substring(line.indexOf('.') + 1).trim();
        elements.push(
          <div key={key++} style={{ display: 'flex', gap: '8px', marginLeft: '12px', marginBottom: '8px', color: 'var(--text-secondary)', fontSize: '0.9rem' }}>
            <span style={{ fontWeight: 600, color: 'var(--primary)' }}>{line.substring(0, line.indexOf('.'))}.</span>
            <span>{itemText}</span>
          </div>
        );
      }
      // Empty line
      else if (line === '') {
        elements.push(<div key={key++} style={{ height: '12px' }} />);
      }
      // Paragraph
      else {
        // Parse inline bolding **text**
        const parts = line.split('**');
        const renderedLine = parts.map((part, index) => {
          if (index % 2 === 1) {
            return <strong key={index} style={{ color: 'white', fontWeight: 600 }}>{part}</strong>;
          }
          return part;
        });

        elements.push(<p key={key++} style={{ lineHeight: '1.7', fontSize: '0.9rem', color: 'var(--text-secondary)', marginBottom: '12px' }}>{renderedLine}</p>);
      }
    }

    // Flush remaining table
    if (inTable) flushTable();

    return elements;
  };

  if (loading) {
    return (
      <div className="glass-card" style={{ padding: '60px', textAlign: 'center', color: 'var(--text-secondary)' }}>
        <div className="animate-spin" style={{ display: 'inline-block', width: '30px', height: '30px', border: '3px solid rgba(255,255,255,0.1)', borderTopColor: 'var(--primary)', borderRadius: '50%', marginBottom: '16px' }} />
        <p>Membuka laporan analisa AI...</p>
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      
      {/* Header controls */}
      <div className="glass-card" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderLeft: '4px solid var(--color-neutral)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <div style={{ padding: '8px', background: 'var(--color-neutral-bg)', borderRadius: '8px' }}>
            <Cpu size={18} color="#a78bfa" />
          </div>
          <div>
            <h3 style={{ fontSize: '1.1rem', color: 'white' }}>Laporan Ringkasan AI</h3>
            <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Hasil evaluasi kandidat final IDX oleh analis AI</p>
          </div>
        </div>

        {report && (
          <button onClick={copyToClipboard} className="btn-secondary" style={{ fontSize: '0.8rem', display: 'flex', gap: '6px', alignItems: 'center', padding: '8px 14px' }}>
            {copied ? <Check size={14} color="var(--color-success)" /> : <Copy size={14} />}
            {copied ? 'Copied!' : 'Copy Laporan'}
          </button>
        )}
      </div>

      {/* Main markdown report viewer */}
      {report ? (
        <div className="glass-card" style={{ padding: '32px 40px', background: 'rgba(11, 15, 25, 0.6)', border: '1px solid var(--border-glass)' }}>
          <div style={{ maxWidth: '900px', margin: '0 auto' }}>
            {parseMarkdown(report)}
          </div>
        </div>
      ) : (
        <div className="glass-card" style={{ textAlign: 'center', padding: '60px', color: 'var(--text-secondary)' }}>
          <AlertCircle size={40} strokeWidth={1} style={{ color: 'var(--color-warning)', margin: '0 auto 16px' }} />
          <h4 style={{ color: 'white', marginBottom: '8px', fontSize: '1.1rem' }}>Laporan AI Belum Tersedia</h4>
          <p style={{ fontSize: '0.85rem', maxWidth: '480px', margin: '0 auto 20px', lineHeight: '1.6' }}>
            Laporan AI tidak ditemukan untuk hasil run ini. Hal ini dikarenakan run belum menyelesaikan Stage 6 atau Anda mengaktifkan opsi simulasi (dry-run) tanpa DeepSeek API key.
          </p>
          <div style={{ display: 'flex', justifyContent: 'center', gap: '12px' }}>
            <span className="badge badge-warning">Stage 6 Required</span>
            <span className="badge badge-neutral">DeepSeek Key Required</span>
          </div>
        </div>
      )}

    </div>
  );
};
