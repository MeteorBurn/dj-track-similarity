import type {
  EmbeddingSource,
  HybridSearchPayload,
  HybridSearchSource,
  SetBuilderBpmChange,
  SetBuilderBpmMode,
  SetBuilderClassifierFlow,
  SetBuilderEnergyCurve,
  SetBuilderGeneratePayload,
  SetBuilderMode,
  SetBuilderSeedMode
} from "./api";

export type PrimarySearchTab = "set" | "sonara" | "mert" | "muq" | "clap" | "class" | "lab";
export type GenericSearchTab = Extract<PrimarySearchTab, "sonara" | "mert" | "muq" | "clap">;
export type SetWorkflowTab = "builder" | "hybrid";
export type TabNavigationKey = "ArrowLeft" | "ArrowRight" | "Home" | "End";

export const primarySearchTabs: readonly PrimarySearchTab[] = [
  "set",
  "lab",
  "sonara",
  "mert",
  "muq",
  "clap",
  "class"
];

export const setWorkflowTabs: readonly SetWorkflowTab[] = ["builder", "hybrid"];
export const setSourceOrder: readonly EmbeddingSource[] = ["mert", "maest", "muq", "clap"];
export const hybridSourceOrder: readonly HybridSearchSource[] = ["mert", "maest", "muq", "sonara", "clap"];

export const setDefaultRawWeights: Readonly<Record<EmbeddingSource | "sonara_broad", number>> = {
  mert: 0.3,
  maest: 0.18,
  muq: 0.15,
  clap: 0.22,
  sonara_broad: 0.3
};

export type SetBuilderDraft = {
  databasePath: string | null;
  databaseIdentity: string | null;
  seedMode: SetBuilderSeedMode;
  seedTrackIds: number[];
  autoSeedCount: number;
  sources: Record<EmbeddingSource, boolean>;
  useCustomWeights: boolean;
  weights: Record<EmbeddingSource | "sonara_broad", number>;
  mode: SetBuilderMode;
  limit: number;
  diversity: number;
  energyCurve: SetBuilderEnergyCurve;
  bpmMode: SetBuilderBpmMode;
  bpmChange: SetBuilderBpmChange;
  bpmStart?: number;
  bpmTarget?: number;
  classifierPreferences: Record<string, number>;
  classifierFlows: Record<string, SetBuilderClassifierFlow>;
  randomSeed?: number;
};

export type HybridDraft = {
  databasePath: string | null;
  databaseIdentity: string | null;
  seedTrackIds: number[];
  sources: Record<HybridSearchSource, boolean>;
  useCustomWeights: boolean;
  weights: Record<HybridSearchSource, number>;
  perSource: number;
  limit: number;
  transitionRiskWeight: number;
  classifierPreferences: Record<string, number>;
  classifierRiskWeights: Record<string, number>;
};

export type PayloadResult<T> =
  | { ok: true; payload: T }
  | { ok: false; error: string };

export type RequestTokenGuard = {
  begin: () => number;
  invalidate: () => void;
  isCurrent: (token: number) => boolean;
};

export function tabAfterKey<T extends string>(
  tabs: readonly T[],
  active: T,
  key: string
): T | null {
  if (!isTabNavigationKey(key) || tabs.length === 0) return null;
  if (key === "Home") return tabs[0];
  if (key === "End") return tabs[tabs.length - 1];
  const currentIndex = Math.max(0, tabs.indexOf(active));
  const delta = key === "ArrowRight" ? 1 : -1;
  return tabs[(currentIndex + delta + tabs.length) % tabs.length];
}

export function createRequestTokenGuard(): RequestTokenGuard {
  let currentToken = 0;
  return {
    begin() {
      currentToken += 1;
      return currentToken;
    },
    invalidate() {
      currentToken += 1;
    },
    isCurrent(token) {
      return currentToken === token;
    }
  };
}

export function canAddSetPreview(responseKey: string, currentKey: string, itemCount: number): boolean {
  return Boolean(responseKey) && responseKey === currentKey && itemCount > 0;
}

export function genericSearchResultIsCurrent(
  activeTab: PrimarySearchTab,
  resultOrigin: GenericSearchTab | null,
  responseKey: string,
  currentKey: string
): boolean {
  return (
    resultOrigin !== null
    && activeTab === resultOrigin
    && Boolean(responseKey)
    && responseKey === currentKey
  );
}

export function uniqueSeedTrackIds(seedTrackIds: readonly number[]): number[] {
  return [...new Set(seedTrackIds)];
}

export function buildSetBuilderPayload(draft: SetBuilderDraft): PayloadResult<SetBuilderGeneratePayload> {
  const seedTrackIds = uniqueSeedTrackIds(draft.seedTrackIds);
  if (draft.seedMode === "manual" && (seedTrackIds.length < 1 || seedTrackIds.length > 5)) {
    return { ok: false, error: "Manual SET requires 1-5 unique seed tracks." };
  }
  if (!integerInRange(draft.autoSeedCount, 1, 5)) {
    return { ok: false, error: "Auto anchors must be an integer from 1 to 5." };
  }
  if (!integerInRange(draft.limit, 1, 500)) {
    return { ok: false, error: "SET limit must be an integer from 1 to 500." };
  }
  if (!finiteInRange(draft.diversity, 0, 1)) {
    return { ok: false, error: "SET diversity must be between 0 and 1." };
  }
  if (draft.randomSeed !== undefined && !Number.isSafeInteger(draft.randomSeed)) {
    return { ok: false, error: "Random seed must be a safe integer or left empty." };
  }
  if (draft.bpmMode !== "general") {
    if (draft.bpmStart !== undefined && !finiteInRange(draft.bpmStart, 20, 300)) {
      return { ok: false, error: "Start BPM must be between 20 and 300 or left empty." };
    }
    if (draft.bpmTarget !== undefined && !finiteInRange(draft.bpmTarget, 20, 300)) {
      return { ok: false, error: "Target BPM must be between 20 and 300 or left empty." };
    }
  }

  const sources = setSourceOrder.filter((source) => draft.sources[source]);
  if (sources.length === 0) {
    return { ok: false, error: "Enable at least one SET embedding source." };
  }
  const weightsResult = selectedWeights(
    sources,
    draft.weights,
    draft.useCustomWeights,
    ["sonara_broad"]
  );
  if (!weightsResult.ok) return weightsResult;

  const payload: SetBuilderGeneratePayload = {
    seed_mode: draft.seedMode,
    seed_track_ids: draft.seedMode === "manual" ? seedTrackIds : [],
    auto_seed_count: draft.autoSeedCount,
    sources,
    weights: weightsResult.weights,
    mode: draft.mode,
    limit: draft.limit,
    diversity: draft.diversity,
    energy_curve: draft.energyCurve,
    bpm_mode: draft.bpmMode,
    bpm_change: draft.bpmChange,
    classifier_preferences: sortedFiniteScoreMap(draft.classifierPreferences),
    classifier_flows: sortedStringMap(draft.classifierFlows)
  };
  if (draft.randomSeed !== undefined) payload.random_seed = draft.randomSeed;
  if (draft.bpmMode !== "general") {
    if (draft.bpmStart !== undefined) payload.bpm_start = draft.bpmStart;
    if (draft.bpmTarget !== undefined) payload.bpm_target = draft.bpmTarget;
  }
  return { ok: true, payload };
}

export function buildHybridPayload(draft: HybridDraft): PayloadResult<HybridSearchPayload> {
  const seedTrackIds = uniqueSeedTrackIds(draft.seedTrackIds);
  if (seedTrackIds.length < 1 || seedTrackIds.length > 5) {
    return { ok: false, error: "Hybrid Preview requires 1-5 unique seed tracks." };
  }
  if (!integerInRange(draft.perSource, 1, 100)) {
    return { ok: false, error: "Hybrid per-source limit must be an integer from 1 to 100." };
  }
  if (!integerInRange(draft.limit, 1, 100)) {
    return { ok: false, error: "Hybrid result limit must be an integer from 1 to 100." };
  }
  if (!finiteInRange(draft.transitionRiskWeight, 0, 1)) {
    return { ok: false, error: "Hybrid transition risk weight must be between 0 and 1." };
  }

  const sources = hybridSourceOrder.filter((source) => draft.sources[source]);
  if (sources.length === 0) {
    return { ok: false, error: "Enable at least one Hybrid Preview source." };
  }
  const weightsResult = selectedWeights(sources, draft.weights, draft.useCustomWeights);
  if (!weightsResult.ok) return weightsResult;

  return {
    ok: true,
    payload: {
      seed_track_ids: seedTrackIds,
      sources,
      weights: weightsResult.weights,
      per_source: draft.perSource,
      limit: draft.limit,
      transition_risk_weight: draft.transitionRiskWeight,
      transition_risk_version: "v2",
      classifier_preferences: sortedFiniteScoreMap(draft.classifierPreferences),
      classifier_risk_weights: sortedFiniteScoreMap(draft.classifierRiskWeights),
      include_diagnostics: true,
      record_session: true
    }
  };
}

export function setBuilderSignature(draft: SetBuilderDraft): string {
  const payload = buildSetBuilderPayload(draft);
  return JSON.stringify({
    database_path: draft.databasePath,
    database_identity: draft.databaseIdentity,
    request: payload.ok ? payload.payload : { invalid: payload.error }
  });
}

export function hybridSignature(draft: HybridDraft): string {
  const payload = buildHybridPayload(draft);
  return JSON.stringify({
    database_path: draft.databasePath,
    database_identity: draft.databaseIdentity,
    request: payload.ok ? payload.payload : { invalid: payload.error }
  });
}

function selectedWeights<S extends string>(
  sources: readonly S[],
  availableWeights: Record<S, number> | (Record<S, number> & Record<"sonara_broad", number>),
  useCustomWeights: boolean,
  additionalKeys: readonly "sonara_broad"[] = []
): { ok: true; weights: Record<string, number> | null } | { ok: false; error: string } {
  if (!useCustomWeights) return { ok: true, weights: null };
  const keys: string[] = [...sources, ...additionalKeys];
  const weights: Record<string, number> = {};
  for (const key of keys) {
    const value = availableWeights[key as keyof typeof availableWeights];
    if (!Number.isFinite(value) || value < 0) {
      return { ok: false, error: `Weight ${key} must be finite and nonnegative.` };
    }
    weights[key] = value;
  }
  if (!Object.values(weights).some((value) => value > 0)) {
    return { ok: false, error: "At least one enabled custom weight must be positive." };
  }
  return { ok: true, weights };
}

function sortedFiniteScoreMap(values: Record<string, number>): Record<string, number> {
  return Object.fromEntries(
    Object.entries(values)
      .filter(([, value]) => Number.isFinite(value) && value !== 0)
      .sort(([left], [right]) => left.localeCompare(right))
  );
}

function sortedStringMap<T extends string>(values: Record<string, T>): Record<string, T> {
  return Object.fromEntries(
    Object.entries(values).sort(([left], [right]) => left.localeCompare(right))
  );
}

function finiteInRange(value: number, min: number, max: number): boolean {
  return Number.isFinite(value) && value >= min && value <= max;
}

function integerInRange(value: number, min: number, max: number): boolean {
  return Number.isInteger(value) && value >= min && value <= max;
}

function isTabNavigationKey(key: string): key is TabNavigationKey {
  return key === "ArrowLeft" || key === "ArrowRight" || key === "Home" || key === "End";
}
