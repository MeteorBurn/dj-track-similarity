import { useEffect, useRef, useState } from "react";
import {
  api,
  type DjSetBuildPayload,
  type DjSetBuildResponse,
  type DjSetDirectionAxis,
  type DjSetDirectionRelation,
  type DjSetPreset,
  type DjSetStage,
  type EmbeddingSource,
  type Track,
} from "./api";
import { djSetPresetName, djSetSlotPlan, djSetStageLabel, type DjSetStageField } from "./djSetView";
import { errorText, isAbortError } from "./errors";
import { seedEmbeddingFamilies, type SeedEmbeddingFamily } from "./searchSurfaceState";
import { displayTrack, sameTrackIdentity } from "./trackDisplay";

/** What a seed track does for the set: "reference" sets the breed and is never
 * placed, "pinned" is placed where the engine chooses, "slot" in a given slot. */
export type DjSetSeedRole = "reference" | "pinned" | "slot";

/** The form as typed. A number field holds null while it is empty: for the
 * seed that is a value ("let the server choose"), for the other fields it is a
 * gap that blocks the build. */
export type DjSetSettings = {
  tracks: number | null;
  /** null = MERT-v2 when the library has it, else the first family that has embeddings. */
  poolModel: SeedEmbeddingFamily | null;
  poolSize: number | null;
  directionAxis: DjSetDirectionAxis | null;
  directionRelation: DjSetDirectionRelation;
  directionMargin: number | null;
  variety: number;
  seed: number | null;
};

/** A stage as typed: an empty number field is null, as in the settings; the
 * rules of the stage ride along untouched. */
export type DjSetStageDraft = Omit<DjSetStage, DjSetStageField> & Record<DjSetStageField, number | null>;

export type DjSetState = ReturnType<typeof useDjSet>;

type SeedPlacement = { role: DjSetSeedRole; slot: number | null };
type SeedReference = SeedPlacement & { track: Track };

const DEFAULT_PRESET = "arch";
const DEFAULT_POOL_SIZE = 2000;
const defaultPlacement: SeedPlacement = { role: "reference", slot: null };
const stageFields: readonly DjSetStageField[] = ["share", "intensity_start", "intensity_end", "bpm_start", "bpm_end"];

const defaultSettings: DjSetSettings = {
  tracks: 15,
  poolModel: null,
  poolSize: DEFAULT_POOL_SIZE,
  directionAxis: null,
  directionRelation: "similar",
  directionMargin: 10,
  variety: 0.35,
  seed: null,
};

/** The DJ SET tab: how the set develops, the role of every seed track, the
 * build settings, one build request at a time and the last set it returned.
 * The set belongs to the library it was built from and outlives a change of
 * settings. */
export function useDjSet({ databaseIdentity, seedTracks, embeddingCounts }: {
  databaseIdentity: string | null;
  seedTracks: Track[];
  embeddingCounts: Record<EmbeddingSource, number>;
}) {
  const [settings, setSettings] = useState(defaultSettings);
  const [placements, setPlacements] = useState<Record<string, SeedPlacement>>({});
  // The presets as the server defines them; null until they arrive, and for
  // good when they cannot be loaded.
  const [presets, setPresets] = useState<DjSetPreset[] | null>(null);
  const [presetsUnavailable, setPresetsUnavailable] = useState(false);
  const [presetKey, setPresetKey] = useState(DEFAULT_PRESET);
  // The stages being edited, per preset: switching away and back keeps them.
  const [drafts, setDrafts] = useState<Record<string, DjSetStageDraft[]>>({});
  const [pendingSince, setPendingSince] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [built, setBuilt] = useState<{ databaseIdentity: string; response: DjSetBuildResponse } | null>(null);
  const controllerRef = useRef<AbortController | null>(null);

  const references: SeedReference[] = seedTracks.map((track) => ({
    track,
    ...(placements[track.track_uuid] ?? defaultPlacement),
  }));
  const hasReference = references.some(({ role }) => role === "reference");
  const poolModels = seedEmbeddingFamilies.filter((family) => embeddingCounts[family] > 0);
  const poolModel = settings.poolModel !== null && poolModels.includes(settings.poolModel)
    ? settings.poolModel
    : poolModels.includes("mert_v2") ? "mert_v2" : poolModels[0] ?? null;

  const preset = presets?.find(({ key }) => key === presetKey) ?? presets?.[0] ?? null;
  const stages: DjSetStageDraft[] | null = preset ? drafts[preset.key] ?? preset.stages : null;
  const stagesChanged = preset !== null && stages !== null && stages.some((stage, index) => (
    stageFields.some((field) => stage[field] !== preset.stages[index][field])
  ));
  const presetsStatus: "loading" | "ready" | "unavailable" = presets !== null
    ? "ready"
    : presetsUnavailable ? "unavailable" : "loading";
  const request = buildRequest(settings, references, hasReference, poolModel, preset?.key ?? null, stages);
  const problem = databaseIdentity ? request.problem : "Сначала откройте библиотеку.";
  const result = built !== null && built.databaseIdentity === databaseIdentity ? built.response : null;

  useEffect(() => {
    controllerRef.current?.abort();
    controllerRef.current = null;
    setPendingSince(null);
    setError("");
    setBuilt(null);
  }, [databaseIdentity]);

  useEffect(() => () => controllerRef.current?.abort(), []);

  useEffect(() => {
    const controller = new AbortController();
    api.djsetPresets({ signal: controller.signal })
      .then((loaded) => {
        if (controller.signal.aborted) return;
        if (!Array.isArray(loaded) || !loaded.length) throw new Error("The server returned no presets.");
        setPresets(loaded);
      })
      .catch(() => {
        if (!controller.signal.aborted) setPresetsUnavailable(true);
      });
    return () => controller.abort();
  }, []);

  // A removed seed takes its role with it: added again, it starts as a reference.
  const seedKey = seedTracks.map((track) => track.track_uuid).join("|");
  useEffect(() => {
    const present = new Set(seedTracks.map((track) => track.track_uuid));
    setPlacements((current) => Object.keys(current).every((key) => present.has(key))
      ? current
      : Object.fromEntries(Object.entries(current).filter(([key]) => present.has(key))));
  }, [seedKey]);

  function setSetting<Key extends keyof DjSetSettings>(key: Key, value: DjSetSettings[Key]) {
    setSettings((current) => ({ ...current, [key]: value }));
  }

  function setSeedRole(track: Track, role: DjSetSeedRole) {
    setPlacements((current) => ({
      ...current,
      [track.track_uuid]: { role, slot: current[track.track_uuid]?.slot ?? null },
    }));
  }

  function setSeedSlot(track: Track, slot: number | null) {
    setPlacements((current) => ({ ...current, [track.track_uuid]: { role: "slot", slot } }));
  }

  function editStages(edit: (current: DjSetStageDraft[]) => DjSetStageDraft[]) {
    if (!preset) return;
    setDrafts((current) => ({ ...current, [preset.key]: edit(current[preset.key] ?? preset.stages) }));
  }

  function setStageValue(index: number, field: DjSetStageField, value: number | null) {
    editStages((current) => current.map((stage, position) => (
      position === index ? { ...stage, [field]: value } : stage
    )));
  }

  /** Move the whole tempo plan up or down, keeping its shape. */
  function shiftBpm(delta: number) {
    editStages((current) => current.map((stage) => ({
      ...stage,
      bpm_start: stage.bpm_start === null ? null : Number((stage.bpm_start + delta).toFixed(2)),
      bpm_end: stage.bpm_end === null ? null : Number((stage.bpm_end + delta).toFixed(2)),
    })));
  }

  function resetStages() {
    if (!preset) return;
    setDrafts(({ [preset.key]: _dropped, ...rest }) => rest);
  }

  function build() {
    if (controllerRef.current || !databaseIdentity || !request.payload) return;
    const controller = new AbortController();
    controllerRef.current = controller;
    const builtFor = databaseIdentity;
    setPendingSince(Date.now());
    setError("");
    api.djsetBuild(request.payload, { signal: controller.signal })
      .then((response) => {
        if (controllerRef.current !== controller) return;
        controllerRef.current = null;
        setPendingSince(null);
        setBuilt({ databaseIdentity: builtFor, response });
      })
      .catch((cause: unknown) => {
        if (controllerRef.current !== controller) return;
        controllerRef.current = null;
        setPendingSince(null);
        if (!isAbortError(cause)) setError(errorText(cause));
      });
  }

  function cancel() {
    controllerRef.current?.abort();
    controllerRef.current = null;
    setPendingSince(null);
  }

  /** The built set keeps its own copy of each track, so a like has to reach it. */
  function adoptTrack(updated: Track) {
    setBuilt((current) => current && {
      ...current,
      response: {
        ...current.response,
        slots: current.response.slots.map((slot) => (
          sameTrackIdentity(slot.track, updated) ? { ...slot, track: updated } : slot
        )),
      },
    });
  }

  return {
    settings,
    setSetting,
    references,
    setSeedRole,
    setSeedSlot,
    hasReference,
    poolModels,
    poolModel,
    /** Every way a set can develop; null until the server answers. */
    presets,
    /** "unavailable": the server has no presets, so a build runs on its default. */
    presetsStatus,
    /** The preset being edited; null without presets. */
    presetKey: preset?.key ?? null,
    selectPreset: setPresetKey,
    /** The stages of that preset as typed; null without presets. */
    stages,
    /** Whether they differ from the server's. */
    stagesChanged,
    setStageValue,
    shiftBpm,
    resetStages,
    /** The stages and the target of every slot, when every field holds a valid number. */
    plan: request.plan,
    /** Why a build cannot start now; empty when it can. */
    problem,
    /** When the running build started, in epoch milliseconds; null when idle. */
    pendingSince,
    error,
    build,
    cancel,
    /** The last built set of the open library. */
    result,
    adoptTrack,
  };
}

function inRange(value: number | null, minimum: number, maximum: number, integer = false): value is number {
  return value !== null && value >= minimum && value <= maximum && (!integer || Number.isInteger(value));
}

type DjSetPlan = { stages: DjSetStage[]; slots: ReturnType<typeof djSetSlotPlan> };

/** The request body for the form, or the first thing in the form that keeps it
 * from being one. The ranges are the server's own. */
function buildRequest(
  settings: DjSetSettings,
  references: SeedReference[],
  hasReference: boolean,
  poolModel: SeedEmbeddingFamily | null,
  preset: string | null,
  drafts: DjSetStageDraft[] | null,
): { payload: DjSetBuildPayload | null; problem: string; plan: DjSetPlan | null } {
  const { tracks, seed } = settings;
  const tracksValid = inRange(tracks, 5, 60, true);

  let stages: DjSetStage[] | null = null;
  let stageProblem = "";
  if (preset !== null && drafts !== null) {
    stages = [];
    for (const draft of drafts) {
      const name = `Этап «${djSetStageLabel(preset, draft.key)}»`;
      const { share, intensity_start, intensity_end, bpm_start, bpm_end } = draft;
      if (share === null || share <= 0 || share > 100) stageProblem = `${name}: доля больше 0 и не больше 100.`;
      else if (!inRange(intensity_start, 0, 1) || !inRange(intensity_end, 0, 1)) stageProblem = `${name}: интенсивность от 0 до 1.`;
      else if (!inRange(bpm_start, 60, 200) || !inRange(bpm_end, 60, 200)) stageProblem = `${name}: BPM от 60 до 200.`;
      else {
        stages.push({ ...draft, share, intensity_start, intensity_end, bpm_start, bpm_end });
        continue;
      }
      stages = null;
      break;
    }
  }
  const plan = stages !== null && tracksValid && tracks >= stages.length
    ? { stages, slots: djSetSlotPlan(tracks, stages) }
    : null;
  const fail = (problem: string) => ({ payload: null, problem, plan });

  if (!tracksValid) return fail("Треков: целое число от 5 до 60.");
  if (stageProblem) return fail(stageProblem);
  if (stages !== null && preset !== null && tracks < stages.length) {
    return fail(`Треков меньше, чем этапов в «${djSetPresetName(preset)}»: нужно хотя бы ${stages.length}.`);
  }
  if (seed !== null && !inRange(seed, 0, 4294967295, true)) return fail("Зерно: целое число от 0 до 4294967295 или пусто.");

  const takenSlots = new Set<number>();
  for (const { track, role, slot } of references) {
    if (role !== "slot") continue;
    if (!inRange(slot, 1, tracks, true)) return fail(`Слот для «${displayTrack(track)}»: целое число от 1 до ${tracks}.`);
    if (takenSlots.has(slot)) return fail(`Слот ${slot} назначен двум референсам.`);
    takenSlots.add(slot);
  }

  // The server reads the pool and the direction only for a "reference" seed;
  // without one the pool fields still have to be valid, so they go as defaults.
  let pool: { model: EmbeddingSource; size: number } = { model: poolModel ?? "mert_v2", size: DEFAULT_POOL_SIZE };
  let direction: DjSetBuildPayload["direction"] = null;
  if (hasReference) {
    if (poolModel === null) return fail("Ориентиру нужны эмбеддинги: запустите ML-анализ библиотеки или смените роль референса.");
    if (!inRange(settings.poolSize, 100, 20000, true)) return fail("Пул: целое число от 100 до 20000.");
    pool = { model: poolModel, size: settings.poolSize };
    if (settings.directionAxis !== null) {
      if (!inRange(settings.directionMargin, 0, 50)) return fail("Запас смещения: от 0 до 50.");
      direction = {
        axis: settings.directionAxis,
        relation: settings.directionRelation,
        margin: settings.directionMargin,
      };
    }
  }

  return {
    problem: "",
    plan,
    payload: {
      tracks,
      // Without loaded presets the server builds on its own default.
      preset: preset ?? DEFAULT_PRESET,
      stages,
      references: references.map(({ track, role, slot }) => ({
        track_id: track.track_id,
        role: role === "reference" ? "reference" : "pinned",
        slot: role === "slot" ? slot : null,
      })),
      pool_model: pool.model,
      pool_size: pool.size,
      direction,
      variety: settings.variety,
      seed,
    },
  };
}
