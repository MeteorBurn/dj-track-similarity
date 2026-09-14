import type { MertV2LayerState } from "./useMertV2Layers";

const authorHints: Record<number, { label: string; tasks: string }> = {
  12: { label: "инструменты", tasks: "Instruments: MTG-Jamendo" },
  13: { label: "настроение / тема", tasks: "Mood/theme: MTG-Jamendo" },
  16: { label: "жанр", tasks: "Genre: MTG-Jamendo" },
  22: { label: "top-50 теги", tasks: "Top-50 tags: MTG-Jamendo" },
  23: { label: "доли / тональность / теги", tasks: "Beat: GTZAN; key: GiantSteps; tagging: MagnaTagATune" },
  24: { label: "жанр / эмоции", tasks: "Genre: GTZAN; emotion: EmoMusic" },
};
const hintMeaning = "Подсказки — выбор слоёв авторами MERT-v2 FullSong для обученных предсказателей на указанных задачах, а не гарантия специализации поиска похожих треков.";

export function MertV2LayerSelect({ state }: { state: MertV2LayerState }) {
  const hint = authorHints[state.layer];
  return <div className="mert-v2-layer-select">
    <label title={`${hintMeaning}${hint ? ` ${hint.tasks}.` : ""}`}>Слой MERT-v2
      <select value={state.layer} disabled={state.loading || !state.layers} onChange={event => state.selectLayer(Number(event.target.value))}>
        {Array.from({ length: 24 }, (_, index) => index + 1).map(layer => {
          const count = state.layers?.find(row => row.layer === layer)?.track_count ?? 0;
          const itemHint = authorHints[layer];
          return <option key={layer} value={layer} disabled={count === 0} title={itemHint ? `${hintMeaning} ${itemHint.tasks}.` : undefined}>
            L{layer}{itemHint ? ` — ${itemHint.label}` : ""} · {state.loading ? "…" : count}
          </option>;
        })}
      </select>
    </label>
    {state.layers?.some(row => row.track_count > 0) && state.layers.every(row => row.layer === 24 || row.track_count === 0)
      ? <small>Сохранён только L24. Повторный анализ MERT-v2 заполнит остальные слои.</small> : null}
    {state.error ? <small className="error" role="alert">{state.error}</small> : !state.loading && state.layers && state.trackCount === 0 ? <small>Для L{state.layer} нет сохранённых эмбеддингов.</small> : null}
  </div>;
}
