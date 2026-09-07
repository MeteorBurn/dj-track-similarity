import { useEffect, useState } from "react";
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

  useEffect(() => {
    if (!scanJob?.job_id || !["queued", "running"].includes(scanJob.state || "")) return;
    const timer = window.setInterval(() => {
      void api.scanJob(scanJob.job_id!).then((job) => {
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
      }).catch((error) => {
        setNotice({ kind: "error", text: error instanceof Error ? error.message : String(error) });
      });
    }, 1200);
    return () => window.clearInterval(timer);
  }, [scanJob?.job_id, scanJob?.state]);

  useEffect(() => {
    if (!analysisJob || !["queued", "running"].includes(analysisJob.state)) return;
    const timer = window.setInterval(() => {
      const request = analysisJobRequest(analysisJob);
      void request.then((job) => {
        setAnalysisJob(job);
        if (["completed", "cancelled", "failed"].includes(job.state)) {
          void refreshLibrary(0, { refreshSummary: true });
          refreshClassifierProfilesInBackground();
        }
      }).catch((error) => {
        setNotice({ kind: "error", text: error instanceof Error ? error.message : String(error) });
      });
    }, 1500);
    return () => window.clearInterval(timer);
  }, [analysisJob?.job_id, analysisJob?.state]);

  useEffect(() => {
    if (!databaseValidationJob || !["queued", "running"].includes(databaseValidationJob.state)) return;
    const timer = window.setInterval(() => {
      void api.databaseValidationJob(databaseValidationJob.job_id).then((job) => {
        setDatabaseValidationJob(job);
        const detail = `${job.checked} проверено · предупреждений ${job.warnings} · ошибок ${job.errors}`;
        const prefix = job.state === "completed" ? "Проверка БД завершена" : job.state === "cancelled" ? "Проверка БД отменена" : "Проверка БД";
        setNotice({ kind: job.errors ? "error" : "ok", text: `${prefix}: ${detail}` });
        promptDatabaseOptimization(job);
      }).catch((error) => setNotice({ kind: "error", text: error instanceof Error ? error.message : String(error) }));
    }, 1000);
    return () => window.clearInterval(timer);
  }, [databaseValidationJob?.job_id, databaseValidationJob?.state]);

  useEffect(() => {
    if (!databaseOptimizationJob || !["queued", "running"].includes(databaseOptimizationJob.state)) return;
    const timer = window.setInterval(() => {
      void api.databaseOptimizationJob(databaseOptimizationJob.job_id).then((job) => {
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
      }).catch((error) => setNotice({ kind: "error", text: error instanceof Error ? error.message : String(error) }));
    }, 1000);
    return () => window.clearInterval(timer);
  }, [databaseOptimizationJob?.job_id, databaseOptimizationJob?.state]);

  useEffect(() => {
    if (!analysisPipelineJob || !["queued", "running"].includes(analysisPipelineJob.state)) return;
    // Each stage child is adopted once; its own poller keeps it current.
    let adoptedChildJobId: string | null = null;
    const timer = window.setInterval(() => {
      void api.analysisPipeline(analysisPipelineJob.job_id).then((job) => {
        setAnalysisPipelineJob(job);
        const currentStage = job.current_stage;
        const childJobId = currentStage ? job.stages[currentStage]?.child_job_id : null;
        if (childJobId && childJobId !== adoptedChildJobId) {
          adoptedChildJobId = childJobId;
          void api.analysisJob(childJobId).then(setAnalysisJob).catch((error) => {
            adoptedChildJobId = null;
            setNotice({ kind: "error", text: error instanceof Error ? error.message : String(error) });
          });
        }
        if (["completed", "cancelled", "failed"].includes(job.state)) {
          void refreshLibrary(0, { refreshSummary: true });
          refreshClassifierProfilesInBackground();
        }
      }).catch((error) => {
        setNotice({ kind: "error", text: error instanceof Error ? error.message : String(error) });
      });
    }, 1500);
    return () => window.clearInterval(timer);
  }, [analysisPipelineJob?.job_id, analysisPipelineJob?.state]);

  useEffect(() => {
    if (!genreTagJob || !["queued", "running"].includes(genreTagJob.state)) return;
    const timer = window.setInterval(() => {
      void api.genreTagJob(genreTagJob.job_id).then((job) => {
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
      }).catch((error) => {
        setNotice({ kind: "error", text: error instanceof Error ? error.message : String(error) });
      });
    }, 1200);
    return () => window.clearInterval(timer);
  }, [genreTagJob?.job_id, genreTagJob?.state]);
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
