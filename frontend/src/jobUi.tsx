import { AnalysisJobStatus, AnalysisModel, api, DatabaseValidationJobStatus, GenreTagJobStatus, ScanStats } from "./api";
import { basename, formatEta } from "./trackDisplay";

const ACTIVE_JOB_STATES = ["queued", "running"] as const;
const AUDIO_MODELS: AnalysisModel[] = ["sonara", "maest", "mert", "muq", "clap"];
const MAX_LOG_EVENTS = 120;
const SECONDS_TO_MS = 1000;

function calculateProgressPercent(processed: number, total: number): number {
  return total ? Math.round((processed / total) * 100) : 100;
}

function calculateEta(isRunning: boolean, avgSecondsPerTrack: number | null | undefined, total: number, processed: number): number | null {
  return isRunning && avgSecondsPerTrack ? Math.max(0, (total - processed) * avgSecondsPerTrack) : null;
}

function isJobActive(state: string | undefined): boolean {
  return state ? ACTIVE_JOB_STATES.includes(state as (typeof ACTIVE_JOB_STATES)[number]) : false;
}

export type ActivityEvent = { id: number; time: number; level: "info" | "ok" | "warn" | "error"; message: string; detail?: string };

type UnifiedLogEvent = {
  id: string;
  timeMs: number;
  level: ActivityEvent["level"];
  source: string;
  message: string;
  detail?: string;
};

export function UnifiedLog({
  processKind,
  scanJob,
  analysisJob,
  genreTagJob,
  databaseValidationJob,
  events,
  className = ""
}: {
  processKind: "scan" | "analysis" | "genre_tags" | "database_validation";
  scanJob: ScanStats | null;
  analysisJob: AnalysisJobStatus | null;
  genreTagJob: GenreTagJobStatus | null;
  databaseValidationJob: DatabaseValidationJobStatus | null;
  events: ActivityEvent[];
  className?: string;
}) {
  const mergedEvents = unifiedLogEvents(scanJob, analysisJob, genreTagJob, databaseValidationJob, events);
  return (
    <section className={`log-panel ${className}`.trim()}>
      <div className="log-title">
        <span>Лог</span>
        <span>{mergedEvents.length}</span>
      </div>
      <div className="log-body">
        <ProcessStatus kind={processKind} scanJob={scanJob} analysisJob={analysisJob} genreTagJob={genreTagJob} databaseValidationJob={databaseValidationJob} />
        <UnifiedEventList events={mergedEvents} />
      </div>
    </section>
  );
}

function ProcessStatus({
  kind,
  scanJob,
  analysisJob,
  genreTagJob,
  databaseValidationJob
}: {
  kind: "scan" | "analysis" | "genre_tags" | "database_validation";
  scanJob: ScanStats | null;
  analysisJob: AnalysisJobStatus | null;
  genreTagJob: GenreTagJobStatus | null;
  databaseValidationJob: DatabaseValidationJobStatus | null;
}) {
  if (kind === "database_validation") return <DatabaseValidationProcessStatus job={databaseValidationJob} />;
  if (kind === "genre_tags") {
    return <GenreTagProcessStatus job={genreTagJob} />;
  }
  if (kind === "analysis") {
    return <AnalysisProcessStatus job={analysisJob} />;
  }
  return <ScanProcessStatus job={scanJob} />;
}

function unifiedLogEvents(
  scanJob: ScanStats | null,
  analysisJob: AnalysisJobStatus | null,
  genreTagJob: GenreTagJobStatus | null,
  databaseValidationJob: DatabaseValidationJobStatus | null,
  activityEvents: ActivityEvent[]
) {
  const uiEvents = transformUiEvents(activityEvents);
  const scanEvents = transformJobEvents("scan", scanJob?.events || [], { idPrefix: "scan" });
  const analysisEvents = transformJobEvents("analysis", analysisJob?.events || [], {
    idPrefix: "analysis",
    filterFn: (event) => !isPerClassifierAnalysisEvent(event.message)
  });
  const genreTagEvents = transformJobEvents("genre tags", genreTagJob?.events || [], { idPrefix: "genre-tags" });
  const validationEvents = transformJobEvents("validation", databaseValidationJob?.events || [], {
    idPrefix: "validation",
    formatDetail: (event) => event.path || undefined
  });
  return [...uiEvents, ...scanEvents, ...analysisEvents, ...genreTagEvents, ...validationEvents].sort((left, right) => right.timeMs - left.timeMs).slice(0, MAX_LOG_EVENTS);
}

type JobEvent = { timestamp: number; level: string; message: string; path?: string | null };

function transformJobEvents(
  source: string,
  events: JobEvent[],
  options: { idPrefix: string; filterFn?: (event: JobEvent) => boolean; formatDetail?: (event: JobEvent) => string | undefined }
): UnifiedLogEvent[] {
  const filtered = options.filterFn ? events.filter(options.filterFn) : events;
  return filtered.map((event, index) => ({
    id: `${options.idPrefix}-${event.timestamp}-${index}`,
    timeMs: event.timestamp * SECONDS_TO_MS,
    level: event.level as ActivityEvent["level"],
    source,
    message: event.message,
    detail: options.formatDetail ? options.formatDetail(event) : event.path ? basename(event.path) : undefined
  }));
}

function transformUiEvents(events: ActivityEvent[]): UnifiedLogEvent[] {
  return events.map((event) => ({
    id: `ui-${event.id}`,
    timeMs: event.time,
    level: event.level,
    source: "ui",
    message: event.message,
    detail: event.detail
  }));
}

function isPerClassifierAnalysisEvent(message: string) {
  return message === "Classifier analyzed" || /\bclassification (started|completed)$/.test(message);
}

export function analysisJobRequest(job: AnalysisJobStatus) {
  if (job.adapter_name === "multi" || job.models?.length) return api.analysisJob(job.job_id);
  return api.classifierJob(job.adapter_name, job.job_id);
}

export function cancelAnalysisJob(job: AnalysisJobStatus) {
  if (job.adapter_name === "multi" || job.models?.length) return api.cancelAnalysisJob(job.job_id);
  return api.cancelClassifierJob(job.adapter_name, job.job_id);
}

function ScanProcessStatus({ job }: { job: ScanStats | null }) {
  if (!job) {
    return <div className="process-box">Сканирование не запущено</div>;
  }
  // A limited scan stops at its limit of added tracks, so that is the target.
  const total = job.limit && job.limit > 0 ? job.limit : job.total || 0;
  const processed = job.processed || 0;
  const percent = calculateProgressPercent(processed, total);
  const running = isJobActive(job.state || "");
  const etaSeconds = calculateEta(running, job.avg_seconds_per_track, total, processed);
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
        {job.skipped ? <span>skip {job.skipped}</span> : null}
        <span>fail {job.failed || 0}</span>
        <span>{job.workers || 1} поток</span>
        <span>{percent}%</span>
      </div>
      {job.avg_seconds_per_track != null && <span className="analysis-muted">{job.avg_seconds_per_track.toFixed(2)} s/file{etaSeconds ? ` · ETA ${formatEta(etaSeconds)}` : ""}</span>}
      {job.current_path && <span className="analysis-current">Сейчас: {basename(job.current_path)}</span>}
    </div>
  );
}

function UnifiedEventList({ events }: { events: UnifiedLogEvent[] }) {
  return (
    <div className="process-log">
      <div className="process-log-title">
        <span>События</span>
        <span>{events.length}</span>
      </div>
      <div className="process-log-list">
        {events.length === 0 ? (
          <span className="process-log-empty">Событий пока нет</span>
        ) : (
          events.map((event) => (
            <div className={`process-log-row ${event.level}`} key={event.id}>
              <time>{new Date(event.timeMs).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit", second: "2-digit" })}</time>
              <strong>{event.level}</strong>
              <span>[{sourceLabel(event.source)}]: {event.message}{event.detail ? ` · ${event.detail}` : ""}</span>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

function sourceLabel(source: string) {
  if (source === "validation") return "validation";
  if (source === "scan") return "scan";
  if (source === "analysis") return "analysis";
  if (source === "genre tags") return "genre tags";
  return "UI";
}

function DatabaseValidationProcessStatus({ job }: { job: DatabaseValidationJobStatus | null }) {
  if (!job) return <div className="process-box">Проверка БД не запущена</div>;
  return (
    <div className="process-box">
      <div className="process-head"><strong>{job.state}</strong><span>{job.checked} проверено</span></div>
      <div className="process-grid"><span>warn {job.warnings}</span><span>error {job.errors}</span></div>
    </div>
  );
}

export function scanSummary(job: ScanStats) {
  return `+${job.added || 0} · обновлено ${job.updated || 0} · без изменений ${job.unchanged || 0} · ошибок ${job.failed || 0}`;
}

export function stageIndicatorLabel(
  scanJob: ScanStats | null,
  analysisJob: AnalysisJobStatus | null,
  genreTagJob?: GenreTagJobStatus | null,
) {
  if (scanJob?.state && ["queued", "running"].includes(scanJob.state)) return "Идет сканирование";
  if (analysisJob?.state === "running" && analysisJob.phase === "warmup") return "Прогрев моделей";
  if (analysisJob && ["queued", "running"].includes(analysisJob.state)) return "Идет анализ";
  if (genreTagJob && ["queued", "running"].includes(genreTagJob.state)) return "Идет запись жанров";
  if (scanJob?.state === "cancelled" || analysisJob?.state === "cancelled" || genreTagJob?.state === "cancelled") return "Этап остановлен";
  return "Процесс не запущен";
}

function analysisRuntimeLabel(job: AnalysisJobStatus) {
  if (job.classifier_keys?.[0]) {
    return job.classifier_keys[0].toUpperCase();
  }
  if (job.adapter_name === "sonara" || (job.models?.length === 1 && job.models[0] === "sonara")) {
    return "SONARA";
  }
  if (job.adapter_name === "multi" || job.models?.length) {
    const audioModels = job.models?.map((model) => model.toUpperCase()).join(", ");
    const models = audioModels || "selected models";
    const current = job.current_model ? `now ${job.current_model.toUpperCase()}` : models;
    return `${current} · ${job.device || `${job.device_requested} pending`}`;
  }
  const model = job.model_name || job.adapter_name;
  return `${model} · ${job.device || `${job.device_requested} pending`}`;
}

function AnalysisWarmupStatus({ job }: { job: AnalysisJobStatus }) {
  const models = job.models || [];
  const warmed = models.findIndex((model) => model === job.current_model) + 1;
  return (
    <div className="process-box">
      <div className="process-head">
        <strong>{job.state}</strong>
        <span>Прогрев моделей</span>
      </div>
      <progress max={models.length || 1} value={warmed} />
      <div className="process-grid">
        <span>{warmed}/{models.length}</span>
        {job.current_model ? <span>{job.current_model.toUpperCase()}</span> : null}
        <span>{job.device || `${job.device_requested} pending`}</span>
      </div>
      <span className="analysis-muted">Загрузка моделей в память. Декодирование треков еще не начато.</span>
    </div>
  );
}

function AnalysisProcessStatus({ job }: { job: AnalysisJobStatus | null }) {
  if (!job) {
    return <div className="process-box">Анализ не запущен</div>;
  }
  const percent = calculateProgressPercent(job.processed, job.total);
  const running = isJobActive(job.state);
  if (running && job.phase === "warmup") {
    return <AnalysisWarmupStatus job={job} />;
  }
  const etaSeconds = calculateEta(running, job.avg_seconds_per_track, job.total, job.processed);
  const classifierJob = Boolean(job.classifier_keys?.length);
  const sonaraJob = job.adapter_name === "sonara" || (job.models?.length === 1 && job.models[0] === "sonara");
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
        {sonaraJob ? <span>SONARA {job.sonara_mode === "staged" ? "Staged" : "Direct"}</span> : null}
        {sonaraJob ? <span>BatchSize {job.sonara_batch_size || job.workers || 1}</span> : null}
        {!sonaraJob && !classifierJob ? <span>Track batch {job.track_batch_size || job.workers || 1}</span> : null}
        {!sonaraJob && !classifierJob && job.inference_batch_size ? <span>Inference batch {job.inference_batch_size}</span> : null}
        {classifierJob ? <span>classifier {job.classifier_keys?.[0] || job.adapter_name}</span> : null}
        <span>{percent}%</span>
      </div>
      {job.avg_seconds_per_track != null && <span className="analysis-muted">{job.avg_seconds_per_track.toFixed(2)} s/track{etaSeconds ? ` · ETA ${formatEta(etaSeconds)}` : ""}</span>}
      {job.model_progress && <ModelProgress job={job} />}
      {job.current_path && <span className="analysis-current">Сейчас: {basename(job.current_path)}</span>}
      {job.errors.length > 0 && <span className="analysis-error">{job.errors[0].model ? `${job.errors[0].model}: ` : ""}{job.errors[0].path}: {job.errors[0].error}</span>}
    </div>
  );
}

type ProgressItem = NonNullable<NonNullable<AnalysisJobStatus["model_progress"]>[string]>;
type ProgressRow = { key: string; label: string; item: ProgressItem };

function ModelProgress({ job }: { job: AnalysisJobStatus }) {
  const progress = job.model_progress;
  const audioRows: ProgressRow[] = AUDIO_MODELS.flatMap((model) => {
    const item = progress?.[model];
    return item ? [{ key: model, label: model.toUpperCase(), item }] : [];
  });
  const classifierRows: ProgressRow[] = Object.keys(progress || {})
    .filter((model) => !AUDIO_MODELS.includes(model as AnalysisModel))
    .flatMap((model) => {
      const item = progress?.[model];
      return item ? [{ key: model, label: model.toUpperCase(), item }] : [];
    });
  const rows = [...audioRows, ...classifierRows];
  if (!rows.length) return null;
  return (
    <div className="analysis-model-progress">
      {rows.map(({ key, label, item }) => (
        <span key={key}>
          {label} {item.processed}/{item.total} · ok {item.analyzed} · fail {item.failed}
        </span>
      ))}
    </div>
  );
}

function GenreTagProcessStatus({ job }: { job: GenreTagJobStatus | null }) {
  if (!job) {
    return <div className="process-box">Запись жанров не запущена</div>;
  }
  const percent = calculateProgressPercent(job.processed, job.total);
  const running = isJobActive(job.state);
  const etaSeconds = calculateEta(running, job.avg_seconds_per_track, job.total, job.processed);
  return (
    <div className="process-box">
      <div className="process-head">
        <strong>{job.state}</strong>
        <span>{job.processed}/{job.total} · {percent}%</span>
      </div>
      <progress value={job.processed} max={job.total || 1} />
      <div className="process-grid">
        <span>applied {job.applied}</span>
        <span>skipped {job.skipped}</span>
        <span>failed {job.failed}</span>
      </div>
      {job.avg_seconds_per_track != null && <span className="analysis-muted">{job.avg_seconds_per_track.toFixed(2)} s/track{etaSeconds ? ` · ETA ${formatEta(etaSeconds)}` : ""}</span>}
      {job.current_path && <span className="analysis-current">Сейчас: {basename(job.current_path)}</span>}
      {job.errors.length > 0 && <span className="analysis-error">{job.errors[0].path}: {job.errors[0].error}</span>}
    </div>
  );
}
