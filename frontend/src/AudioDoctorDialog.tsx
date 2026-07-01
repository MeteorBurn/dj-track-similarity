import { useEffect, useMemo, useState } from "react";
import { FileSpreadsheet, FolderOpen, Play, Square, X } from "lucide-react";
import type { AudioDoctorJobPayload, AudioDoctorJobStatus, AudioDoctorKeepId3, AudioDoctorSourceMode } from "./api";
import { AudioDoctorProcessStatus } from "./jobUi";
import { basename } from "./trackDisplay";

const keepId3Options: Array<{ key: AudioDoctorKeepId3; label: string; title: string }> = [
  { key: "first", label: "First", title: "Purpose: keep the first readable top-level WAV ID3 chunk. Type: option. Range: first/last/none." },
  { key: "last", label: "Last", title: "Purpose: keep the last readable top-level WAV ID3 chunk. Type: option. Range: first/last/none." },
  { key: "none", label: "None", title: "Purpose: remove all top-level WAV ID3 chunks during repair. Type: option. Range: first/last/none." }
];

export function AudioDoctorDialog({
  databasePath,
  defaultRoot,
  job,
  onChooseFolder,
  onStart,
  onCancelJob,
  onOpenXlsx,
  onClose
}: {
  databasePath: string | null;
  defaultRoot: string;
  job: AudioDoctorJobStatus | null;
  onChooseFolder: () => Promise<string | null>;
  onStart: (payload: AudioDoctorJobPayload) => Promise<void>;
  onCancelJob: () => Promise<void>;
  onOpenXlsx: () => void;
  onClose: () => void;
}) {
  const [sourceMode, setSourceMode] = useState<AudioDoctorSourceMode>("db");
  const [folder, setFolder] = useState(defaultRoot);
  const [dbRoots, setDbRoots] = useState("");
  const [fileRoot, setFileRoot] = useState("");
  const [keepId3, setKeepId3] = useState<AudioDoctorKeepId3>("first");
  const [workers, setWorkers] = useState("1");
  const [limit, setLimit] = useState("");
  const [reason, setReason] = useState("");
  const [outDir, setOutDir] = useState("");
  const [statePath, setStatePath] = useState("");
  const [applyMode, setApplyMode] = useState(false);
  const [confirmation, setConfirmation] = useState("");
  const [localError, setLocalError] = useState<string | null>(null);
  const running = Boolean(job && ["queued", "running"].includes(job.state));
  const completedWithReport = Boolean(job?.state === "completed" && job.xlsx_path);
  const dbRootList = useMemo(() => splitList(dbRoots), [dbRoots]);
  const reasonList = useMemo(() => splitList(reason).map((item) => item.toUpperCase()), [reason]);

  useEffect(() => {
    if (!folder && defaultRoot) setFolder(defaultRoot);
  }, [defaultRoot, folder]);

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape" && !running) onClose();
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose, running]);

  async function chooseFolder() {
    const selected = await onChooseFolder();
    if (selected) setFolder(selected);
  }

  async function chooseFileRoot() {
    const selected = await onChooseFolder();
    if (selected) setFileRoot(selected);
  }

  async function chooseOutDir() {
    const selected = await onChooseFolder();
    if (selected) setOutDir(selected);
  }

  async function start() {
    const selectedWorkers = optionalInteger(workers);
    const selectedLimit = optionalInteger(limit);
    if (selectedWorkers === "invalid" || selectedLimit === "invalid") {
      setLocalError("Проверьте числовые поля");
      return;
    }
    if (sourceMode === "folder" && !folder.trim()) {
      setLocalError("Укажите Folder");
      return;
    }
    if (fileRoot.trim() && dbRootList.length === 0) {
      setLocalError("File root требует хотя бы один DB root");
      return;
    }
    if (applyMode && confirmation.trim() !== "APPLY REPAIR") {
      setLocalError('Для apply mode нужно ввести "APPLY REPAIR"');
      return;
    }
    setLocalError(null);
    await onStart({
      source_mode: sourceMode,
      folder: sourceMode === "folder" ? folder.trim() : null,
      db_roots: dbRootList,
      file_root: fileRoot.trim() || null,
      keep_id3: keepId3,
      workers: selectedWorkers ?? 1,
      limit: selectedLimit,
      reasons: reasonList,
      out_dir: outDir.trim() || null,
      state_path: statePath.trim() || null,
      apply: applyMode,
      confirmation: applyMode ? confirmation.trim() : null
    });
  }

  return (
    <div className="audio-doctor-backdrop" onClick={running ? undefined : onClose}>
      <section className="audio-doctor-dialog" role="dialog" aria-modal="true" aria-labelledby="audio-doctor-title" onClick={(event) => event.stopPropagation()}>
        <div className="dialog-title audio-doctor-title">
          <div>
            <h2 id="audio-doctor-title">Audio Doctor</h2>
            <span>{sourceMode === "db" ? databasePath || "SQLite база не выбрана" : folder || "Folder не выбран"}</span>
          </div>
          <button className="icon-button close-audio-doctor-dialog-button" title="Закрыть Audio Doctor" aria-label="Закрыть Audio Doctor" onClick={onClose} disabled={running} type="button">
            <X size={16} />
          </button>
        </div>

        <div className="audio-doctor-content">
          <section className="audio-doctor-settings" aria-label="Audio Doctor settings">
            <div className="audio-doctor-field">
              <span>Source</span>
              <div className="audio-doctor-segmented">
                <button className={`audio-doctor-source-button ${sourceMode === "db" ? "active" : ""}`} title="Purpose: read tracks.path from the selected SQLite database. Type: mode. Range: Selected DB or Folder." onClick={() => setSourceMode("db")} disabled={running} type="button">Selected DB</button>
                <button className={`audio-doctor-source-button ${sourceMode === "folder" ? "active" : ""}`} title="Purpose: scan a filesystem folder recursively for supported audio files. Type: mode. Range: Selected DB or Folder." onClick={() => setSourceMode("folder")} disabled={running} type="button">Folder</button>
              </div>
            </div>

            {sourceMode === "folder" ? (
              <label className="audio-doctor-field">
                <span>Folder</span>
                <div className="audio-doctor-path-row">
                  <input value={folder} onChange={(event) => setFolder(event.target.value)} disabled={running} title="Purpose: folder to inspect recursively. Type: Windows path. Range: existing music folder." />
                  <button className="icon-button folder-picker audio-doctor-folder-picker-button" title="Выбрать folder" aria-label="Выбрать folder" onClick={() => void chooseFolder()} disabled={running} type="button">
                    <FolderOpen size={15} />
                  </button>
                </div>
              </label>
            ) : (
              <label className="audio-doctor-field">
                <span>DB roots</span>
                <textarea value={dbRoots} onChange={(event) => setDbRoots(event.target.value)} disabled={running} placeholder="one stored root per line" title="Purpose: optionally restrict selected DB tracks to stored roots. Type: path list. Range: one root per line, comma, or semicolon." />
              </label>
            )}

            <label className="audio-doctor-field">
              <span>File root</span>
              <div className="audio-doctor-path-row">
                <input value={fileRoot} onChange={(event) => setFileRoot(event.target.value)} disabled={running || sourceMode !== "db"} placeholder="optional remap target" title="Purpose: replace matching DB root before filesystem checks. Type: Windows path. Range: requires DB roots." />
                <button className="icon-button folder-picker audio-doctor-file-root-picker-button" title="Выбрать file root" aria-label="Выбрать file root" onClick={() => void chooseFileRoot()} disabled={running || sourceMode !== "db"} type="button">
                  <FolderOpen size={15} />
                </button>
              </div>
            </label>

            <div className="audio-doctor-field">
              <span>keep-id3</span>
              <div className="audio-doctor-segmented">
                {keepId3Options.map((item) => (
                  <button key={item.key} className={`audio-doctor-keep-id3-button ${keepId3 === item.key ? "active" : ""}`} title={item.title} onClick={() => setKeepId3(item.key)} disabled={running} type="button">
                    {item.label}
                  </button>
                ))}
              </div>
            </div>

            <div className="audio-doctor-grid">
              <label className="audio-doctor-field">
                <span>Workers</span>
                <input value={workers} onChange={(event) => setWorkers(event.target.value)} inputMode="numeric" disabled={running || applyMode} title="Purpose: parallel dry-run workers. Type: integer. Range: 1..32; apply always runs sequentially." />
              </label>
              <label className="audio-doctor-field">
                <span>Limit</span>
                <input value={limit} onChange={(event) => setLimit(event.target.value)} inputMode="numeric" placeholder="all" disabled={running} title="Purpose: process only the first N pending files. Type: integer. Range: blank or 1+." />
              </label>
              <label className="audio-doctor-field">
                <span>Reason</span>
                <input value={reason} onChange={(event) => setReason(event.target.value)} placeholder="OVERSIZED_DATA" disabled={running} title="Purpose: process only state entries with matching reason. Type: reason code list. Range: blank or exact report reasons." />
              </label>
            </div>

            <label className="audio-doctor-field">
              <span>Output dir</span>
              <div className="audio-doctor-path-row">
                <input value={outDir} onChange={(event) => setOutDir(event.target.value)} disabled={running} placeholder="tools/audio-doctor/data/reports" title="Purpose: optional report output directory. Type: Windows path. Range: blank for default or writable folder." />
                <button className="icon-button folder-picker audio-doctor-out-picker-button" title="Выбрать output dir" aria-label="Выбрать output dir" onClick={() => void chooseOutDir()} disabled={running} type="button">
                  <FolderOpen size={15} />
                </button>
              </div>
            </label>

            <label className="audio-doctor-field">
              <span>State path</span>
              <input value={statePath} onChange={(event) => setStatePath(event.target.value)} disabled={running} placeholder="derived from source" title="Purpose: optional state JSON path for repeat dry-run/apply workflows. Type: file path. Range: blank for derived path." />
            </label>

            <label className="audio-doctor-apply">
              <input type="checkbox" checked={applyMode} onChange={(event) => setApplyMode(event.target.checked)} disabled={running} title="Purpose: enable repair writes after a dry-run state exists. Type: boolean. Range: off/on." />
              <span>Apply repairable state entries</span>
            </label>

            {applyMode ? (
              <label className="audio-doctor-field">
                <span>Confirmation</span>
                <input value={confirmation} onChange={(event) => setConfirmation(event.target.value)} disabled={running} placeholder="APPLY REPAIR" title="Purpose: exact confirmation for file-writing repair mode. Type: text. Range: APPLY REPAIR." />
              </label>
            ) : null}

            {localError ? <div className="audio-doctor-error">{localError}</div> : null}

            <div className="audio-doctor-actions">
              <button className="audio-doctor-start-button" title="Start Audio Doctor" onClick={() => void start()} disabled={running || (sourceMode === "db" && !databasePath)} type="button">
                <Play size={15} />
                Start
              </button>
              <button className="audio-doctor-cancel-button stop-button" title="Stop current Audio Doctor job" onClick={() => void onCancelJob()} disabled={!running} type="button">
                <Square size={15} />
                Stop
              </button>
            </div>
          </section>

          <section className="audio-doctor-run" aria-label="Audio Doctor run status">
            <AudioDoctorProcessStatus job={job} />
            {completedWithReport ? (
              <div className="audio-doctor-report-ready">
                <div>
                  <strong>XLSX готов</strong>
                  <span>{job?.xlsx_path ? basename(job.xlsx_path) : ""}</span>
                </div>
                <button className="audio-doctor-open-xlsx-button" onClick={onOpenXlsx} title="Открыть XLSX отчёт" type="button">
                  <FileSpreadsheet size={15} />
                  Open XLSX
                </button>
              </div>
            ) : null}
            <AudioDoctorEventLog job={job} />
          </section>
        </div>
      </section>
    </div>
  );
}

function AudioDoctorEventLog({ job }: { job: AudioDoctorJobStatus | null }) {
  const events = job?.events || [];
  return (
    <div className="process-log audio-doctor-log">
      <div className="process-log-title">
        <span>Log</span>
        <span>{events.length}</span>
      </div>
      <div className="process-log-list">
        {events.length === 0 ? (
          <span className="process-log-empty">Событий пока нет</span>
        ) : (
          events.slice().reverse().map((event, index) => (
            <div className={`process-log-row ${event.level}`} key={`${event.timestamp}-${index}`}>
              <time>{new Date(event.timestamp * 1000).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit", second: "2-digit" })}</time>
              <strong>{event.level}</strong>
              <span>{event.message}{event.path ? ` · ${basename(event.path)}` : ""}</span>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

function splitList(value: string) {
  return value
    .split(/[\n,;]+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function optionalInteger(value: string): number | null | "invalid" {
  const trimmed = value.trim();
  if (!trimmed) return null;
  const parsed = Number(trimmed);
  return Number.isInteger(parsed) && parsed >= 1 ? parsed : "invalid";
}
