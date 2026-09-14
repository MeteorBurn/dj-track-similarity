import { useEffect, useRef, useState } from "react";
import { api, type MertV2LayersResponse } from "./api";
import { errorText, isAbortError } from "./errors";

export function useMertV2Layers(databasePath: string | null, catalogUuid: string | null, refreshKey: unknown) {
  const identity = JSON.stringify([databasePath, catalogUuid]);
  const identityRef = useRef(identity);
  identityRef.current = identity;
  const [selection, setSelection] = useState({ identity, layer: 24 });
  const [result, setResult] = useState<{ identity: string; data: MertV2LayersResponse } | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const layer = selection.identity === identity ? selection.layer : 24;
  const layers = result?.identity === identity ? result.data.layers : null;

  useEffect(() => {
    setSelection({ identity, layer: 24 });
  }, [identity]);

  useEffect(() => {
    setResult(null);
    setError("");
    if (!databasePath || !catalogUuid) { setLoading(false); return; }
    const controller = new AbortController();
    setLoading(true);
    const current = () => !controller.signal.aborted && identityRef.current === identity;
    void api.mertV2Layers({ signal: controller.signal }).then(data => {
      if (!current()) return;
      if (data.catalog_uuid !== catalogUuid) throw new Error("Список слоёв относится к другой базе. Обновите библиотеку.");
      setResult({ identity, data });
    }).catch(cause => {
      if (current() && !isAbortError(cause)) setError(errorText(cause));
    }).finally(() => { if (current()) setLoading(false); });
    return () => controller.abort();
  }, [identity, refreshKey]);

  function selectLayer(value: number) {
    if (identityRef.current !== identity || !layers?.some(row => row.layer === value && row.track_count > 0)) return;
    setSelection({ identity, layer: value });
  }

  return {
    layer, layers, loading, error, selectLayer,
    trackCount: layers?.find(row => row.layer === layer)?.track_count ?? 0,
  };
}

export type MertV2LayerState = ReturnType<typeof useMertV2Layers>;
