import { useEffect, useRef, useState } from "react";
import { api, type EmbeddingMapResponse, type Track } from "./api";
import { errorText, isAbortError } from "./errors";

export function useMertV2Explorer(databaseIdentity: string | null, catalogUuid: string | null, layer = 24) {
  const identity = JSON.stringify([databaseIdentity, catalogUuid, layer]);
  const identityRef = useRef(identity);
  identityRef.current = identity;
  const request = useRef<AbortController | null>(null);
  const [result, setResult] = useState<{ identity: string; data: EmbeddingMapResponse } | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const data = result?.identity === identity ? result.data : null;
  const dataRef = useRef(data);
  dataRef.current = data;

  useEffect(() => {
    request.current?.abort();
    request.current = null;
    setResult(null);
    setPending(false);
    setError("");
    return () => {
      request.current?.abort();
      request.current = null;
      dataRef.current = null;
    };
  }, [identity]);

  async function buildMap(clusterCount: number) {
    if (!databaseIdentity || !catalogUuid || identityRef.current !== identity) return;
    request.current?.abort();
    const controller = new AbortController();
    request.current = controller;
    setPending(true);
    setError("");
    setResult(null);
    dataRef.current = null;
    const current = () => request.current === controller && identityRef.current === identity;
    try {
      const response = await api.embeddingMap({
        catalog_uuid: catalogUuid,
        analysis_family: "mert_v2",
        cluster_count: clusterCount,
        mert_v2_layer: layer,
      }, { signal: controller.signal });
      if (!current()) return;
      if (response.catalog_uuid !== catalogUuid || response.mert_v2_layer !== layer || response.points.some(point => point.track.catalog_uuid !== catalogUuid)) {
        throw new Error("The map belongs to a different catalog or layer. Build it again for the selected database.");
      }
      setResult({ identity, data: response });
    } catch (cause) {
      if (current() && !isAbortError(cause)) setError(errorText(cause));
    } finally {
      if (current()) {
        request.current = null;
        setPending(false);
      }
    }
  }

  function currentTrack(track: Track) {
    if (identityRef.current !== identity || dataRef.current !== data || !data) return null;
    return data.points.find(point => point.track.catalog_uuid === track.catalog_uuid
      && point.track.track_id === track.track_id && point.track.track_uuid === track.track_uuid)?.track ?? null;
  }

  function updateTrack(track: Track) {
    if (!currentTrack(track)) return;
    setResult(current => current?.identity === identity ? {
      ...current,
      data: { ...current.data, points: current.data.points.map(point => point.track.track_uuid === track.track_uuid ? { ...point, track } : point) },
    } : current);
  }

  return { data, pending, error, buildMap, currentTrack, updateTrack };
}
