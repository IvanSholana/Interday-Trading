/**
 * usePipeline.ts — Custom React hook that encapsulates all pipeline API calls
 * and real-time polling state.
 *
 * Separating this logic from App.tsx keeps the root component focused on
 * rendering and makes it easier for an LLM to locate and modify API behavior
 * without accidentally touching UI code.
 *
 * Usage:
 *   const {
 *     isRunning, pipelineStatus, pipelineProgress, pipelineCurrentStage,
 *     pipelineError, pipelineLogs, runsList, selectedRunId,
 *     setSelectedRunId, fetchRunsList, handleStartRun, handleCancelRun,
 *   } = usePipeline();
 */
import { useState, useEffect, useCallback } from 'react';
import type {
  RunSummary,
  PipelineStatus,
  PipelineStatusValue,
  RunRequest,
  RecommendationPack,
  RunAuditReport,
} from '../types/api';

// ---------------------------------------------------------------------------
// Types specific to the hook's public interface
// ---------------------------------------------------------------------------

export interface PipelineState {
  isRunning: boolean;
  pipelineStatus: PipelineStatusValue;
  pipelineProgress: number;
  pipelineCurrentStage: string;
  pipelineError: string | null;
  pipelineLogs: string[];
}

export interface PipelineActions {
  runsList: RunSummary[];
  selectedRunId: string;
  setSelectedRunId: (id: string) => void;
  recommendationPack: RecommendationPack | null;
  runAudit: RunAuditReport | null;
  recommendationLoading: boolean;
  recommendationError: string | null;
  fetchRunsList: (selectLatest?: boolean) => Promise<void>;
  fetchRecommendation: (runId: string, capital: number, maxTpPct?: number, maxPositionPct?: number) => Promise<void>;
  handleStartRun: (payload: RunRequest, resumeRunId?: string) => Promise<void>;
  handleCancelRun: () => Promise<void>;
}

// ---------------------------------------------------------------------------
// Hook implementation
// ---------------------------------------------------------------------------

export function usePipeline(): PipelineState & PipelineActions {
  // ── Runs explorer ─────────────────────────────────────────────────────────
  const [runsList, setRunsList] = useState<RunSummary[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string>('');
  const [recommendationPack, setRecommendationPack] = useState<RecommendationPack | null>(null);
  const [runAudit, setRunAudit] = useState<RunAuditReport | null>(null);
  const [recommendationLoading, setRecommendationLoading] = useState<boolean>(false);
  const [recommendationError, setRecommendationError] = useState<string | null>(null);

  // ── Active pipeline execution ──────────────────────────────────────────────
  const [isRunning, setIsRunning] = useState<boolean>(false);
  const [pipelineStatus, setPipelineStatus] = useState<PipelineStatusValue>('idle');
  const [pipelineProgress, setPipelineProgress] = useState<number>(0);
  const [pipelineCurrentStage, setPipelineCurrentStage] = useState<string>('');
  const [pipelineError, setPipelineError] = useState<string | null>(null);
  const [pipelineLogs, setPipelineLogs] = useState<string[]>([]);

  // ── Fetch runs list from backend ──────────────────────────────────────────

  const fetchRunsList = useCallback(async (selectLatest = false): Promise<void> => {
    try {
      const res = await fetch('/api/runs');
      const data: RunSummary[] = await res.json();
      setRunsList(data);
      if (data.length > 0 && (!selectedRunId || selectLatest)) {
        setSelectedRunId(data[0].run);
      }
    } catch (err) {
      console.error('[usePipeline] Error fetching runs list:', err);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const fetchRecommendation = useCallback(
    async (runId: string, capital: number, maxTpPct = 0.05, maxPositionPct = 1.0): Promise<void> => {
      if (!runId) {
        setRecommendationPack(null);
        setRunAudit(null);
        return;
      }

      setRecommendationLoading(true);
      setRecommendationError(null);
      try {
        const params = new URLSearchParams({
          capital: String(capital),
          max_tp_pct: String(maxTpPct),
          max_position_pct: String(maxPositionPct),
        });
        const res = await fetch(`/api/run-audit/${runId}?${params.toString()}`);
        if (!res.ok) {
          const err = await res.json();
          throw new Error((err as { detail?: string }).detail ?? 'Failed to load run audit');
        }
        const data: RunAuditReport = await res.json();
        setRunAudit(data);
        setRecommendationPack(data.recommendation);
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : 'Error loading run audit';
        setRecommendationError(message);
        setRecommendationPack(null);
        setRunAudit(null);
      } finally {
        setRecommendationLoading(false);
      }
    },
    [],
  );

  // ── Apply a status snapshot from the API ──────────────────────────────────

  const applyStatusSnapshot = useCallback((data: PipelineStatus) => {
    setPipelineStatus(data.status);
    setPipelineProgress(data.progress);
    setPipelineCurrentStage(data.current_stage);
    setPipelineError(data.error);
    setPipelineLogs(data.logs ?? []);
  }, []);

  // ── On mount: initial fetch + check if a run is already active ────────────

  useEffect(() => {
    fetchRunsList();

    (async () => {
      try {
        const res = await fetch('/api/status');
        const data: PipelineStatus = await res.json();
        if (data.status === 'running') {
          setIsRunning(true);
          applyStatusSnapshot(data);
        }
      } catch (err) {
        console.error('[usePipeline] Error checking initial pipeline status:', err);
      }
    })();
  }, [fetchRunsList, applyStatusSnapshot]);

  // ── Polling while a run is active ─────────────────────────────────────────

  useEffect(() => {
    if (!isRunning) return;

    const interval = setInterval(async () => {
      try {
        const res = await fetch('/api/status');
        const data: PipelineStatus = await res.json();
        applyStatusSnapshot(data);

        if (data.status !== 'running') {
          setIsRunning(false);
          if (data.run_id) {
            await fetchRunsList(true);
            setSelectedRunId(data.run_id);
          } else {
            await fetchRunsList();
          }
        }
      } catch (err) {
        console.error('[usePipeline] Error polling status:', err);
      }
    }, 1000);

    return () => clearInterval(interval);
  }, [isRunning, applyStatusSnapshot, fetchRunsList]);

  // ── Start a new run (or resume a failed one) ──────────────────────────────

  const handleStartRun = useCallback(
    async (payload: RunRequest, resumeRunId?: string): Promise<void> => {
      if (isRunning) return;

      setIsRunning(true);
      setPipelineStatus('running');
      setPipelineProgress(0);
      setPipelineLogs([
        `[SYS] Inisialisasi pipeline request ke backend...${
          resumeRunId ? ` (Resuming run ${resumeRunId})` : ''
        }`,
      ]);

      const body: RunRequest = {
        ...payload,
        resume_run_id: resumeRunId ?? null,
      };

      try {
        const res = await fetch('/api/run', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        });

        if (!res.ok) {
          const err = await res.json();
          throw new Error((err as { detail?: string }).detail ?? 'Failed to start pipeline');
        }

        const data = await res.json();
        setPipelineLogs((prev) => [
          ...prev,
          `[SYS] Pipeline berhasil distart dengan ID: ${data.run_id}${
            resumeRunId ? ' (Melanjutkan run sebelumnya)' : ''
          }`,
        ]);
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : 'Error triggering run';
        console.error('[usePipeline]', err);
        setIsRunning(false);
        setPipelineStatus('failed');
        setPipelineError(message);
        setPipelineLogs((prev) => [...prev, `[ERR] Gagal menjalankan pipeline: ${message}`]);
      }
    },
    [isRunning],
  );

  // ── Cancel the running pipeline ───────────────────────────────────────────

  const handleCancelRun = useCallback(async (): Promise<void> => {
    try {
      setPipelineLogs((prev) => [
        ...prev,
        '[SYS] Mengirim permintaan pembatalan pipeline...',
      ]);
      const res = await fetch('/api/cancel', { method: 'POST' });
      if (!res.ok) {
        const err = await res.json();
        throw new Error((err as { detail?: string }).detail ?? 'Gagal membatalkan pipeline');
      }
      setPipelineLogs((prev) => [
        ...prev,
        '[SYS] Permintaan pembatalan dikirim. Menunggu stage saat ini selesai...',
      ]);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Error cancelling run';
      console.error('[usePipeline]', err);
      setPipelineLogs((prev) => [...prev, `[ERR] Gagal membatalkan: ${message}`]);
    }
  }, []);

  // ── Public interface ──────────────────────────────────────────────────────

  return {
    // State
    isRunning,
    pipelineStatus,
    pipelineProgress,
    pipelineCurrentStage,
    pipelineError,
    pipelineLogs,
    // Run explorer
    runsList,
    selectedRunId,
    setSelectedRunId,
    recommendationPack,
    runAudit,
    recommendationLoading,
    recommendationError,
    // Actions
    fetchRunsList,
    fetchRecommendation,
    handleStartRun,
    handleCancelRun,
  };
}
