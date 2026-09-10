import { useEffect, useRef, useState } from "react";
import {
  api,
  type AnalysisJobStatus,
  type AnalysisPipelineStatus,
  type ScanStats,
  type GenreTagJobStatus,
  type DatabaseValidationJobStatus,
  type DatabaseOptimizationJobStatus,
  type PromotedClassifier,
} from "./api";
import {
  analysisJobRequest,
  formatMegabytes,
  optimizationPhaseLabel,
  scanSummary,
  type ProcessLogKind,
} from "./jobUi";
import { basename } from "./trackDisplay";
import type { SearchNotice } from "./useSearchRequests";
import type { useActivityLog } from "./useActivityLog";
import type { useLibraryState } from "./useLibraryState";
import { errorText } from "./errors";

type JobStateOptions = {
  classifiers: PromotedClassifier[];
  setProcessLogKind: (kind: ProcessLogKind) => void;
  refreshLibrary: ReturnType<typeof useLibraryState>["refreshLibrary"];
  refreshLibrarySummary: ReturnType<typeof useLibraryState>["refreshLibrarySummary"];
  refreshClassifierProfilesInBackground: () => void;
  setNotice: (notice: SearchNotice) => void;
  appendActivity: ReturnType<typeof useActivityLog>["appendActivity"];
  promptDatabaseOptimization: (job: DatabaseValidationJobStatus) => void;
};

export function useJobState({
  classifiers,
  setProcessLogKind,
  refreshLibrary,
  refreshLibrarySummary,
  refreshClassifierProfilesInBackground,
  setNotice,
  appendActivity,
  promptDatabaseOptimization,
}: JobStateOptions) {
  const [analysisJob, setAnalysisJob] = useState<AnalysisJobStatus | null>(null);
  const [analysisPipelineJob, setAnalysisPipelineJob] = useState<AnalysisPipelineStatus | null>(null);
  const [scanJob, setScanJob] = useState<ScanStats | null>(null);
  const [genreTagJob, setGenreTagJob] = useState<GenreTagJobStatus | null>(null);
  const [databaseValidationJob, setDatabaseValidationJob] = useState<DatabaseValidationJobStatus | null>(null);
  const [databaseOptimizationJob, setDatabaseOptimizationJob] = useState<DatabaseOptimizationJobStatus | null>(null);
  const scanRunning = Boolean(scanJob?.state && ["queued", "running"].includes(scanJob.state));
  const analysisRunning = Boolean(
    (analysisJob && ["queued", "running"].includes(analysisJob.state))
    || (analysisPipelineJob && ["queued", "running"].includes(analysisPipelineJob.state))
  );
  const genreTagRunning = Boolean(genreTagJob && ["queued", "running"].includes(genreTagJob.state));
  const databaseValidationRunning = Boolean(databaseValidationJob && ["queued", "running"].includes(databaseValidationJob.state));
  const databaseOptimizationRunning = Boolean(databaseOptimizationJob && ["queued", "running"].includes(databaseOptimizationJob.state));

  const reportPollError = (error: unknown) => {
    setNotice({ kind: "error", text: errorText(error) });
  };

  useJobPolling(scanJob, 1200, (job) => api.scanJob(job.job_id!), (job) => {
    setScanJob(job);
    if (["completed", "cancelled", "failed"].includes(job.state || "")) {
      void refreshLibrary(0, { refreshSummary: true });
      refreshClassifierProfilesInBackground();
      if (job.state === "completed") {
        appendActivity("ok", "Сканирование завершено", scanSummary(job));
      }
      if (job.state === "cancelled") {
        appendActivity("warn", "Сканирование остановлено", scanSummary(job));
      }
    }
  }, reportPollError);

  const analysisRoute = analysisJob?.adapter_name === "multi" || analysisJob?.models?.length
    ? "analysis" : `classifier:${analysisJob?.adapter_name}`;
  useJobPolling(analysisJob, 1500, analysisJobRequest, (job) => {
    setAnalysisJob(job);
    if (["completed", "cancelled", "failed"].includes(job.state)) {
      void refreshLibrary(0, { refreshSummary: true });
      refreshClassifierProfilesInBackground();
    }
  }, reportPollError, analysisRoute);

  useJobPolling(databaseValidationJob, 1000, (job) => api.databaseValidationJob(job.job_id), (job) => {
    setDatabaseValidationJob(job);
    const detail = `${job.checked} проверено · предупреждений ${job.warnings} · ошибок ${job.errors}`;
    const prefix = job.state === "completed" ? "Проверка БД завершена" : job.state === "cancelled" ? "Проверка БД отменена" : "Проверка БД";
    setNotice({ kind: job.errors ? "error" : "ok", text: `${prefix}: ${detail}` });
    promptDatabaseOptimization(job);
  }, reportPollError);

  useJobPolling(databaseOptimizationJob, 1000, (job) => api.databaseOptimizationJob(job.job_id), (job) => {
    setDatabaseOptimizationJob(job);
    if (job.state === "completed") {
      setNotice({ kind: "ok", text: `Оптимизация БД завершена: ${formatMegabytes(job.size_before)} → ${formatMegabytes(job.size_after)}` });
      appendActivity("ok", "Оптимизация БД завершена", job.files.map((file) => basename(file.backup_path)).join(", "));
      void refreshLibrarySummary();
    } else if (job.state === "failed") {
      setNotice({ kind: "error", text: `Оптимизация БД не удалась: ${job.error ?? "ошибка"}` });
    } else {
      setNotice({ kind: "ok", text: `Оптимизация БД: ${optimizationPhaseLabel(job)}` });
    }
  }, reportPollError);

  // Each stage child is adopted once; its own poller keeps it current.
  const adoptedChildJobId = useRef<string | null>(null);
  useEffect(() => {
    adoptedChildJobId.current = null;
  }, [analysisPipelineJob?.job_id]);
  useJobPolling(analysisPipelineJob, 1500, (job) => api.analysisPipeline(job.job_id), async (job, isCurrent) => {
    setAnalysisPipelineJob(job);
    if (["completed", "cancelled", "failed"].includes(job.state)) {
      void refreshLibrary(0, { refreshSummary: true });
      refreshClassifierProfilesInBackground();
    }
    const currentStage = job.current_stage;
    const childJobId = currentStage ? job.stages[currentStage]?.child_job_id : null;
    if (childJobId && childJobId !== adoptedChildJobId.current) {
      const child = await api.analysisJob(childJobId);
      if (!isCurrent()) return;
      adoptedChildJobId.current = childJobId;
      setAnalysisJob(child);
    }
  }, reportPollError);

  useJobPolling(genreTagJob, 1200, (job) => api.genreTagJob(job.job_id), (job) => {
    setGenreTagJob(job);
    if (["completed", "cancelled", "failed"].includes(job.state)) {
      void refreshLibrary(0, { refreshSummary: true });
      if (job.state === "completed") {
        appendActivity("ok", "Запись жанров завершена", genreTagJobSummary(job));
      }
      if (job.state === "cancelled") {
        appendActivity("warn", "Запись жанров остановлена", genreTagJobSummary(job));
      }
    }
  }, reportPollError);
  async function loadLatestJobs(promotedClassifiers = classifiers) {
    await Promise.all([
      api.latestScanJob().then((job) => {
        if (job) {
          setScanJob(job);
          setProcessLogKind("scan");
        }
      }).catch(() => undefined),
      api.latestAnalysisJob().then((job) => {
        if (job) {
          setAnalysisJob(job);
          if (["queued", "running"].includes(job.state)) setProcessLogKind("analysis");
        }
      }).catch(() => undefined),
      api.latestAnalysisPipeline().then((job) => {
        if (job) setAnalysisPipelineJob(job);
      }).catch(() => undefined),
      ...promotedClassifiers.map((classifier) =>
        api.latestClassifierJob(classifier.classifier_key).then((job) => {
          if (job) {
            setAnalysisJob((current) => (current && ["queued", "running"].includes(current.state) ? current : job));
            if (["queued", "running"].includes(job.state)) setProcessLogKind("analysis");
          }
        }).catch(() => undefined)
      ),
      api.genreTagJobLatest().then((job) => {
        if (job) {
          setGenreTagJob(job);
          if (["queued", "running"].includes(job.state)) setProcessLogKind("genre_tags");
        }
      }).catch(() => undefined),
      api.latestDatabaseValidationJob().then((job) => {
        if (job) {
          setDatabaseValidationJob(job);
          if (["queued", "running"].includes(job.state)) setProcessLogKind("database_validation");
        }
      }).catch(() => undefined),
      api.latestDatabaseOptimizationJob().then((job) => {
        if (job) {
          setDatabaseOptimizationJob(job);
          if (["queued", "running"].includes(job.state)) setProcessLogKind("database_optimization");
        }
      }).catch(() => undefined)
    ]);
  }

  return {
    analysisJob,
    setAnalysisJob,
    analysisPipelineJob,
    setAnalysisPipelineJob,
    scanJob,
    setScanJob,
    genreTagJob,
    setGenreTagJob,
    databaseValidationJob,
    setDatabaseValidationJob,
    databaseOptimizationJob,
    setDatabaseOptimizationJob,
    scanRunning,
    analysisRunning,
    genreTagRunning,
    databaseValidationRunning,
    databaseOptimizationRunning,
    loadLatestJobs,
  };
}

function genreTagJobSummary(job: GenreTagJobStatus) {
  return `записано ${job.applied} · пропущено ${job.skipped} · ошибок ${job.failed} · всего ${job.total}`;
}

function useJobPolling<Job extends { job_id?: string | null; state?: string }>(
  job: Job | null,
  delay: number,
  request: (job: Job) => Promise<Job>,
  receive: (job: Job, isCurrent: () => boolean) => void | Promise<void>,
  onError: (error: unknown) => void,
  route = "",
) {
  const latest = useRef({ request, receive, onError });
  useEffect(() => { latest.current = { request, receive, onError }; });
  const active = Boolean(job?.job_id && ["queued", "running"].includes(job.state ?? ""));
  const jobId = job?.job_id;
  useEffect(() => {
    if (!active || !job) return;
    let current = true;
    let terminal = false;
    let timer: number;
    const isCurrent = () => current;
    async function poll() {
      try {
        const next = await latest.current.request(job!);
        if (!current) return;
        // Stop before invoking completion callbacks, even if React has not committed yet.
        terminal = !["queued", "running"].includes(next.state ?? "");
        await latest.current.receive(next, isCurrent);
      } catch (error) {
        if (current) latest.current.onError(error);
      } finally {
        if (current && !terminal) timer = window.setTimeout(() => { void poll(); }, delay);
      }
    }
    timer = window.setTimeout(() => { void poll(); }, delay);
    return () => {
      current = false;
      window.clearTimeout(timer);
    };
  }, [jobId, active, route, delay]);
}
