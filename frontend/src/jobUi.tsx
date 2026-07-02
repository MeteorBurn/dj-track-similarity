import { AnalysisJobStatus, AnalysisModel, api, AudioDedupJobStatus, AudioDoctorJobStatus, GenreTagJobStatus, ScanStats } from "./api";
import { basename, formatEta } from "./trackDisplay";

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
  audioDedupJob,
  audioDoctorJob,
  genreTagJob,
  events,
  className = ""
}: {
  processKind: "scan" | "analysis" | "genre_tags" | "audio_dedup" | "audio_doctor";
  scanJob: ScanStats | null;
  analysisJob: AnalysisJobStatus | null;
  audioDedupJob?: AudioDedupJobStatus | null;
  audioDoctorJob?: AudioDoctorJobStatus | null;
  genreTagJob: GenreTagJobStatus | null;
  events: ActivityEvent[];
  className?: string;
}) {
  const mergedEvents = unifiedLogEvents(scanJob, analysisJob, audioDedupJob || null, audioDoctorJob || null, genreTagJob, events);
  return (
    <section className={`log-panel ${className}`.trim()}>
      <div className="log-title">
        <span>Лог</span>
        <span>{mergedEvents.length}</span>
      </div>
      <div className="log-body">
        <ProcessStatus kind={processKind} scanJob={scanJob} analysisJob={analysisJob} audioDedupJob={audioDedupJob || null} audioDoctorJob={audioDoctorJob || null} genreTagJob={genreTagJob} />
        <UnifiedEventList events={mergedEvents} />
      </div>
    </section>
  );
}

function ProcessStatus({
  kind,
  scanJob,
  analysisJob,
  audioDedupJob,
  audioDoctorJob,
  genreTagJob
}: {
  kind: "scan" | "analysis" | "genre_tags" | "audio_dedup" | "audio_doctor";
  scanJob: ScanStats | null;
  analysisJob: AnalysisJobStatus | null;
  audioDedupJob: AudioDedupJobStatus | null;
  audioDoctorJob: AudioDoctorJobStatus | null;
  genreTagJob: GenreTagJobStatus | null;
}) {
  if (kind === "audio_doctor") {
    return <AudioDoctorProcessStatus job={audioDoctorJob} />;
  }
  if (kind === "audio_dedup") {
    return <AudioDedupProcessStatus job={audioDedupJob} />;
  }
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
  audioDedupJob: AudioDedupJobStatus | null,
  audioDoctorJob: AudioDoctorJobStatus | null,
  genreTagJob: GenreTagJobStatus | null,
  activityEvents: ActivityEvent[]
) {
  const uiEvents: UnifiedLogEvent[] = activityEvents.map((event) => ({
    id: `ui-${event.id}`,
    timeMs: event.time,
    level: event.level,
    source: "ui",
    message: event.message,
    detail: event.detail
  }));
  const scanEvents: UnifiedLogEvent[] = (scanJob?.events || []).map((event, index) => ({
    id: `scan-${event.timestamp}-${index}`,
    timeMs: event.timestamp * 1000,
    level: event.level as ActivityEvent["level"],
    source: "scan",
    message: event.message,
    detail: event.path ? basename(event.path) : undefined
  }));
  const analysisEvents: UnifiedLogEvent[] = (analysisJob?.events || [])
    .filter((event) => !isPerClassifierAnalysisEvent(event.message))
    .map((event, index) => ({
      id: `analysis-${event.timestamp}-${index}`,
      timeMs: event.timestamp * 1000,
      level: event.level as ActivityEvent["level"],
      source: "analysis",
      message: event.message,
      detail: event.path ? basename(event.path) : undefined
    }));
  const genreTagEvents: UnifiedLogEvent[] = (genreTagJob?.events || []).map((event, index) => ({
    id: `genre-tags-${event.timestamp}-${index}`,
    timeMs: event.timestamp * 1000,
    level: event.level as ActivityEvent["level"],
    source: "genre tags",
    message: event.message,
    detail: event.path ? basename(event.path) : undefined
  }));
  const audioDedupEvents: UnifiedLogEvent[] = (audioDedupJob?.events || []).map((event, index) => ({
    id: `audio-dedup-${event.timestamp}-${index}`,
    timeMs: event.timestamp * 1000,
    level: event.level as ActivityEvent["level"],
    source: "audio dedup",
    message: event.message,
    detail: event.path ? basename(event.path) : undefined
  }));
  const audioDoctorEvents: UnifiedLogEvent[] = (audioDoctorJob?.events || []).map((event, index) => ({
    id: `audio-doctor-${event.timestamp}-${index}`,
    timeMs: event.timestamp * 1000,
    level: event.level as ActivityEvent["level"],
    source: "audio doctor",
    message: event.message,
    detail: event.path ? basename(event.path) : undefined
  }));
  return [...uiEvents, ...scanEvents, ...analysisEvents, ...genreTagEvents, ...audioDedupEvents, ...audioDoctorEvents].sort((left, right) => right.timeMs - left.timeMs).slice(0, 120);
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
  const total = job.total || 0;
  const processed = job.processed || 0;
  const percent = total ? Math.round((processed / total) * 100) : 100;
  const running = ["queued", "running"].includes(job.state || "");
  const etaSeconds = running && job.avg_seconds_per_track ? Math.max(0, (total - processed) * job.avg_seconds_per_track) : null;
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
              <span>{sourceLabel(event.source)}: {event.message}{event.detail ? ` · ${event.detail}` : ""}</span>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

function sourceLabel(source: string) {
  if (source === "scan") return "scan";
  if (source === "analysis") return "analysis";
  if (source === "genre tags") return "genre tags";
  if (source === "audio dedup") return "audio dedup";
  if (source === "audio doctor") return "audio doctor";
  return "UI";
}

export function scanSummary(job: ScanStats) {
  return `+${job.added || 0} · обновлено ${job.updated || 0} · без изменений ${job.unchanged || 0} · ошибок ${job.failed || 0}`;
}

export function stageIndicatorLabel(
  scanJob: ScanStats | null,
  analysisJob: AnalysisJobStatus | null,
  genreTagJob?: GenreTagJobStatus | null,
  audioDedupJob?: AudioDedupJobStatus | null,
  audioDoctorJob?: AudioDoctorJobStatus | null
) {
  if (scanJob?.state && ["queued", "running"].includes(scanJob.state)) return "Идет сканирование";
  if (analysisJob && ["queued", "running"].includes(analysisJob.state)) return "Идет анализ";
  if (genreTagJob && ["queued", "running"].includes(genreTagJob.state)) return "Идет запись жанров";
  if (audioDedupJob && ["queued", "running"].includes(audioDedupJob.state)) return "Идет поиск дублей";
  if (audioDoctorJob && ["queued", "running"].includes(audioDoctorJob.state)) return "Идет Audio Doctor";
  if (scanJob?.state === "cancelled" || analysisJob?.state === "cancelled" || genreTagJob?.state === "cancelled" || audioDedupJob?.state === "cancelled" || audioDoctorJob?.state === "cancelled") return "Этап остановлен";
  return "Процесс не запущен";
}

function analysisRuntimeLabel(job: AnalysisJobStatus) {
  if (job.adapter_name === "multi" || job.models?.length) {
    const audioModels = job.models?.map((model) => model.toUpperCase()).join(", ");
    const classifierModels = job.classifier_keys?.length ? "CLASSIFIERS" : undefined;
    const models = audioModels || classifierModels || "selected models";
    const classifierKeySet = new Set(job.classifier_keys || []);
    const current = job.current_model
      ? classifierKeySet.has(job.current_model)
        ? "now CLASSIFIERS"
        : `now ${job.current_model.toUpperCase()}`
      : models;
    return `${current} · ${job.device || `${job.device_requested} pending`}`;
  }
  const model = job.model_name || job.adapter_name;
  return `${model} · ${job.device || `${job.device_requested} pending`}`;
}

function AnalysisProcessStatus({ job }: { job: AnalysisJobStatus | null }) {
  if (!job) {
    return <div className="process-box">Анализ не запущен</div>;
  }
  const percent = job.total ? Math.round((job.processed / job.total) * 100) : 100;
  const running = ["queued", "running"].includes(job.state);
  const etaSeconds = running && job.avg_seconds_per_track ? Math.max(0, (job.total - job.processed) * job.avg_seconds_per_track) : null;
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
        <span>tracks {job.track_batch_size || job.workers || 1}</span>
        {job.inference_batch_size ? <span>infer {job.inference_batch_size}</span> : null}
        <span>{percent}%</span>
      </div>
      {job.avg_seconds_per_track != null && <span className="analysis-muted">{job.avg_seconds_per_track.toFixed(2)} s/track{etaSeconds ? ` · ETA ${formatEta(etaSeconds)}` : ""}</span>}
      {job.current_path && <span className="analysis-current">Сейчас: {basename(job.current_path)}</span>}
      {job.model_progress && <ModelProgress job={job} />}
      {job.errors.length > 0 && <span className="analysis-error">{job.errors[0].model ? `${job.errors[0].model}: ` : ""}{job.errors[0].path}: {job.errors[0].error}</span>}
    </div>
  );
}

type ProgressItem = NonNullable<NonNullable<AnalysisJobStatus["model_progress"]>[string]>;
type ProgressRow = { key: string; label: string; item: ProgressItem };

function ModelProgress({ job }: { job: AnalysisJobStatus }) {
  const progress = job.model_progress;
  const audioModels: AnalysisModel[] = ["sonara", "maest", "mert", "muq", "clap"];
  const audioRows: ProgressRow[] = audioModels.flatMap((model) => {
    const item = progress?.[model];
    return item ? [{ key: model, label: model.toUpperCase(), item }] : [];
  });
  const classifierProgressItems = Object.keys(progress || {})
    .filter((model) => !audioModels.includes(model as AnalysisModel))
    .flatMap((model) => {
      const item = progress?.[model];
      return item ? [item] : [];
    });
  const classifierRow = classifierProgressItems.length ? classifierProgressRow(classifierProgressItems) : null;
  const rows = classifierRow ? [...audioRows, classifierRow] : audioRows;
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

function classifierProgressRow(items: ProgressItem[]): ProgressRow {
  return {
    key: "classifiers",
    label: "CLASSIFIERS",
    item: {
      total: Math.max(...items.map((item) => item.total)),
      processed: Math.min(...items.map((item) => item.processed)),
      analyzed: Math.min(...items.map((item) => item.analyzed)),
      failed: Math.max(...items.map((item) => item.failed)),
      skipped: Math.min(...items.map((item) => item.skipped))
    }
  };
}

function GenreTagProcessStatus({ job }: { job: GenreTagJobStatus | null }) {
  if (!job) {
    return <div className="process-box">Запись жанров не запущена</div>;
  }
  const percent = job.total ? Math.round((job.processed / job.total) * 100) : 100;
  const running = ["queued", "running"].includes(job.state);
  const etaSeconds = running && job.avg_seconds_per_track ? Math.max(0, (job.total - job.processed) * job.avg_seconds_per_track) : null;
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

export function AudioDedupProcessStatus({ job }: { job: AudioDedupJobStatus | null }) {
  if (!job) {
    return <div className="process-box">Audio Dedup не запущен</div>;
  }
  const percent = job.total ? Math.round((job.processed / job.total) * 100) : job.state === "completed" ? 100 : 0;
  const running = ["queued", "running"].includes(job.state);
  const etaSeconds = running && job.avg_seconds_per_item && job.total ? Math.max(0, (job.total - job.processed) * job.avg_seconds_per_item) : null;
  return (
    <div className="process-box">
      <div className="process-head">
        <strong>{job.state}</strong>
        <span>{job.current_step || job.root}</span>
      </div>
      <progress value={job.total ? job.processed : job.state === "completed" ? 1 : 0} max={job.total || 1} />
      <div className="process-grid">
        <span>{job.processed}/{job.total || 0}</span>
        <span>groups {job.groups}</span>
        <span>safe {job.safe_candidates}</span>
        {job.apply ? <span>deleted {job.deleted}</span> : null}
        {job.failed ? <span>fail {job.failed}</span> : null}
        <span>{percent}%</span>
      </div>
      {job.avg_seconds_per_item != null && <span className="analysis-muted">{job.avg_seconds_per_item.toFixed(2)} s/item{etaSeconds ? ` · ETA ${formatEta(etaSeconds)}` : ""}</span>}
      {job.current_path && <span className="analysis-current">Сейчас: {basename(job.current_path)}</span>}
      {job.errors.length > 0 && <span className="analysis-error">{job.errors[0].error}</span>}
    </div>
  );
}

export function AudioDoctorProcessStatus({ job }: { job: AudioDoctorJobStatus | null }) {
  if (!job) {
    return <div className="process-box">Audio Doctor не запущен</div>;
  }
  const percent = job.total ? Math.round((job.processed / job.total) * 100) : job.state === "completed" ? 100 : 0;
  const running = ["queued", "running"].includes(job.state);
  const etaSeconds = running && job.avg_seconds_per_item && job.total ? Math.max(0, (job.total - job.processed) * job.avg_seconds_per_item) : null;
  return (
    <div className="process-box">
      <div className="process-head">
        <strong>{job.state}</strong>
        <span>{job.current_step || job.folder || job.db_path}</span>
      </div>
      <progress value={job.total ? job.processed : job.state === "completed" ? 1 : 0} max={job.total || 1} />
      <div className="process-grid">
        <span>{job.processed}/{job.total || 0}</span>
        <span>ok {job.ok}</span>
        <span>repair {job.repairable}</span>
        {job.repaired ? <span>done {job.repaired}</span> : null}
        {job.suspicious ? <span>review {job.suspicious}</span> : null}
        {job.failed ? <span>fail {job.failed}</span> : null}
        <span>{percent}%</span>
      </div>
      {job.avg_seconds_per_item != null && <span className="analysis-muted">{job.avg_seconds_per_item.toFixed(2)} s/item{etaSeconds ? ` · ETA ${formatEta(etaSeconds)}` : ""}</span>}
      {job.current_path && <span className="analysis-current">Сейчас: {basename(job.current_path)}</span>}
      {job.errors.length > 0 && <span className="analysis-error">{job.errors[0].error}</span>}
    </div>
  );
}
