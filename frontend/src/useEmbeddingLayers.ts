import { useEffect, useRef, useState } from "react";
import { api, type EmbeddingLayersResponse, type LayeredEmbeddingFamily } from "./api";
import { errorText, isAbortError } from "./errors";
import type { SeedSearchModel } from "./searchSurfaceState";

// Families with a layer list; its count, default, labels and blends come from the server.
const layeredFamilies: readonly LayeredEmbeddingFamily[] = ["mert_v2", "sheetsage2", "muq", "maest"];

export function useEmbeddingLayers(family: SeedSearchModel, databasePath: string | null, catalogUuid: string | null, refreshKey: unknown) {
  const layeredFamily = layeredFamilies.find(name => name === family) ?? null;
  const identity = JSON.stringify([family, databasePath, catalogUuid]);
  const identityRef = useRef(identity);
  identityRef.current = identity;
  // blendLayer is the second layer of a blended search; null searches one layer.
  const [selection, setSelection] = useState<{ identity: string; layer: number | null; blendLayer: number | null }>({ identity, layer: null, blendLayer: null });
  const [result, setResult] = useState<{ identity: string; data: EmbeddingLayersResponse } | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const layer = selection.identity === identity ? selection.layer : null;
  const blendLayer = selection.identity === identity ? selection.blendLayer : null;
  const coverage = result?.identity === identity ? result.data : null;
  const layers = coverage?.layers ?? null;
  const blends = coverage?.blends ?? [];

  useEffect(() => {
    setSelection({ identity, layer: null, blendLayer: null });
  }, [identity]);

  useEffect(() => {
    setResult(null);
    setError("");
    if (!layeredFamily || !databasePath || !catalogUuid) { setLoading(false); return; }
    const controller = new AbortController();
    setLoading(true);
    const current = () => !controller.signal.aborted && identityRef.current === identity;
    void api.embeddingLayers(layeredFamily, { signal: controller.signal }).then(data => {
      if (!current()) return;
      if (data.catalog_uuid !== catalogUuid) throw new Error("Список слоёв относится к другой базе. Обновите библиотеку.");
      setResult({ identity, data });
      setSelection(chosen => chosen.identity === identity && chosen.layer !== null ? chosen : { identity, layer: data.default_layer, blendLayer: null });
    }).catch(cause => {
      if (current() && !isAbortError(cause)) setError(errorText(cause));
    }).finally(() => { if (current()) setLoading(false); });
    return () => controller.abort();
  }, [identity, refreshKey]);

  function selectLayer(value: number, blend: number | null = null) {
    if (identityRef.current !== identity) return;
    const stored = blend === null
      ? layers?.some(row => row.layer === value && row.track_count > 0)
      : blends.some(row => row.layer === value && row.blend_layer === blend && row.track_count > 0);
    if (stored) setSelection({ identity, layer: value, blendLayer: blend });
  }

  return {
    layered: layeredFamily !== null,
    layer, blendLayer, layers, blends, loading, error, selectLayer,
    label: layer === null ? null : blendLayer === null ? `L${layer}` : `L${layer}+L${blendLayer}`,
    defaultLayer: coverage?.default_layer ?? null,
    note: coverage?.note ?? null,
    trackCount: (blendLayer === null
      ? layers?.find(row => row.layer === layer)
      : blends.find(row => row.layer === layer && row.blend_layer === blendLayer))?.track_count ?? 0,
  };
}

export type EmbeddingLayerState = ReturnType<typeof useEmbeddingLayers>;
