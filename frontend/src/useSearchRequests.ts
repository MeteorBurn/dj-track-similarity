import { useEffect, useMemo, useRef, useState } from "react";
import { api, type Track, type SearchResult, type EmbeddingSource } from "./api";
import {
  createRequestTokenGuard,
  isSeedEmbeddingFamily,
  seedEmbeddingFamilyPresentation,
  type GenericSearchTab,
  type SeedEmbeddingFamily,
} from "./searchSurfaceState";
import { displayTrack } from "./trackDisplay";
import type { SearchFiltersState } from "./SearchPlaylistPanel";
import type { useActivityLog } from "./useActivityLog";

export type SearchNotice = { kind: "ok" | "error" | "idle"; text: string };
type GenericSearchResultState = {
  origin: GenericSearchTab;
  requestKey: string;
};
type GuardedRequestTicket = {
  token: number;
  requestKey: string;
  controller: AbortController;
};

export type SearchRequestLifecycle = Pick<
  ReturnType<typeof useSearchRequests>,
  | "beginGenericSearchRequest"
  | "genericSearchRequestIsCurrent"
  | "commitGenericSearchResults"
  | "finishGenericSearchRequest"
>;

type SearchRequestsOptions = {
  databasePath: string | null;
  databaseCatalogUuid: string | null;
  seedTracks: Track[];
  seeds: number[];
  filters: SearchFiltersState;
  textUseNegativePrompt: boolean;
  selectedPresetKeys: string[];
  textCompareModels: boolean;
  analysisDevice: "auto" | "cpu" | "cuda";
  textEmbeddingFamily: "clap" | "mulan";
  seedEmbeddingFamily: SeedEmbeddingFamily;
  setResults: (results: SearchResult[]) => void;
  addSeed: (track: Track) => void;
  setNotice: (notice: SearchNotice) => void;
  appendActivity: ReturnType<typeof useActivityLog>["appendActivity"];
};

export function useSearchRequests({
  databasePath,
  databaseCatalogUuid,
  seedTracks,
  seeds,
  filters,
  textUseNegativePrompt,
  selectedPresetKeys,
  textCompareModels,
  analysisDevice,
  textEmbeddingFamily,
  seedEmbeddingFamily,
  setResults,
  addSeed,
  setNotice,
  appendActivity,
}: SearchRequestsOptions) {
  const genericSearchRequestGuard = useRef(createRequestTokenGuard());
  const genericSearchAbortController = useRef<AbortController | null>(null);
  const [genericSearchPending, setGenericSearchPending] = useState(false);
  const [randomSonaraTrackPending, setRandomSonaraTrackPending] = useState(false);
  const [randomEmbeddingTrackPending, setRandomEmbeddingTrackPending] = useState(false);
  const [genericSearchResultState, setGenericSearchResultState] = useState<GenericSearchResultState | null>(null);
  const genericSearchInputKey = useMemo(
    () => JSON.stringify({
      database_path: databasePath,
      catalog_uuid: databaseCatalogUuid,
      seed_identities: seedTracks.map((track) => ({
        track_id: track.track_id,
        track_uuid: track.track_uuid,
      })),
      filters,
      text_use_negative_prompt: textUseNegativePrompt,
      prompt_preset_keys: selectedPresetKeys,
      textCompareModels,
      analysis_device: analysisDevice,
      text_embedding_family: textEmbeddingFamily,
      seed_embedding_family: seedEmbeddingFamily,
    }),
    [
      analysisDevice,
      selectedPresetKeys,
      textCompareModels,
      textUseNegativePrompt,
      textEmbeddingFamily,
      seedEmbeddingFamily,
      databaseCatalogUuid,
      databasePath,
      filters,
      seedTracks,
    ]
  );
  const genericSearchInputKeyRef = useRef(genericSearchInputKey);
  genericSearchInputKeyRef.current = genericSearchInputKey;

  useEffect(() => {
    genericSearchInputKeyRef.current = genericSearchInputKey;
    cancelGenericSearchRequest();
    setGenericSearchResultState(null);
    setResults([]);
  }, [genericSearchInputKey]);

  useEffect(() => () => {
    genericSearchAbortController.current?.abort();
  }, []);

  function beginGenericSearchRequest(): GuardedRequestTicket {
    genericSearchAbortController.current?.abort();
    const controller = new AbortController();
    const ticket = {
      token: genericSearchRequestGuard.current.begin(),
      requestKey: genericSearchInputKeyRef.current,
      controller,
    };
    genericSearchAbortController.current = controller;
    setGenericSearchPending(true);
    setGenericSearchResultState(null);
    setResults([]);
    return ticket;
  }

  function genericSearchRequestIsCurrent(ticket: GuardedRequestTicket) {
    return (
      genericSearchRequestGuard.current.isCurrent(ticket.token)
      && genericSearchInputKeyRef.current === ticket.requestKey
    );
  }

  function commitGenericSearchResults(
    ticket: GuardedRequestTicket,
    origin: GenericSearchTab,
    value: Awaited<ReturnType<typeof api.search>>
  ) {
    if (!genericSearchRequestIsCurrent(ticket)) return false;
    setResults(value);
    setGenericSearchResultState({
      origin,
      requestKey: ticket.requestKey,
    });
    return true;
  }

  function finishGenericSearchRequest(ticket: GuardedRequestTicket) {
    if (!genericSearchRequestIsCurrent(ticket)) return;
    if (genericSearchAbortController.current === ticket.controller) {
      genericSearchAbortController.current = null;
    }
    setGenericSearchPending(false);
  }

  function cancelGenericSearchRequest() {
    genericSearchRequestGuard.current.invalidate();
    genericSearchAbortController.current?.abort();
    genericSearchAbortController.current = null;
    setGenericSearchPending(false);
  }
  async function handleSonaraSearch() {
    if (!seeds.length) {
      setNotice({ kind: "error", text: "Выберите seed-треки" });
      return;
    }
    const customMode = filters.sonaraMode === "custom";
    const ticket = beginGenericSearchRequest();
    appendActivity("info", "SONARA search запущен", `${filters.sonaraMode} · ${seeds.length} seed`);
    try {
      const value = await api.sonaraSearch({
        seed_track_ids: seeds,
        limit: filters.limit,
        mode: filters.sonaraMode,
        mixer_weights: customMode ? filters.sonaraMixer : null,
        modifiers: customMode ? filters.sonaraModifiers : null,
      }, {
        signal: ticket.controller.signal,
      });
      if (commitGenericSearchResults(ticket, "sonara", value)) {
        appendActivity("ok", "SONARA search завершен", `Найдено: ${value.length}`);
        setNotice({ kind: "ok", text: `Найдено: ${value.length}` });
      }
    } catch (error) {
      if (!genericSearchRequestIsCurrent(ticket) || isAbortError(error)) return;
      const message = error instanceof Error ? error.message : String(error);
      setNotice({ kind: "error", text: message });
      appendActivity("error", "SONARA search недоступен", message);
    } finally {
      finishGenericSearchRequest(ticket);
    }
  }

  async function handleAddRandomSonaraTrack() {
    if (randomSonaraTrackPending) return;
    setRandomSonaraTrackPending(true);
    appendActivity("info", "Добавление случайного SONARA seed", `Исключено текущих seed: ${seeds.length}`);
    try {
      const track = await api.randomSonaraTrack({
        exclude_track_ids: seeds,
      });
      addSeed(track);
      const selected = displayTrack(track);
      appendActivity("ok", "Добавлен случайный SONARA seed", selected);
      setNotice({ kind: "ok", text: `Добавлен seed: ${selected}` });
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      setNotice({ kind: "error", text: message });
      appendActivity("error", "Не удалось добавить случайный SONARA seed", message);
    } finally {
      setRandomSonaraTrackPending(false);
    }
  }

  async function handleAddRandomEmbeddingTrack() {
    if (randomEmbeddingTrackPending) return;
    const label = seedEmbeddingFamilyPresentation[seedEmbeddingFamily].label;
    setRandomEmbeddingTrackPending(true);
    appendActivity("info", `Добавление случайного ${label} seed`, `Исключено текущих seed: ${seeds.length}`);
    try {
      const track = await api.randomEmbeddingTrack({
        analysis_family: seedEmbeddingFamily,
        exclude_track_ids: seeds,
      });
      addSeed(track);
      const selected = displayTrack(track);
      appendActivity("ok", `Добавлен случайный ${label} seed`, selected);
      setNotice({ kind: "ok", text: `Добавлен seed: ${selected}` });
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      setNotice({ kind: "error", text: message });
      appendActivity("error", `Не удалось добавить случайный ${label} seed`, message);
    } finally {
      setRandomEmbeddingTrackPending(false);
    }
  }
  async function handleEmbeddingSearch(analysisFamily: EmbeddingSource) {
    if (!seeds.length) {
      const error = new Error("Выберите от 1 до 5 уникальных seed-треков");
      setNotice({ kind: "error", text: error.message });
      throw error;
    }
    if (!isSeedEmbeddingFamily(analysisFamily)) {
      throw new Error(`Unsupported seed embedding model: ${analysisFamily}`);
    }
    const label = seedEmbeddingFamilyPresentation[analysisFamily].label;
    const ticket = beginGenericSearchRequest();
    appendActivity("info", `${label} search запущен`, `${seeds.length} seed`);
    try {
      const value = await api.search({
        analysis_family: analysisFamily,
        seed_track_ids: seeds,
        limit: filters.limit,
        epsilon: null,
        noise: 0,
      }, {
        signal: ticket.controller.signal,
      });
      if (commitGenericSearchResults(ticket, analysisFamily, value)) {
        appendActivity("ok", `${label} search завершен`, `Найдено: ${value.length}`);
        setNotice({ kind: "ok", text: `Найдено: ${value.length}` });
      }
    } catch (error) {
      if (!genericSearchRequestIsCurrent(ticket) || isAbortError(error)) return;
      const message = error instanceof Error ? error.message : String(error);
      setNotice({ kind: "error", text: message });
      appendActivity("error", `${label} search недоступен`, message);
      throw error;
    } finally {
      finishGenericSearchRequest(ticket);
    }
  }

  return {
    genericSearchPending,
    randomSonaraTrackPending,
    randomEmbeddingTrackPending,
    genericSearchResultState,
    genericSearchInputKey,
    beginGenericSearchRequest,
    genericSearchRequestIsCurrent,
    commitGenericSearchResults,
    finishGenericSearchRequest,
    cancelGenericSearchRequest,
    handleSonaraSearch,
    handleAddRandomSonaraTrack,
    handleAddRandomEmbeddingTrack,
    handleEmbeddingSearch,
  };
}

function isAbortError(error: unknown) {
  return error instanceof Error && error.name === "AbortError";
}
