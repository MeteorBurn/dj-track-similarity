import { Trash2 } from "lucide-react";
import { ReactNode } from "react";
import { AnalysisJobStatus, api, ScanStats } from "./api";
import { basename, formatEta, formatTime } from "./trackDisplay";

export type ActivityEvent = { id: number; time: number; level: "info" | "ok" | "warn" | "error"; message: string; detail?: string };

export function ProcessLog({
  kind,
  scanJob,
  analysisJob
}: {
  kind: "scan" | "analysis";
  scanJob: ScanStats | null;
  analysisJob: AnalysisJobStatus | null;
}) {
  if (kind === "analysis") {
    return <AnalysisProcessLog job={analysisJob} />;
  }
  return <ScanProcessLog job={scanJob} />;
}

export function TabbedLog({
  activeTab,
  onTabChange,
  processKind,
  scanJob,
  analysisJob,
  events
}: {
  activeTab: "journal" | "process";
  onTabChange: (tab: "journal" | "process") => void;
  processKind: "scan" | "analysis";
  scanJob: ScanStats | null;
  analysisJob: AnalysisJobStatus | null;
  events: ActivityEvent[];
}) {
  return (
    <section className="log-panel">
      <div className="log-tabs" role="tablist" aria-label="Журналы процесса">
        <button
          className={activeTab === "journal" ? "active" : ""}
          role="tab"
          aria-selected={activeTab === "journal"}
          onClick={() => onTabChange("journal")}
        >
          Журнал
          <span>{events.length}</span>
        </button>
        <button
          className={activeTab === "process" ? "active" : ""}
          role="tab"
          aria-selected={activeTab === "process"}
          onClick={() => onTabChange("process")}
        >
          Лог
          <span>{processEventCount(processKind, scanJob, analysisJob)}</span>
        </button>
      </div>
      <div className="log-tab-body">
        {activeTab === "journal" ? (
          <ActivityLog events={events} />
        ) : (
          <ProcessLog kind={processKind} scanJob={scanJob} analysisJob={analysisJob} />
        )}
      </div>
    </section>
  );
}

function processEventCount(kind: "scan" | "analysis", scanJob: ScanStats | null, analysisJob: AnalysisJobStatus | null) {
  if (kind === "analysis") return analysisJob?.events.length || 0;
  return scanJob?.events?.length || 0;
}

export function analysisJobRequest(job: AnalysisJobStatus) {
  if (job.adapter_name === "sonara") return api.sonaraJob(job.job_id);
  if (job.adapter_name === "maest") return api.genreJob(job.job_id);
  return api.analyzeJob(job.job_id);
}

export function cancelAnalysisJob(job: AnalysisJobStatus) {
  if (job.adapter_name === "sonara") return api.cancelSonaraJob(job.job_id);
  if (job.adapter_name === "maest") return api.cancelGenreJob(job.job_id);
  return api.cancelAnalyzeJob(job.job_id);
}

export function AnalysisButton({
  label,
  icon,
  disabled,
  title,
  onRun,
  onReset
}: {
  label: string;
  icon: ReactNode;
  disabled: boolean;
  title?: string;
  onRun: () => void;
  onReset: () => void;
}) {
  return (
    <div className="analysis-button-pair">
      <button className="primary" disabled={disabled} title={title} onClick={onRun}>
        {icon}
        {label}
      </button>
      <button className="analysis-reset" disabled={disabled} title={`Reset ${label}`} aria-label={`Reset ${label}`} onClick={onReset}>
        Reset
        <Trash2 size={14} />
      </button>
    </div>
  );
}

function ScanProcessLog({ job }: { job: ScanStats | null }) {
  if (!job) {
    return <div className="process-box">Сканирование не запущено</div>;
  }
  const total = job.total || 0;
  const processed = job.processed || 0;
  const percent = total ? Math.round((processed / total) * 100) : 100;
  const running = ["queued", "running"].includes(job.state || "");
  const etaSeconds = running && job.avg_seconds_per_track ? Math.max(0, (total - processed) * job.avg_seconds_per_track) : null;
  const latestEvents = [...(job.events || [])].reverse().slice(0, 12);
  return (
    <div className="process-box">
      <div className="process-head">
        <strong>{job.state || "idle"}</strong>
        <span>{job.root || "scan"} · {processed}/{total}</span>
      </div>
      <progress max={total || 1} value={processed} />
      <div className="process-grid">
        <span>+{job.added || 0}</span>
        <span>upd {job.updated || 0}</span>
        <span>same {job.unchanged || 0}</span>
        <span>fail {job.failed || 0}</span>
        <span>{job.workers || 1} поток</span>
        <span>{percent}%</span>
      </div>
      {job.avg_seconds_per_track != null && <span className="analysis-muted">{job.avg_seconds_per_track.toFixed(2)} s/file{etaSeconds ? ` · ETA ${formatEta(etaSeconds)}` : ""}</span>}
      {job.current_path && <span className="analysis-current">Сейчас: {basename(job.current_path)}</span>}
      <div className="process-log">
        <div className="process-log-title">
          <span>Журнал процесса</span>
          <span>{latestEvents.length}/{job.events?.length || 0}</span>
        </div>
        <div className="process-log-list simple">
        {latestEvents.length === 0 ? (
          <span className="process-log-empty">Событий пока нет</span>
        ) : (
          latestEvents.map((event, index) => (
            <div className={`process-log-row ${event.level}`} key={`${event.timestamp}-${index}`}>
              <time>{formatTime(event.timestamp)}</time>
              <strong>{event.level}</strong>
              <span>
              {event.message}{event.path ? ` · ${basename(event.path)}` : ""}
              </span>
            </div>
          ))
        )}
        </div>
      </div>
    </div>
  );
}

function ActivityLog({ events }: { events: ActivityEvent[] }) {
  return (
    <div className="activity-log">
      <div className="activity-log-title">
        <span>Журнал действий</span>
        <span>{events.length}</span>
      </div>
      <div className="activity-log-list">
        {events.map((event) => (
          <div className={`activity-log-row ${event.level}`} key={event.id}>
            <time>{new Date(event.time).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit", second: "2-digit" })}</time>
            <strong>{event.message}</strong>
            {event.detail && <span>{event.detail}</span>}
          </div>
        ))}
      </div>
    </div>
  );
}

export function scanSummary(job: ScanStats) {
  return `+${job.added || 0} · обновлено ${job.updated || 0} · без изменений ${job.unchanged || 0} · ошибок ${job.failed || 0}`;
}

export function stageIndicatorLabel(scanJob: ScanStats | null, analysisJob: AnalysisJobStatus | null) {
  if (scanJob?.state && ["queued", "running"].includes(scanJob.state)) return "Идет сканирование";
  if (analysisJob && ["queued", "running"].includes(analysisJob.state)) return "Идет анализ";
  if (scanJob?.state === "cancelled" || analysisJob?.state === "cancelled") return "Этап остановлен";
  return "Процесс не запущен";
}

function analysisRuntimeLabel(job: AnalysisJobStatus) {
  const model = job.model_name || job.adapter_name;
  if (job.adapter_name === "fake") return `${model} · smoke`;
  return `${model} · ${job.device || `${job.device_requested} pending`}`;
}

function AnalysisProcessLog({ job }: { job: AnalysisJobStatus | null }) {
  if (!job) {
    return <div className="process-box">Анализ не запущен</div>;
  }
  const percent = job.total ? Math.round((job.processed / job.total) * 100) : 100;
  const running = ["queued", "running"].includes(job.state);
  const etaSeconds = running && job.avg_seconds_per_track ? Math.max(0, (job.total - job.processed) * job.avg_seconds_per_track) : null;
  const latestEvents = [...job.events].reverse().slice(0, 14);
  return (
    <div className="process-box">
      <div className="process-head">
        <strong>{job.state}</strong>
        <span>{analysisRuntimeLabel(job)}</span>
      </div>
      <progress max={job.total || 1} value={job.processed} />
      <div className="process-grid">
        <span>{job.processed}/{job.total}</span>
        <span>ok {job.analyzed}</span>
        <span>fail {job.failed}</span>
        {job.skipped ? <span>skip {job.skipped}</span> : null}
        <span>batch {job.batch_size || job.workers || 1}</span>
        <span>{percent}%</span>
      </div>
      {job.avg_seconds_per_track != null && <span className="analysis-muted">{job.avg_seconds_per_track.toFixed(2)} s/track{etaSeconds ? ` · ETA ${formatEta(etaSeconds)}` : ""}</span>}
      {job.current_path && <span className="analysis-current">Сейчас: {basename(job.current_path)}</span>}
      {job.errors.length > 0 && <span className="analysis-error">{job.errors[0].path}: {job.errors[0].error}</span>}
      <div className="process-log">
        <div className="process-log-title">
          <span>Журнал процесса</span>
          <span>{latestEvents.length}/{job.events.length}</span>
        </div>
        <div className="process-log-list">
          {latestEvents.length === 0 ? (
            <span className="process-log-empty">Событий пока нет</span>
          ) : (
            latestEvents.map((event, index) => (
              <div className={`process-log-row ${event.level}`} key={`${event.timestamp}-${index}`}>
                <time>{formatTime(event.timestamp)}</time>
                <strong>{event.level}</strong>
                <span>{event.message}{event.path ? ` · ${basename(event.path)}` : ""}</span>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
