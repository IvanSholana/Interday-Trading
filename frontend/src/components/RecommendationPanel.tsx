import React from 'react';
import { AlertTriangle, CheckCircle2, ClipboardCheck, Gauge, ShieldAlert, Target } from 'lucide-react';
import type { CandidateRecommendation, RecommendationPack, RunAuditReport, StageArtifactAudit } from '../types/api';

interface RecommendationPanelProps {
  pack: RecommendationPack | null;
  audit: RunAuditReport | null;
  loading: boolean;
  error: string | null;
}

const formatIdr = (value: number | null): string => {
  if (value === null) return '-';
  return `Rp ${Math.round(value).toLocaleString('id-ID')}`;
};

const formatPct = (value: number | null): string => {
  if (value === null) return '-';
  return `${(value * 100).toFixed(2)}%`;
};

const gradeClass = (grade: string): string => {
  if (grade === 'A' || grade === 'B') return 'badge-success';
  if (grade === 'C') return 'badge-warning';
  return 'badge-danger';
};

const readinessClass = (readiness: string): string => {
  if (readiness === 'READY') return 'badge-success';
  if (readiness === 'NEEDS_LIVE_CONFIRMATION') return 'badge-warning';
  if (readiness === 'WATCH_ONLY') return 'badge-info';
  return 'badge-danger';
};

const decisionClass = (decision: string): string => {
  if (decision === 'REVIEW_BUY') return 'badge-success';
  if (decision === 'WAIT_CONFIRMATION') return 'badge-warning';
  if (decision === 'WATCH_ONLY') return 'badge-info';
  return 'badge-danger';
};

const portfolioDecisionClass = (decision: string): string => {
  if (decision === 'WITHIN_BUDGET_REVIEW') return 'badge-success';
  if (decision === 'PICK_PRIMARY_ONLY_OR_REDUCE_SIZE' || decision === 'REDUCE_RISK_BEFORE_EXECUTION') return 'badge-warning';
  return 'badge-danger';
};

const auditStatusClass = (status: string): string => {
  if (status === 'READY_FOR_REVIEW') return 'badge-success';
  if (status === 'NEEDS_MORNING_CONFIRMATION' || status === 'WATCH_ONLY') return 'badge-warning';
  return 'badge-danger';
};

const artifactStatusClass = (status: string): string => {
  if (status === 'OK') return 'badge-success';
  if (status === 'MISSING' || status === 'EMPTY') return 'badge-danger';
  return 'badge-warning';
};

const primaryMetric = (label: string, value: string): React.ReactElement => (
  <div style={{ minWidth: 120 }}>
    <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginBottom: 4 }}>{label}</div>
    <div style={{ fontSize: '0.95rem', color: 'white', fontWeight: 700 }}>{value}</div>
  </div>
);

const ShortlistRow: React.FC<{ item: CandidateRecommendation }> = ({ item }) => (
  <tr style={{ borderTop: '1px solid var(--border-glass)' }}>
    <td style={{ padding: '12px 10px', color: 'white', fontWeight: 700 }}>{item.symbol}</td>
    <td style={{ padding: '12px 10px' }}>
      <span className={`badge ${decisionClass(item.execution_decision)}`}>{item.execution_decision}</span>
    </td>
    <td style={{ padding: '12px 10px' }}>
      <span className={`badge ${gradeClass(item.decision_grade)}`}>{item.decision_grade}</span>
    </td>
    <td style={{ padding: '12px 10px', color: 'var(--text-secondary)' }}>{item.confidence_score.toFixed(1)}</td>
    <td style={{ padding: '12px 10px' }}>
      <span className={`badge ${readinessClass(item.readiness)}`}>{item.readiness}</span>
    </td>
    <td style={{ padding: '12px 10px', color: 'var(--text-secondary)' }}>{formatIdr(item.entry_price)}</td>
    <td style={{ padding: '12px 10px', color: 'var(--text-secondary)' }}>{formatPct(item.target_tp_pct)}</td>
    <td style={{ padding: '12px 10px', color: 'var(--text-secondary)' }}>{formatIdr(item.expected_net_profit)}</td>
    <td style={{ padding: '12px 10px', color: 'var(--text-secondary)' }}>{item.risk_reward_ratio?.toFixed(2) ?? '-'}</td>
    <td style={{ padding: '12px 10px', color: 'var(--text-secondary)' }}>{item.lots}</td>
  </tr>
);

const ArtifactHealth: React.FC<{ artifacts: StageArtifactAudit[] }> = ({ artifacts }) => {
  const importantArtifacts = artifacts.filter((artifact) =>
    ['stage1', 'stage2', 'stage3c', 'stage4', 'hybrid_watchlist', 'stage6_report'].includes(artifact.key),
  );

  return (
    <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 12 }}>
      {importantArtifacts.map((artifact) => (
        <span key={artifact.key} className={`badge ${artifactStatusClass(artifact.status)}`}>
          {artifact.key} {artifact.status}
        </span>
      ))}
    </div>
  );
};

export const RecommendationPanel: React.FC<RecommendationPanelProps> = ({ pack, audit, loading, error }) => {
  if (loading) {
    return (
      <div className="glass-card" style={{ marginBottom: 24 }}>
        <div style={{ color: 'var(--text-secondary)' }}>Memuat recommendation pack...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="glass-card" style={{ marginBottom: 24, borderColor: 'var(--color-danger-border)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, color: 'var(--color-danger)' }}>
          <ShieldAlert size={18} />
          <span>{error}</span>
        </div>
      </div>
    );
  }

  if (!pack) return null;

  const primary = pack.primary;

  return (
    <div className="glass-card" style={{ marginBottom: 24 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16, flexWrap: 'wrap', marginBottom: 20 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div style={{ padding: 10, borderRadius: 8, background: 'var(--color-info-bg)', color: 'var(--color-info)' }}>
            <ClipboardCheck size={20} />
          </div>
          <div>
            <h2 style={{ fontSize: '1.15rem', color: 'white' }}>Professional Recommendation Pack</h2>
            <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', marginTop: 4 }}>
              Capital {formatIdr(pack.capital)} | Target net portofolio {formatPct(pack.portfolio_target_profit_pct)} | Max position {formatPct(pack.max_position_pct)}
            </div>
            <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginTop: 4 }}>
              Schema {pack.schema_version} | Policy {pack.policy_version}
            </div>
          </div>
        </div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
          {audit && <span className={`badge ${auditStatusClass(audit.overall_status)}`}>{audit.overall_status}</span>}
          <span className={`badge ${portfolioDecisionClass(pack.portfolio_decision)}`}>{pack.portfolio_decision}</span>
          <span className="badge badge-success">Ready {pack.ready_count}</span>
          <span className="badge badge-warning">Draft {pack.draft_count}</span>
          <span className="badge badge-info">Watch {pack.watch_count}</span>
          <span className="badge badge-danger">Rejected {pack.rejected_count}</span>
        </div>
      </div>

      {audit && (
        <div style={{ border: '1px solid var(--border-glass)', borderRadius: 8, padding: 14, marginBottom: 18, background: 'rgba(255,255,255,0.025)' }}>
          <div style={{ display: 'flex', gap: 10, alignItems: 'flex-start', color: 'var(--text-secondary)', lineHeight: 1.5 }}>
            <AlertTriangle size={18} color={audit.overall_status === 'READY_FOR_REVIEW' ? 'var(--color-success)' : 'var(--color-warning)'} />
            <div>
              <div style={{ color: 'white', fontWeight: 700, marginBottom: 2 }}>{audit.next_action}</div>
              <div style={{ fontSize: '0.8rem' }}>
                Missing: {audit.missing_artifacts.length > 0 ? audit.missing_artifacts.join(', ') : 'none'}
              </div>
            </div>
          </div>
          <ArtifactHealth artifacts={audit.artifacts} />
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 12, marginBottom: 18 }}>
        {primaryMetric('Target Net', formatIdr(pack.portfolio_target_profit_amount))}
        {primaryMetric('Selected Exposure', formatIdr(pack.total_selected_position_value))}
        {primaryMetric('Capital Usage', formatPct(pack.total_selected_capital_usage_pct))}
        {primaryMetric('Selected Net', formatIdr(pack.total_selected_expected_net_profit))}
        {primaryMetric('Target Progress', formatPct(pack.portfolio_target_progress_pct))}
        {primaryMetric('Shortfall', formatIdr(pack.portfolio_profit_shortfall_amount))}
        {primaryMetric('Selected Max Loss', formatIdr(pack.total_selected_max_loss_amount))}
        {primaryMetric('Max Loss %', formatPct(pack.total_selected_max_loss_pct))}
      </div>

      {pack.portfolio_flags.length > 0 && (
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 18 }}>
          {pack.portfolio_flags.map((flag) => (
            <span key={flag} className="badge badge-warning">{flag}</span>
          ))}
        </div>
      )}

      {primary ? (
        <div style={{ display: 'grid', gridTemplateColumns: 'minmax(260px, 1.1fr) minmax(320px, 1.9fr)', gap: 20 }}>
          <div style={{ borderRight: '1px solid var(--border-glass)', paddingRight: 20 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'flex-start', marginBottom: 16 }}>
              <div>
                <div style={{ color: 'var(--text-muted)', fontSize: '0.75rem', marginBottom: 4 }}>Primary Candidate</div>
                <div style={{ color: 'white', fontSize: '2rem', fontWeight: 800 }}>{primary.symbol}</div>
              </div>
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
                <span className={`badge ${decisionClass(primary.execution_decision)}`}>{primary.execution_decision}</span>
                <span className={`badge ${gradeClass(primary.decision_grade)}`}>Grade {primary.decision_grade}</span>
                <span className={`badge ${readinessClass(primary.readiness)}`}>{primary.readiness}</span>
              </div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14, marginBottom: 16 }}>
              {primaryMetric('Confidence', primary.confidence_score.toFixed(1))}
              {primaryMetric('Score', primary.final_score.toFixed(1))}
              {primaryMetric('Lots', `${primary.lots} lot`)}
              {primaryMetric('Position', formatIdr(primary.position_value))}
              {primaryMetric('Gross Profit', formatIdr(primary.expected_gross_profit))}
              {primaryMetric('Net Profit', formatIdr(primary.expected_net_profit))}
              {primaryMetric('Max Loss', formatIdr(primary.max_loss_amount))}
              {primaryMetric(
                'Fees + Slip',
                formatIdr(
                  (primary.estimated_buy_fee ?? 0)
                  + (primary.estimated_sell_fee ?? 0)
                  + (primary.estimated_slippage ?? 0),
                ),
              )}
            </div>

            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              {primary.audit_flags.length === 0 ? (
                <span className="badge badge-success">CLEAR</span>
              ) : (
                primary.audit_flags.map((flag) => (
                  <span key={flag} className="badge badge-warning">{flag}</span>
                ))
              )}
            </div>
          </div>

          <div style={{ minWidth: 0 }}>
            <div style={{ display: 'flex', gap: 18, flexWrap: 'wrap', marginBottom: 18 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--text-secondary)' }}>
                <Target size={16} color="var(--color-success)" />
                <span>Entry {formatIdr(primary.entry_price)} | TP {formatIdr(primary.tp1_price)} | SL {formatIdr(primary.stop_loss_price)}</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--text-secondary)' }}>
                <Gauge size={16} color="var(--color-info)" />
                <span>TP {formatPct(primary.target_tp_pct)} | SL {formatPct(primary.stop_loss_pct)} | R:R {primary.risk_reward_ratio?.toFixed(2) ?? '-'}</span>
              </div>
            </div>

            <div style={{ color: 'var(--text-secondary)', lineHeight: 1.6, marginBottom: 16 }}>
              {primary.primary_reason}
            </div>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 16 }}>
              <span className="badge badge-neutral">Status {primary.confidence_components.status_base.toFixed(1)}</span>
              <span className="badge badge-neutral">Score {primary.confidence_components.score_component.toFixed(1)}</span>
              <span className="badge badge-neutral">R:R {primary.confidence_components.risk_reward_component.toFixed(1)}</span>
              <span className="badge badge-warning">Penalty {primary.confidence_components.audit_penalty.toFixed(1)}</span>
            </div>
            <div style={{ display: 'flex', gap: 10, alignItems: 'flex-start', color: 'var(--text-primary)', background: 'rgba(255,255,255,0.04)', padding: 14, borderRadius: 8 }}>
              {primary.readiness === 'READY' ? <CheckCircle2 size={18} color="var(--color-success)" /> : <AlertTriangle size={18} color="var(--color-warning)" />}
              <span>{primary.next_action}</span>
            </div>
          </div>
        </div>
      ) : (
        <div style={{ color: 'var(--text-secondary)' }}>Tidak ada kandidat yang lolos filter recommendation pack.</div>
      )}

      {pack.candidates.length > 0 && (
        <div style={{ marginTop: 22, overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 820 }}>
            <thead>
              <tr style={{ color: 'var(--text-muted)', fontSize: '0.78rem', textAlign: 'left' }}>
                <th style={{ padding: '8px 10px' }}>Symbol</th>
                <th style={{ padding: '8px 10px' }}>Decision</th>
                <th style={{ padding: '8px 10px' }}>Grade</th>
                <th style={{ padding: '8px 10px' }}>Confidence</th>
                <th style={{ padding: '8px 10px' }}>Readiness</th>
                <th style={{ padding: '8px 10px' }}>Entry</th>
                <th style={{ padding: '8px 10px' }}>TP%</th>
                <th style={{ padding: '8px 10px' }}>Net</th>
                <th style={{ padding: '8px 10px' }}>R:R</th>
                <th style={{ padding: '8px 10px' }}>Lots</th>
              </tr>
            </thead>
            <tbody>
              {pack.candidates.map((item) => (
                <ShortlistRow key={item.symbol} item={item} />
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div style={{ marginTop: 18, color: 'var(--text-muted)', fontSize: '0.78rem' }}>{pack.caveat}</div>
    </div>
  );
};
