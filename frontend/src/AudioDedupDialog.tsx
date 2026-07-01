import { useEffect, useMemo, useState } from "react";
import { FileSpreadsheet, FolderOpen, Play, Square, X } from "lucide-react";
import type { AudioDedupJobPayload, AudioDedupJobStatus, AudioDedupPreset } from "./api";
import { AudioDedupProcessStatus } from "./jobUi";
import { basename } from "./trackDisplay";

const presets: Array<{ key: AudioDedupPreset; label: string; title: string }> = [
  { key: "safe", label: "Safe", title: "Conservative thresholds, lowest false-positive risk." },
  { key: "balanced", label: "Balanced", title: "Wider search scope with manual review still expected." },
  { key: "aggressive", label: "Aggressive", title: "Broadest matching; expect more manual review." }
];

export function AudioDedupDialog({
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
  job: AudioDedupJobStatus | null;
  onChooseFolder: () => Promise<string | null>;
  onStart: (payload: AudioDedupJobPayload) => Promise<void>;
  onCancelJob: () => Promise<void>;
  onOpenXlsx: () => void;
  onClose: () => void;
}) {
  const [root, setRoot] = useState(defaultRoot);
  const [pathContains, setPathContains] = useState("");
  const [preset, setPreset] = useState<AudioDedupPreset>("safe");
  const [minScore, setMinScore] = useState("");
  const [minSimilarity, setMinSimilarity] = useState("");
  const [limitGroups, setLimitGroups] = useState("");
  const [outDir, setOutDir] = useState("");
  const [applyMode, setApplyMode] = useState(false);
  const [confirmation, setConfirmation] = useState("");
  const [localError, setLocalError] = useState<string | null>(null);
  const running = Boolean(job && ["queued", "running"].includes(job.state));
  const completedWithReport = Boolean(job?.state === "completed" && job.xlsx_path);
  const pathContainsList = useMemo(() => splitPathContains(pathContains), [pathContains]);

  useEffect(() => {
    if (!root && defaultRoot) setRoot(defaultRoot);
  }, [defaultRoot, root]);

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape" && !running) onClose();
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose, running]);

  async function chooseRoot() {
    const selected = await onChooseFolder();
    if (selected) setRoot(selected);
  }

  async function chooseOutDir() {
    const selected = await onChooseFolder();
    if (selected) setOutDir(selected);
  }

  async function start() {
    const trimmedRoot = root.trim();
    if (!trimmedRoot) {
      setLocalError("Укажите Root");
      return;
    }
    const score = optionalNumber(minScore);
    const similarity = optionalNumber(minSimilarity);
    const limit = optionalInteger(limitGroups);
    if (score === "invalid" || similarity === "invalid" || limit === "invalid") {
      setLocalError("Проверьте числовые поля");
      return;
    }
    if (applyMode && confirmation.trim() !== "APPLY DELETE") {
      setLocalError('Для apply mode нужно ввести "APPLY DELETE"');
      return;
    }
    setLocalError(null);
    await onStart({
      root: trimmedRoot,
      path_contains: pathContainsList,
      preset,
      min_score: score,
      min_similarity: similarity,
      limit_groups: limit,
      out_dir: outDir.trim() || null,
      apply: applyMode,
      confirmation: applyMode ? confirmation.trim() : null
    });
  }

  return (
    <div className="audio-dedup-backdrop" onClick={running ? undefined : onClose}>
      <section className="audio-dedup-dialog" role="dialog" aria-modal="true" aria-labelledby="audio-dedup-title" onClick={(event) => event.stopPropagation()}>
        <div className="dialog-title audio-dedup-title">
          <div>
            <h2 id="audio-dedup-title">Audio Dedup</h2>
            <span>{databasePath || "SQLite база не выбрана"}</span>
          </div>
          <button className="icon-button close-audio-dedup-dialog-button" title="Закрыть" aria-label="Закрыть Audio Dedup" onClick={onClose} disabled={running} type="button">
            <X size={16} />
          </button>
        </div>

        <div className="audio-dedup-content">
          <section className="audio-dedup-settings" aria-label="Audio Dedup settings">
            <label className="audio-dedup-field">
              <span>Root</span>
              <div className="audio-dedup-path-row">
                <input value={root} onChange={(event) => setRoot(event.target.value)} disabled={running} title="Stored path root. Only DB tracks inside this root are considered." />
                <button className="icon-button folder-picker audio-dedup-root-picker-button" title="Выбрать root" aria-label="Выбрать root" onClick={() => void chooseRoot()} disabled={running} type="button">
                  <FolderOpen size={15} />
                </button>
              </div>
            </label>

            <label className="audio-dedup-field">
              <span>Path contains</span>
              <textarea value={pathContains} onChange={(event) => setPathContains(event.target.value)} disabled={running} placeholder="one filter per line" title="Optional case-insensitive path filters. Split by lines, comma, or semicolon." />
            </label>

            <div className="audio-dedup-field">
              <span>Preset</span>
              <div className="audio-dedup-segmented">
                {presets.map((item) => (
                  <button key={item.key} className={`audio-dedup-preset-button ${preset === item.key ? "active" : ""}`} title={item.title} onClick={() => setPreset(item.key)} disabled={running} type="button">
                    {item.label}
                  </button>
                ))}
              </div>
            </div>

            <div className="audio-dedup-grid">
              <label className="audio-dedup-field">
                <span>Min score</span>
                <input value={minScore} onChange={(event) => setMinScore(event.target.value)} inputMode="decimal" placeholder="preset" disabled={running} title="Optional override, range 0..1." />
              </label>
              <label className="audio-dedup-field">
                <span>Min similarity</span>
                <input value={minSimilarity} onChange={(event) => setMinSimilarity(event.target.value)} inputMode="decimal" placeholder="preset" disabled={running} title="Optional audio-to-audio content gate over MERT/MAEST/CLAP embeddings, range 0..1; not the lower CLAP text-search score." />
              </label>
              <label className="audio-dedup-field">
                <span>Limit groups</span>
                <input value={limitGroups} onChange={(event) => setLimitGroups(event.target.value)} inputMode="numeric" placeholder="all" disabled={running} title="Optional maximum number of duplicate groups to write." />
              </label>
            </div>

            <label className="audio-dedup-field">
              <span>Output dir</span>
              <div className="audio-dedup-path-row">
                <input value={outDir} onChange={(event) => setOutDir(event.target.value)} disabled={running} placeholder="tools/audio-dedup/data/reports" title="Optional report output directory." />
                <button className="icon-button folder-picker audio-dedup-out-picker-button" title="Выбрать output dir" aria-label="Выбрать output dir" onClick={() => void chooseOutDir()} disabled={running} type="button">
                  <FolderOpen size={15} />
                </button>
              </div>
            </label>

            <label className="audio-dedup-apply">
              <input type="checkbox" checked={applyMode} onChange={(event) => setApplyMode(event.target.checked)} disabled={running} />
              <span>Apply delete safe candidates</span>
            </label>

            {applyMode ? (
              <label className="audio-dedup-field">
                <span>Confirmation</span>
                <input value={confirmation} onChange={(event) => setConfirmation(event.target.value)} disabled={running} placeholder="APPLY DELETE" title="Required exact confirmation for destructive apply mode." />
              </label>
            ) : null}

            {localError ? <div className="audio-dedup-error">{localError}</div> : null}

            <div className="audio-dedup-actions">
              <button className="audio-dedup-start-button" title="Start duplicate search" onClick={() => void start()} disabled={running || !databasePath} type="button">
                <Play size={15} />
                Start
              </button>
              <button className="audio-dedup-cancel-button stop-button" title="Stop current Audio Dedup job" onClick={() => void onCancelJob()} disabled={!running} type="button">
                <Square size={15} />
                Stop
              </button>
            </div>
          </section>

          <section className="audio-dedup-run" aria-label="Audio Dedup run status">
            <AudioDedupProcessStatus job={job} />
            {completedWithReport ? (
              <div className="audio-dedup-report-ready">
                <div>
                  <strong>XLSX готов</strong>
                  <span>{job?.xlsx_path ? basename(job.xlsx_path) : ""}</span>
                </div>
                <button className="audio-dedup-open-xlsx-button" onClick={onOpenXlsx} title="Открыть XLSX отчёт" type="button">
                  <FileSpreadsheet size={15} />
                  Open XLSX
                </button>
              </div>
            ) : null}
            <AudioDedupEventLog job={job} />
          </section>
        </div>
      </section>
    </div>
  );
}

function AudioDedupEventLog({ job }: { job: AudioDedupJobStatus | null }) {
  const events = job?.events || [];
  return (
    <div className="process-log audio-dedup-log">
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

function splitPathContains(value: string) {
  return value
    .split(/[\n,;]+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function optionalNumber(value: string): number | null | "invalid" {
  const trimmed = value.trim();
  if (!trimmed) return null;
  const parsed = Number(trimmed);
  return Number.isFinite(parsed) && parsed >= 0 && parsed <= 1 ? parsed : "invalid";
}

function optionalInteger(value: string): number | null | "invalid" {
  const trimmed = value.trim();
  if (!trimmed) return null;
  const parsed = Number(trimmed);
  return Number.isInteger(parsed) && parsed >= 1 ? parsed : "invalid";
}
