import { useEffect, useMemo, useState } from "react";
import { FileSpreadsheet, FolderOpen, Play, Square, X } from "lucide-react";
import type {
  AudioDedupJobPayload,
  AudioDedupJobStatus,
  AudioDedupPreset,
  EmbeddingSource
} from "./api";
import { AudioDedupProcessStatus } from "./jobUi";
import { basename } from "./trackDisplay";

export const audioDedupSourceOrder: readonly EmbeddingSource[] = ["mert", "maest", "muq", "clap"];
export const audioDedupDefaultWeights: Readonly<Record<EmbeddingSource, number>> = {
  mert: 0.43,
  maest: 0.32,
  muq: 0.12,
  clap: 0.04
};

const audioDedupSourceLabels: Record<EmbeddingSource, string> = {
  mert: "MERT",
  maest: "MAEST",
  muq: "MuQ",
  clap: "CLAP"
};
const legacySources: readonly EmbeddingSource[] = ["mert", "maest", "clap"];
const applyDeleteConfirmation = "APPLY DELETE";

const presets: Array<{ key: AudioDedupPreset; label: string; title: string }> = [
  { key: "safe", label: "Safe", title: "Conservative thresholds, lowest false-positive risk." },
  { key: "balanced", label: "Balanced", title: "Wider search scope with manual review still expected." },
  { key: "aggressive", label: "Aggressive", title: "Broadest matching; expect more manual review." }
];

type AudioDedupWeightInputs = Record<EmbeddingSource, string>;

type AudioDedupPayloadDraft = {
  root: string;
  pathContains: string[];
  sources: EmbeddingSource[];
  customWeights: boolean;
  weightInputs: AudioDedupWeightInputs;
  preset: AudioDedupPreset;
  minScore: string;
  minSimilarity: string;
  limitGroups: string;
  outDir: string;
  apply: boolean;
  confirmation: string;
};

export type AudioDedupPayloadBuildResult =
  | { ok: true; payload: AudioDedupJobPayload }
  | { ok: false; error: string };

export function buildAudioDedupJobPayload(
  draft: AudioDedupPayloadDraft
): AudioDedupPayloadBuildResult {
  const root = draft.root.trim();
  if (!root) {
    return { ok: false, error: "Укажите Root" };
  }
  if (
    draft.sources.length === 0
    || new Set(draft.sources).size !== draft.sources.length
    || draft.sources.some((source) => !audioDedupSourceOrder.includes(source))
  ) {
    return { ok: false, error: "Выберите хотя бы один уникальный evidence source" };
  }

  const sources = audioDedupSourceOrder.filter((source) => draft.sources.includes(source));
  const score = optionalNumber(draft.minScore);
  const similarity = optionalNumber(draft.minSimilarity);
  const limit = optionalInteger(draft.limitGroups);
  if (score === "invalid" || similarity === "invalid" || limit === "invalid") {
    return { ok: false, error: "Проверьте числовые поля" };
  }

  let customWeights: Partial<Record<EmbeddingSource, number>> | null = null;
  if (draft.customWeights) {
    customWeights = {};
    for (const source of sources) {
      const rawWeight = draft.weightInputs[source].trim();
      const weight = Number(rawWeight);
      if (!rawWeight || !Number.isFinite(weight) || weight < 0) {
        return {
          ok: false,
          error: `Raw weight ${audioDedupSourceLabels[source]} должен быть конечным неотрицательным числом`
        };
      }
      customWeights[source] = weight;
    }
    if (!sources.some((source) => (customWeights?.[source] ?? 0) > 0)) {
      return { ok: false, error: "Хотя бы один raw weight должен быть больше нуля" };
    }
  }

  const effectiveWeights: Partial<Record<EmbeddingSource, number>> = {};
  for (const source of sources) {
    effectiveWeights[source] = customWeights?.[source] ?? audioDedupDefaultWeights[source];
  }
  if (
    draft.apply
    && !isLegacyDeleteSafetyProfile(sources, effectiveWeights)
    && (
      !sources.includes("mert")
      || !sources.includes("maest")
      || (effectiveWeights.mert ?? 0) <= 0
      || (effectiveWeights.maest ?? 0) <= 0
    )
  ) {
    return {
      ok: false,
      error: "Non-legacy apply profile требует положительные MERT и MAEST weights; backend также проверит их независимое corroboration"
    };
  }
  if (draft.apply && draft.confirmation !== applyDeleteConfirmation) {
    return {
      ok: false,
      error: `Для apply mode нужно ввести "${applyDeleteConfirmation}"`
    };
  }

  return {
    ok: true,
    payload: {
      root,
      path_contains: draft.pathContains,
      sources,
      weights: customWeights,
      preset: draft.preset,
      min_score: score,
      min_similarity: similarity,
      limit_groups: limit,
      out_dir: draft.outDir.trim() || null,
      apply: draft.apply,
      confirmation: draft.apply ? draft.confirmation : null
    }
  };
}

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
  const [enabledSources, setEnabledSources] = useState<EmbeddingSource[]>([
    ...audioDedupSourceOrder
  ]);
  const [customWeights, setCustomWeights] = useState(false);
  const [weightInputs, setWeightInputs] = useState<AudioDedupWeightInputs>(
    defaultWeightInputs
  );
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

  function setSourceEnabled(source: EmbeddingSource, enabled: boolean) {
    setEnabledSources((current) => {
      if (enabled) {
        return audioDedupSourceOrder.filter(
          (candidate) => candidate === source || current.includes(candidate)
        );
      }
      return current.filter((candidate) => candidate !== source);
    });
    setLocalError(null);
  }

  function resetEvidenceProfile() {
    setEnabledSources([...audioDedupSourceOrder]);
    setWeightInputs(defaultWeightInputs());
    setCustomWeights(false);
    setLocalError(null);
  }

  function selectLegacyEvidenceProfile() {
    setEnabledSources([...legacySources]);
    setWeightInputs(defaultWeightInputs());
    setCustomWeights(true);
    setLocalError(null);
  }

  async function start() {
    const result = buildAudioDedupJobPayload({
      root,
      pathContains: pathContainsList,
      sources: enabledSources,
      customWeights,
      weightInputs,
      preset,
      minScore,
      minSimilarity,
      limitGroups,
      outDir,
      apply: applyMode,
      confirmation
    });
    if (!result.ok) {
      setLocalError(result.error);
      return;
    }
    setLocalError(null);
    await onStart(result.payload);
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

            <fieldset className="audio-dedup-source-controls" disabled={running}>
              <legend>Embedding evidence</legend>
              <div className="audio-dedup-source-grid">
                {audioDedupSourceOrder.map((source) => {
                  const enabled = enabledSources.includes(source);
                  return (
                    <div className={`audio-dedup-source-row ${enabled ? "enabled" : ""}`} key={source}>
                      <label className="audio-dedup-source-toggle">
                        <input
                          type="checkbox"
                          checked={enabled}
                          onChange={(event) => setSourceEnabled(source, event.target.checked)}
                          disabled={running || (enabled && enabledSources.length === 1)}
                        />
                        <span>{audioDedupSourceLabels[source]}</span>
                      </label>
                      {!enabled ? (
                        <span className="audio-dedup-default-weight">disabled</span>
                      ) : customWeights ? (
                        <label className="audio-dedup-weight-field">
                          <span>Raw weight</span>
                          <input
                            aria-label={`${audioDedupSourceLabels[source]} raw weight`}
                            value={weightInputs[source]}
                            onChange={(event) => {
                              const value = event.target.value;
                              setWeightInputs((current) => ({ ...current, [source]: value }));
                              setLocalError(null);
                            }}
                            inputMode="decimal"
                            disabled={running}
                          />
                        </label>
                      ) : (
                        <span className="audio-dedup-default-weight">
                          raw {audioDedupDefaultWeights[source]}
                        </span>
                      )}
                    </div>
                  );
                })}
              </div>
              <label className="audio-dedup-custom-weights">
                <input
                  type="checkbox"
                  checked={customWeights}
                  onChange={(event) => {
                    setCustomWeights(event.target.checked);
                    setLocalError(null);
                  }}
                  disabled={running}
                />
                <span>Custom raw weights</span>
              </label>
              <div className="audio-dedup-source-actions">
                <button
                  className="audio-dedup-reset-evidence-button"
                  type="button"
                  onClick={resetEvidenceProfile}
                  disabled={running}
                  title="Enable MERT, MAEST, MuQ and audio-to-audio CLAP with backend raw defaults."
                >
                  Reset defaults
                </button>
                <button
                  className="audio-dedup-legacy-evidence-button"
                  type="button"
                  onClick={selectLegacyEvidenceProfile}
                  disabled={running}
                  title="Exact pre-MuQ opt-out: MERT 0.43, MAEST 0.32, CLAP 0.04."
                >
                  Pre-MuQ legacy
                </button>
              </div>
              <p className="audio-dedup-evidence-note">
                Score — это weighted ranking signal, не вероятность. Для каждой пары он
                нормализуется только по доступным включённым evidence. CLAP здесь означает
                сохранённый audio-to-audio embedding, а не CLAP text search. MuQ или CLAP
                сами по себе никогда не разрешают удаление: non-legacy apply profile требует
                положительные MERT и MAEST weights, а backend отдельно проверяет их corroboration.
              </p>
            </fieldset>

            <div className="audio-dedup-grid">
              <label className="audio-dedup-field">
                <span>Min score</span>
                <input value={minScore} onChange={(event) => setMinScore(event.target.value)} inputMode="decimal" placeholder="preset" disabled={running} title="Optional override, range 0..1." />
              </label>
              <label className="audio-dedup-field">
                <span>Min similarity</span>
                <input value={minSimilarity} onChange={(event) => setMinSimilarity(event.target.value)} inputMode="decimal" placeholder="preset" disabled={running} title="Optional audio-to-audio content gate over enabled MERT/MAEST/MuQ/CLAP embeddings, range 0..1; not the lower CLAP text-search score." />
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
                <input value={confirmation} onChange={(event) => setConfirmation(event.target.value)} disabled={running} placeholder={applyDeleteConfirmation} title="Required exact confirmation for destructive apply mode." />
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
            <AudioDedupEffectiveProfile job={job} />
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

function AudioDedupEffectiveProfile({ job }: { job: AudioDedupJobStatus | null }) {
  if (!job) return null;
  return (
    <div className="audio-dedup-effective-profile" aria-label="Actual Audio Dedup sources and weights">
      <strong>Фактический evidence profile</strong>
      <span>
        Sources: {job.sources.map((source) => audioDedupSourceLabels[source]).join(", ")}
      </span>
      <span>
        Raw weights: {job.sources.map((source) => {
          const weight = job.weights[source];
          return `${audioDedupSourceLabels[source]}=${weight ?? "—"}`;
        }).join(", ")}
      </span>
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

function defaultWeightInputs(): AudioDedupWeightInputs {
  return {
    mert: String(audioDedupDefaultWeights.mert),
    maest: String(audioDedupDefaultWeights.maest),
    muq: String(audioDedupDefaultWeights.muq),
    clap: String(audioDedupDefaultWeights.clap)
  };
}

function isLegacyDeleteSafetyProfile(
  sources: EmbeddingSource[],
  weights: Partial<Record<EmbeddingSource, number>>
) {
  return (
    sources.length === legacySources.length
    && legacySources.every((source) => sources.includes(source))
    && legacySources.every((source) => weights[source] === audioDedupDefaultWeights[source])
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
