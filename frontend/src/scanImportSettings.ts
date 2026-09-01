export type ScanImportSettings = {
  root: string;
  selectedFormats: string[];
  minDurationSeconds: string;
  maxDurationSeconds: string;
  workers: number;
};

type StorageReader = Pick<Storage, "getItem">;
type StorageWriter = Pick<Storage, "setItem">;

export const scanImportSettingsStorageKey = "dj-track-similarity.scan-import-settings";

export const scanFormats = [
  { key: "aac", label: "AAC", extensions: [".aac"] },
  { key: "aif", label: "AIF", extensions: [".aif"] },
  { key: "aiff", label: "AIFF", extensions: [".aiff"] },
  { key: "alac", label: "ALAC", extensions: [".alac"] },
  { key: "ape", label: "APE", extensions: [".ape"] },
  { key: "flac", label: "FLAC", extensions: [".flac"] },
  { key: "m4a", label: "M4A", extensions: [".m4a"] },
  { key: "mp3", label: "MP3", extensions: [".mp3"] },
  { key: "ogg", label: "OGG", extensions: [".ogg"] },
  { key: "opus", label: "OPUS", extensions: [".opus"] },
  { key: "wav", label: "WAV", extensions: [".wav"] },
  { key: "wave", label: "WAVE", extensions: [".wave"] },
  { key: "wma", label: "WMA", extensions: [".wma"] },
  { key: "wv", label: "WavPack", extensions: [".wv"] },
] as const;

export function defaultScanImportSettings(): ScanImportSettings {
  return {
    root: "",
    selectedFormats: scanFormats.map((format) => format.key),
    minDurationSeconds: "120",
    maxDurationSeconds: "1200",
    workers: 8,
  };
}

// Mirrors ScanRequest's optional bound fields: an empty or non-positive value
// means "no bound" rather than zero.
export function boundScanDuration(value: string): number | undefined {
  if (!value.trim()) return undefined;
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : undefined;
}

export function scanExtensionsFor(selectedFormats: readonly string[]): string[] {
  return scanFormats
    .filter((format) => selectedFormats.includes(format.key))
    .flatMap((format) => format.extensions);
}

// The source folder is a deliberate per-session choice, the same rule the
// SONARA/ML staging folders already follow: never restored from storage, and
// a previously stored path is overwritten on the next save.
export function loadScanImportSettings(
  storage: StorageReader | null = browserLocalStorage(),
): ScanImportSettings {
  if (!storage) return cloneDefaults();
  try {
    const raw = storage.getItem(scanImportSettingsStorageKey);
    if (!raw) return cloneDefaults();
    const parsed = JSON.parse(raw) as Record<string, unknown>;
    const storedFormats = Array.isArray(parsed.selectedFormats)
      ? parsed.selectedFormats.filter(
        (key): key is string => typeof key === "string" && scanFormats.some((format) => format.key === key),
      )
      : [];
    return {
      root: "",
      selectedFormats: storedFormats.length ? storedFormats : scanFormats.map((format) => format.key),
      minDurationSeconds: typeof parsed.minDurationSeconds === "string" ? parsed.minDurationSeconds : "120",
      maxDurationSeconds: typeof parsed.maxDurationSeconds === "string" ? parsed.maxDurationSeconds : "1200",
      workers: boundedInteger(parsed.workers, 1, 64, 8),
    };
  } catch {
    return cloneDefaults();
  }
}

export function saveScanImportSettings(
  settings: ScanImportSettings,
  storage: StorageWriter | null = browserLocalStorage(),
) {
  if (!storage) return;
  try {
    storage.setItem(scanImportSettingsStorageKey, JSON.stringify({ ...settings, root: "" }));
  } catch {
    // Persistence is optional; loading tracks remains available when storage is blocked.
  }
}

function browserLocalStorage(): Storage | null {
  try {
    return typeof localStorage === "undefined" ? null : localStorage;
  } catch {
    return null;
  }
}

function boundedInteger(value: unknown, minimum: number, maximum: number, fallback: number) {
  const integer = Math.trunc(Number(value));
  return Number.isFinite(integer) ? Math.min(maximum, Math.max(minimum, integer)) : fallback;
}

function cloneDefaults(): ScanImportSettings {
  return { ...defaultScanImportSettings() };
}
