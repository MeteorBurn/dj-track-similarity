export type SonaraAnalysisMode = "direct" | "staged";

export type SonaraAnalysisSettings = {
  mode: SonaraAnalysisMode;
  directBatchSize: number;
  bpmMin: number;
  bpmMax: number;
  staged: {
    folder: string;
    processes: number;
    threads: number;
    batchSize: number;
    stageSize: number;
  };
};

type StorageReader = Pick<Storage, "getItem">;
type StorageWriter = Pick<Storage, "setItem">;

export const sonaraAnalysisSettingsStorageKey = "dj-track-similarity.sonara-analysis-settings";

// Matches the backend default analysis range (Rekordbox 70-180).
export const defaultSonaraBpmMin = 70;
export const defaultSonaraBpmMax = 180;
export const minSonaraBpm = 20;
export const maxSonaraBpm = 400;

export const defaultSonaraAnalysisSettings: SonaraAnalysisSettings = {
  mode: "direct",
  directBatchSize: 8,
  bpmMin: defaultSonaraBpmMin,
  bpmMax: defaultSonaraBpmMax,
  staged: {
    folder: "",
    processes: 4,
    threads: 4,
    batchSize: 4,
    stageSize: 32,
  },
};

// The staging folder is a deliberate per-session choice: it receives temporary
// read-only copies of source audio. It is never restored from storage, and a
// previously stored path is overwritten on the next save.
export function loadSonaraAnalysisSettings(
  storage: StorageReader | null = browserLocalStorage(),
): SonaraAnalysisSettings {
  if (!storage) return cloneDefaults();
  try {
    const raw = storage.getItem(sonaraAnalysisSettingsStorageKey);
    if (!raw) return cloneDefaults();
    const parsed = JSON.parse(raw) as Record<string, unknown>;
    const staged = objectValue(parsed.staged);
    return {
      mode: parsed.mode === "staged" ? "staged" : "direct",
      directBatchSize: boundedInteger(parsed.directBatchSize, 1, 16, 8),
      ...boundedBpmRange(parsed.bpmMin, parsed.bpmMax),
      staged: {
        folder: "",
        processes: boundedInteger(staged.processes, 1, 16, 4),
        threads: boundedInteger(staged.threads, 1, 64, 4),
        batchSize: boundedInteger(staged.batchSize, 1, 16, 4),
        stageSize: boundedInteger(staged.stageSize, 1, 512, 32),
      },
    };
  } catch {
    return cloneDefaults();
  }
}

export function saveSonaraAnalysisSettings(
  settings: SonaraAnalysisSettings,
  storage: StorageWriter | null = browserLocalStorage(),
) {
  if (!storage) return;
  try {
    storage.setItem(
      sonaraAnalysisSettingsStorageKey,
      JSON.stringify({ ...settings, staged: { ...settings.staged, folder: "" } }),
    );
  } catch {
    // Persistence is optional; analysis remains available when storage is blocked.
  }
}

function browserLocalStorage(): Storage | null {
  try {
    return typeof localStorage === "undefined" ? null : localStorage;
  } catch {
    return null;
  }
}

export type SonaraBpmPreset = {
  key: string;
  label: string;
  bpmMin: number;
  bpmMax: number;
};

// Ranges the common DJ tools analyse with. Every pair spans a full octave, so
// each tempo folds into it exactly once — the rule the stored Core row enforces.
export const sonaraBpmPresets: readonly SonaraBpmPreset[] = [
  { key: "rekordbox", label: "Rekordbox", bpmMin: 70, bpmMax: 180 },
  { key: "virtual-dj", label: "VirtualDJ", bpmMin: 80, bpmMax: 240 },
  { key: "mixed-in-key", label: "Mixed In Key", bpmMin: 79, bpmMax: 192 },
];

export function matchingSonaraBpmPreset(
  range: { bpmMin: number; bpmMax: number },
): SonaraBpmPreset | null {
  return sonaraBpmPresets.find(
    (preset) => preset.bpmMin === range.bpmMin && preset.bpmMax === range.bpmMax,
  ) ?? null;
}

// Keep the pair valid while one end is edited, so the panel cannot submit a
// range the backend would reject. Editing one bound pushes the other just far
// enough to preserve the octave rule.
export function applySonaraBpmChange(
  current: { bpmMin: number; bpmMax: number },
  change: { bpmMin?: number; bpmMax?: number },
): { bpmMin: number; bpmMax: number } {
  if (change.bpmMin !== undefined) {
    const bpmMin = clamp(change.bpmMin, minSonaraBpm, Math.floor(maxSonaraBpm / 2));
    return { bpmMin, bpmMax: Math.max(current.bpmMax, 2 * bpmMin) };
  }
  if (change.bpmMax !== undefined) {
    const bpmMax = clamp(change.bpmMax, 2 * minSonaraBpm, maxSonaraBpm);
    return { bpmMin: Math.min(current.bpmMin, Math.floor(bpmMax / 2)), bpmMax };
  }
  return { ...current };
}

function clamp(value: number, minimum: number, maximum: number) {
  return Math.min(maximum, Math.max(minimum, value));
}

// A stored pair that no longer satisfies the octave rule would be rejected by
// the backend, so fall back to the default range instead of loading it.
export function boundedBpmRange(
  rawMin: unknown,
  rawMax: unknown,
): { bpmMin: number; bpmMax: number } {
  const bpmMin = boundedNumber(rawMin, minSonaraBpm, maxSonaraBpm, defaultSonaraBpmMin);
  const bpmMax = boundedNumber(rawMax, minSonaraBpm, maxSonaraBpm, defaultSonaraBpmMax);
  if (bpmMax < 2 * bpmMin) {
    return { bpmMin: defaultSonaraBpmMin, bpmMax: defaultSonaraBpmMax };
  }
  return { bpmMin, bpmMax };
}

function boundedNumber(
  value: unknown,
  minimum: number,
  maximum: number,
  fallback: number,
) {
  const parsed = Number(value);
  return Number.isFinite(parsed)
    ? Math.min(maximum, Math.max(minimum, parsed))
    : fallback;
}

function objectValue(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" ? value as Record<string, unknown> : {};
}

function boundedInteger(
  value: unknown,
  minimum: number,
  maximum: number,
  fallback: number,
) {
  const integer = Math.trunc(Number(value));
  return Number.isFinite(integer)
    ? Math.min(maximum, Math.max(minimum, integer))
    : fallback;
}

function cloneDefaults(): SonaraAnalysisSettings {
  return {
    ...defaultSonaraAnalysisSettings,
    staged: { ...defaultSonaraAnalysisSettings.staged },
  };
}
