export type MLAnalysisMode = "direct" | "staged";

export type MLAnalysisSettings = {
  mode: MLAnalysisMode;
  staged: {
    folder: string;
    workers: number;
    stageSize: number;
  };
};

type StorageReader = Pick<Storage, "getItem">;
type StorageWriter = Pick<Storage, "setItem">;

export const mlAnalysisSettingsStorageKey = "dj-track-similarity.ml-analysis-settings";

export const defaultMLAnalysisSettings: MLAnalysisSettings = {
  mode: "direct",
  staged: {
    folder: "",
    workers: 4,
    stageSize: 64,
  },
};

// The staging folder is a deliberate per-session choice: it receives temporary
// read-only copies of source audio. It is never restored from storage, and a
// previously stored path is overwritten on the next save.
export function loadMLAnalysisSettings(
  storage: StorageReader | null = browserLocalStorage(),
): MLAnalysisSettings {
  if (!storage) return cloneDefaults();
  try {
    const raw = storage.getItem(mlAnalysisSettingsStorageKey);
    if (!raw) return cloneDefaults();
    const parsed = JSON.parse(raw) as Record<string, unknown>;
    const staged = objectValue(parsed.staged);
    return {
      mode: parsed.mode === "staged" ? "staged" : "direct",
      staged: {
        folder: "",
        workers: boundedInteger(staged.workers, 1, 16, 4),
        stageSize: boundedInteger(staged.stageSize, 1, 512, 64),
      },
    };
  } catch {
    return cloneDefaults();
  }
}

export function saveMLAnalysisSettings(
  settings: MLAnalysisSettings,
  storage: StorageWriter | null = browserLocalStorage(),
) {
  if (!storage) return;
  try {
    storage.setItem(
      mlAnalysisSettingsStorageKey,
      JSON.stringify({ ...settings, staged: { ...settings.staged, folder: "" } }),
    );
  } catch {
    // Persistence is optional; analysis remains available when storage is blocked.
  }
}

export function withMLStagingFolder(
  settings: MLAnalysisSettings,
  folder: string,
): MLAnalysisSettings {
  return {
    ...settings,
    staged: { ...settings.staged, folder },
  };
}

function browserLocalStorage(): Storage | null {
  try {
    return typeof localStorage === "undefined" ? null : localStorage;
  } catch {
    return null;
  }
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

function cloneDefaults(): MLAnalysisSettings {
  return {
    ...defaultMLAnalysisSettings,
    staged: { ...defaultMLAnalysisSettings.staged },
  };
}
