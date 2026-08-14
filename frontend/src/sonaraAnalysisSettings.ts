export type SonaraAnalysisMode = "direct" | "staged";

export type SonaraAnalysisSettings = {
  mode: SonaraAnalysisMode;
  directBatchSize: number;
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

export const defaultSonaraAnalysisSettings: SonaraAnalysisSettings = {
  mode: "direct",
  directBatchSize: 8,
  staged: {
    folder: "",
    processes: 4,
    threads: 4,
    batchSize: 4,
    stageSize: 32,
  },
};

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
      staged: {
        folder: typeof staged.folder === "string" ? staged.folder : "",
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
    storage.setItem(sonaraAnalysisSettingsStorageKey, JSON.stringify(settings));
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
