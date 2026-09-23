import { useEffect, useRef, useState } from "react";
import { api, type ClusterMapResponse, type EmbeddingSearchPayload, type Track } from "./api";
import { errorText, isAbortError } from "./errors";
import { isSeedEmbeddingFamily, type SeedSearchModel } from "./searchSurfaceState";
import type { EmbeddingLayerState } from "./useEmbeddingLayers";

/** One build of the cluster map; it lives only while its key matches the inputs. */
export type ClusterMapEntry = {
  key: string;
  payload: EmbeddingSearchPayload;
  status: "loading" | "ready" | "error";
  response: ClusterMapResponse | null;
  error: string;
};

export type ClusterMapState = ReturnType<typeof useClusterMap>;

/** The cluster map of the current REFERENCE search, cached in memory per
 * library, model, layer, seeds and limit. Closing the dialog keeps a finished
 * or running build; changing any input drops it. */
export function useClusterMap({ databaseIdentity, model, layerState, seedTracks, limit }: {
  databaseIdentity: string | null;
  model: SeedSearchModel;
  layerState: EmbeddingLayerState;
  seedTracks: Track[];
  limit: number;
}) {
  const key = JSON.stringify([
    databaseIdentity,
    model,
    layerState.layer,
    [...seedTracks]
      .sort((left, right) => left.track_id - right.track_id)
      .map((track) => [track.track_id, track.track_uuid]),
    limit,
  ]);
  const keyRef = useRef(key);
  keyRef.current = key;
  const controllerRef = useRef<AbortController | null>(null);
  const [entry, setEntry] = useState<ClusterMapEntry | null>(null);
  const [open, setOpen] = useState(false);
  const current = entry?.key === key ? entry : null;
  const reason = !databaseIdentity
    ? "Сначала откройте библиотеку."
    : model === "sonara"
      ? "Карте нужна модель с эмбеддингами: MAEST, MERT-v2, MuQ, MuQ-MuLan или CLAP."
      : !seedTracks.length
        ? "Добавьте референс, чтобы построить карту его выдачи."
        : "";
  // The body `handleEmbeddingSearch` posts to /api/search, so the map shows that exact search.
  const request: EmbeddingSearchPayload | null = reason
    || !isSeedEmbeddingFamily(model)
    || (layerState.layered && layerState.layer === null)
    ? null
    : {
      analysis_family: model,
      ...(layerState.layer !== null ? { layer: layerState.layer } : {}),
      seed_track_ids: seedTracks.map((track) => track.track_id),
      limit,
      epsilon: null,
      noise: 0,
    };

  useEffect(() => {
    controllerRef.current?.abort();
    controllerRef.current = null;
    setEntry(null);
    setOpen(false);
  }, [key]);

  useEffect(() => () => controllerRef.current?.abort(), []);

  function build() {
    if (!request) return;
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    const buildKey = key;
    const payload = request;
    const seedCatalogs = seedTracks.map((track) => track.catalog_uuid);
    const isCurrent = () => controllerRef.current === controller && keyRef.current === buildKey;
    setEntry({ key: buildKey, payload, status: "loading", response: null, error: "" });
    api.clusterMap(payload, { signal: controller.signal })
      .then((response) => {
        if (!isCurrent()) return;
        const mismatch = responseMismatch(response, payload, seedCatalogs);
        if (mismatch) throw new Error(mismatch);
        controllerRef.current = null;
        setEntry({ key: buildKey, payload, status: "ready", response, error: "" });
      })
      .catch((cause: unknown) => {
        if (!isCurrent() || isAbortError(cause)) return;
        controllerRef.current = null;
        setEntry({ key: buildKey, payload, status: "error", response: null, error: errorText(cause) });
      });
  }

  function show() {
    if (!request) return;
    if (!current || current.status === "error") build();
    setOpen(true);
  }

  // A running build keeps going behind a closed dialog; an error is not kept.
  function close() {
    setOpen(false);
    setEntry((value) => (value?.status === "error" ? null : value));
  }

  return {
    status: current?.status ?? "idle",
    entry: current,
    open: open && current !== null,
    reason,
    show,
    close,
    retry: build,
  };
}

function responseMismatch(response: ClusterMapResponse, payload: EmbeddingSearchPayload, seedCatalogs: string[]) {
  if (!response?.reference || !response.summary || !Array.isArray(response.summary.pool_preservation)
    || !Array.isArray(response.facets) || !Array.isArray(response.descriptors)
    || !Array.isArray(response.points)
    || response.points.some((point) => !point.evidence || !Array.isArray(point.evidence.contribution) || !Array.isArray(point.values))) {
    return "Сервер использует прежний формат карты. Перезапустите приложение через run_server.cmd.";
  }
  if (!seedCatalogs.every((catalog) => catalog === response.catalog_uuid)) {
    return "Карта пришла для другой библиотеки. Обновите библиотеку и постройте карту заново.";
  }
  if (response.analysis_family !== payload.analysis_family) {
    return "Карта пришла для другой модели. Постройте карту заново.";
  }
  if (payload.layer != null && response.layer !== payload.layer) {
    return `Карта пришла не для слоя L${payload.layer}. Постройте карту заново.`;
  }
  return "";
}
