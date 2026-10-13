import type { EmbeddingLayerState } from "./useEmbeddingLayers";

export function EmbeddingLayerSelect({ state, modelLabel }: { state: EmbeddingLayerState; modelLabel: string }) {
  const onlyDefaultStored = state.layers?.some(row => row.track_count > 0)
    && state.layers.every(row => row.layer === state.defaultLayer || row.track_count === 0);
  // A blend's option value is both of its layers, "13+12".
  const value = state.layer === null ? "" : state.blendLayer === null ? `${state.layer}` : `${state.layer}+${state.blendLayer}`;
  return <div className="embedding-layer-select">
    <label>Слой {modelLabel}
      <select name="embedding-layer" title={state.note ?? undefined} value={value} disabled={state.loading || !state.layers} onChange={event => {
        const [layer, blendLayer] = event.target.value.split("+").map(Number);
        state.selectLayer(layer, blendLayer ?? null);
      }}>
        {state.layers?.map(row => (
          <option key={row.layer} value={row.layer} disabled={row.track_count === 0} title={[row.source, state.note].filter(Boolean).join("\n") || undefined}>
            L{row.layer}{row.label ? ` – ${row.label}` : ""}
          </option>
        ))}
        {state.blends.map(row => (
          <option key={`${row.layer}+${row.blend_layer}`} value={`${row.layer}+${row.blend_layer}`} disabled={row.track_count === 0}
            title={`Выберите, чтобы искать по двум слоям сразу. Оценка трека равна среднему его похожести по L${row.layer} и по L${row.blend_layer}, поэтому выше оказываются треки, близкие в обоих слоях. Нужны оба слоя в базе; новые данные не записываются.`}>
            L{row.layer}+L{row.blend_layer} – среднее двух слоёв
          </option>
        ))}
      </select>
    </label>
    {onlyDefaultStored ? <small>Сохранён только L{state.defaultLayer}. Повторный анализ заполнит остальные слои.</small> : null}
    {state.error ? <small className="error" role="alert">{state.error}</small> : !state.loading && state.layers && state.trackCount === 0 ? <small>Для {state.label} нет сохранённых эмбеддингов.</small> : null}
  </div>;
}
