import { useEffect, useMemo, useRef, useState } from "react";
import { api, type Track, type SearchResult, type EmbeddingSource } from "./api";
import {
  createRequestTokenGuard,
  isSeedEmbeddingFamily,
  seedSearchModelPresentation,
  type GenericSearchTab,
  type SeedSearchModel,
} from "./searchSurfaceState";
import { displayTrack } from "./trackDisplay";
import type { SearchFiltersState } from "./SearchPlaylistPanel";
import type { useActivityLog } from "./useActivityLog";
import { errorText, isAbortError } from "./errors";

export type SearchNotice = { kind: "ok" | "error" | "warn" | "idle"; text: string };
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
  seedSearchModel: SeedSearchModel;
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
  seedSearchModel,
  setResults,
  addSeed,
  setNotice,
  appendActivity,
}: SearchRequestsOptions) {
  const genericSearchRequestGuard = useRef(createRequestTokenGuard());
  const genericSearchAbortController = useRef<AbortController | null>(null);
  const randomTrackAbortController = useRef<AbortController | null>(null);
  const randomTrackDatabaseKey = JSON.stringify([databasePath, databaseCatalogUuid]);
  const randomTrackDatabaseKeyRef = useRef(randomTrackDatabaseKey);
  randomTrackDatabaseKeyRef.current = randomTrackDatabaseKey;
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
      seed_search_model: seedSearchModel,
    }),
    [
      analysisDevice,
      selectedPresetKeys,
      textCompareModels,
      textUseNegativePrompt,
      textEmbeddingFamily,
      seedSearchModel,
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
    randomTrackAbortController.current?.abort();
  }, []);

  useEffect(() => {
    cancelRandomTrackRequest();
  }, [randomTrackDatabaseKey]);

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

  function cancelRandomTrackRequest() {
    randomTrackAbortController.current?.abort();
    randomTrackAbortController.current = null;
    setRandomSonaraTrackPending(false);
    setRandomEmbeddingTrackPending(false);
  }

  function randomTrackRequestIsCurrent(controller: AbortController, databaseKey: string) {
    return randomTrackAbortController.current === controller
      && !controller.signal.aborted
      && randomTrackDatabaseKeyRef.current === databaseKey;
  }

  async function handleSonaraSearch() {
    if (!seeds.length) {
      setNotice({ kind: "error", text: "Выберите seed-треки" });
      return;
    }
    const ticket = beginGenericSearchRequest();
    appendActivity("info", "SONARA search запущен", `${seeds.length} seed`);
    try {
      const value = await api.sonaraSearch({
        seed_track_ids: seeds,
        limit: filters.limit,
        mixer_weights: filters.sonaraMixer,
        modifiers: filters.sonaraModifiers,
      }, {
        signal: ticket.controller.signal,
      });
      if (commitGenericSearchResults(ticket, "sonara", value)) {
        appendActivity("ok", "SONARA search завершен", `Найдено: ${value.length}`);
        setNotice({ kind: "ok", text: `Найдено: ${value.length}` });
      }
    } catch (error) {
      if (!genericSearchRequestIsCurrent(ticket) || isAbortError(error)) return;
      const message = errorText(error);
      setNotice({ kind: "error", text: message });
      appendActivity("error", "SONARA search недоступен", message);
    } finally {
      finishGenericSearchRequest(ticket);
    }
  }

  async function handleAddRandomSonaraTrack() {
    if (randomTrackAbortController.current || !databaseCatalogUuid) return;
    const controller = new AbortController();
    const databaseKey = randomTrackDatabaseKey;
    randomTrackAbortController.current = controller;
    setRandomSonaraTrackPending(true);
    appendActivity("info", "Добавление случайного SONARA seed", `Исключено текущих seed: ${seeds.length}`);
    try {
      const track = await api.randomSonaraTrack({
        exclude_track_ids: seeds,
      }, {
        signal: controller.signal,
      });
      if (!randomTrackRequestIsCurrent(controller, databaseKey)) return;
      if (track.catalog_uuid !== databaseCatalogUuid) {
        throw new Error("Random track belongs to a different catalog; refresh the current library and try again.");
      }
      addSeed(track);
      const selected = displayTrack(track);
      appendActivity("ok", "Добавлен случайный SONARA seed", selected);
      setNotice({ kind: "ok", text: `Добавлен seed: ${selected}` });
    } catch (error) {
      if (!randomTrackRequestIsCurrent(controller, databaseKey) || isAbortError(error)) return;
      const message = errorText(error);
      setNotice({ kind: "error", text: message });
      appendActivity("error", "Не удалось добавить случайный SONARA seed", message);
    } finally {
      if (randomTrackRequestIsCurrent(controller, databaseKey)) {
        randomTrackAbortController.current = null;
        setRandomSonaraTrackPending(false);
      }
    }
  }

  async function handleAddRandomEmbeddingTrack() {
    if (randomTrackAbortController.current || !databaseCatalogUuid || !isSeedEmbeddingFamily(seedSearchModel)) return;
    const controller = new AbortController();
    const databaseKey = randomTrackDatabaseKey;
    randomTrackAbortController.current = controller;
    const label = seedSearchModelPresentation[seedSearchModel].label;
    setRandomEmbeddingTrackPending(true);
    appendActivity("info", `Добавление случайного ${label} seed`, `Исключено текущих seed: ${seeds.length}`);
    try {
      const track = await api.randomEmbeddingTrack({
        analysis_family: seedSearchModel,
        exclude_track_ids: seeds,
      }, {
        signal: controller.signal,
      });
      if (!randomTrackRequestIsCurrent(controller, databaseKey)) return;
      if (track.catalog_uuid !== databaseCatalogUuid) {
        throw new Error("Random track belongs to a different catalog; refresh the current library and try again.");
      }
      addSeed(track);
      const selected = displayTrack(track);
      appendActivity("ok", `Добавлен случайный ${label} seed`, selected);
      setNotice({ kind: "ok", text: `Добавлен seed: ${selected}` });
    } catch (error) {
      if (!randomTrackRequestIsCurrent(controller, databaseKey) || isAbortError(error)) return;
      const message = errorText(error);
      setNotice({ kind: "error", text: message });
      appendActivity("error", `Не удалось добавить случайный ${label} seed`, message);
    } finally {
      if (randomTrackRequestIsCurrent(controller, databaseKey)) {
        randomTrackAbortController.current = null;
        setRandomEmbeddingTrackPending(false);
      }
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
    const label = seedSearchModelPresentation[analysisFamily].label;
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
      const message = errorText(error);
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
    cancelRandomTrackRequest,
    handleSonaraSearch,
    handleAddRandomSonaraTrack,
    handleAddRandomEmbeddingTrack,
    handleEmbeddingSearch,
  };
}

