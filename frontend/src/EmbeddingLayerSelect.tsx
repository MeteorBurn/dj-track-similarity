import type { EmbeddingLayerState } from "./useEmbeddingLayers";

export function EmbeddingLayerSelect({ state, modelLabel }: { state: EmbeddingLayerState; modelLabel: string }) {
  const onlyDefaultStored = state.layers?.some(row => row.track_count > 0)
    && state.layers.every(row => row.layer === state.defaultLayer || row.track_count === 0);
  return <div className="embedding-layer-select">
    <label>Слой {modelLabel}
      <select name="embedding-layer" title={state.note ?? undefined} value={state.layer ?? ""} disabled={state.loading || !state.layers} onChange={event => state.selectLayer(Number(event.target.value))}>
        {state.layers?.map(row => (
          <option key={row.layer} value={row.layer} disabled={row.track_count === 0} title={[row.source, state.note].filter(Boolean).join("\n") || undefined}>
            L{row.layer}{row.label ? ` – ${row.label}` : ""}
          </option>
        ))}
      </select>
    </label>
    {onlyDefaultStored ? <small>Сохранён только L{state.defaultLayer}. Повторный анализ заполнит остальные слои.</small> : null}
    {state.error ? <small className="error" role="alert">{state.error}</small> : !state.loading && state.layers && state.trackCount === 0 ? <small>Для L{state.layer} нет сохранённых эмбеддингов.</small> : null}
  </div>;
}
