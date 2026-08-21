import { Check, ListFilter, Search, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import type { EmbeddingSource } from "./api";
import type { TextPromptAxis, TextPromptModel, TextPromptPreset } from "./textPromptPresets";
import {
  defaultNegativeWeight,
  modelAdvice,
  negativeWeightRange,
  presetByKey
} from "./textPromptPresets";

export function ClapSearchTab({
  textQuery,
  onTextQueryChange,
  clapNegativeQuery,
  onClapNegativeQueryChange,
  clapUseNegativePrompt,
  onClapUseNegativePromptChange,
  textEmbeddingFamily,
  onTextEmbeddingFamilyChange,
  selectedPresetKeys,
  onTogglePreset,
  onClearPresets,
  promptAxes,
  promptPresets,
  negativeWeight,
  onNegativeWeightChange,
  limit,
  onLimitChange,
  textPromptHelp,
  limitHelp,
  hasStoredTextEmbeddings,
  busy,
  textSearchTitle,
  handleTextSearch
}: {
  textQuery: string;
  onTextQueryChange: (value: string) => void;
  clapNegativeQuery: string;
  onClapNegativeQueryChange: (value: string) => void;
  clapUseNegativePrompt: boolean;
  onClapUseNegativePromptChange: (value: boolean) => void;
  textEmbeddingFamily: Extract<EmbeddingSource, "clap" | "mulan">;
  onTextEmbeddingFamilyChange: (value: Extract<EmbeddingSource, "clap" | "mulan">) => void;
  selectedPresetKeys: string[];
  onTogglePreset: (key: string) => void;
  onClearPresets: () => void;
  promptAxes: TextPromptAxis[];
  promptPresets: TextPromptPreset[];
  negativeWeight: number | null;
  onNegativeWeightChange: (value: number) => void;
  limit: number;
  onLimitChange: (value: number) => void;
  textPromptHelp: string;
  limitHelp: string;
  hasStoredTextEmbeddings: boolean;
  busy: boolean;
  textSearchTitle: string;
  handleTextSearch: () => void;
}) {
  const [presetMenuOpen, setPresetMenuOpen] = useState(false);
  const [activeAxis, setActiveAxis] = useState(promptAxes[0]?.key ?? "");
  const presetMenuRef = useRef<HTMLDivElement>(null);
  const textModelLabel = textEmbeddingFamily === "mulan" ? "MuQ-MuLan" : "CLAP";
  const promptModel: TextPromptModel = textEmbeddingFamily;
  const axisPresets = useMemo(
    () => promptPresets.filter((preset) => preset.axis === activeAxis),
    [promptPresets, activeAxis]
  );
  const selectedPresets = useMemo(
    () => selectedPresetKeys.map((key) => presetByKey(key)).filter(Boolean) as TextPromptPreset[],
    [selectedPresetKeys]
  );
  const promptLineCount = textQuery.split(/\r?\n/).filter((line) => line.trim()).length;
  // A preset carries the weight measured for it; with a hand-written bank the
  // server default applies until the slider moves.
  const appliedNegativeWeight = negativeWeight ?? defaultNegativeWeight;
  // Rank fusion was measured and rejected, so the two models are never mixed.
  // The selection instead points at whichever one was measured to rank it best,
  // and says plainly when the measurements cannot point anywhere.
  const advice = useMemo(() => modelAdvice(selectedPresetKeys), [selectedPresetKeys]);
  const advisedModel = advice.kind === "single" ? advice.model : null;
  const advisedModelLabel = advisedModel === "mulan" ? "MuQ-MuLan" : "CLAP";

  useEffect(() => {
    if (!presetMenuOpen) return;
    function closePresetMenuOnOutsideClick(event: PointerEvent) {
      const target = event.target;
      if (target instanceof Node && !presetMenuRef.current?.contains(target)) {
        setPresetMenuOpen(false);
      }
    }
    document.addEventListener("pointerdown", closePresetMenuOnOutsideClick);
    return () => document.removeEventListener("pointerdown", closePresetMenuOnOutsideClick);
  }, [presetMenuOpen]);

  return (
    <div className="search-tab-panel" role="tabpanel">
      <div className="text-search-box clap-text-search-box">
        <label className="clap-query-field clap-group-label" title={textPromptHelp}>
          Prompt bank
          <textarea
            className="clap-query-input"
            rows={4}
            value={textQuery}
            onChange={(event) => onTextQueryChange(event.target.value)}
            placeholder={"A breakbeat track.\nA track with broken drums and syncopated percussion."}
            title={textPromptHelp}
          />
        </label>
        <div className="clap-prompt-toolbar">
          <div className="clap-prompt-actions" ref={presetMenuRef}>
            <button
              className={`clap-toolbar-button clap-preset-toolbar-control clap-presets-button ${presetMenuOpen ? "active" : ""}`}
              title="Выбрать пресеты по осям. Несколько пресетов складываются в один банк."
              aria-label="Выбрать prompt preset"
              aria-expanded={presetMenuOpen}
              onClick={() => setPresetMenuOpen((current) => !current)}
              type="button"
            >
              <ListFilter size={12} />
              Пресеты
            </button>
            {selectedPresets.length ? (
              <div className="clap-preset-chips">
                {selectedPresets.map((preset) => (
                  <button
                    className="clap-preset-chip"
                    key={preset.key}
                    title={`${preset.hint} Нажмите, чтобы убрать пресет из банка.`}
                    onClick={() => onTogglePreset(preset.key)}
                    type="button"
                  >
                    {preset.label}
                    <X size={12} strokeWidth={2.6} />
                  </button>
                ))}
                <button
                  className="clap-preset-chip-clear"
                  title="Убрать все пресеты и очистить банк"
                  onClick={onClearPresets}
                  type="button"
                >
                  Очистить
                </button>
              </div>
            ) : null}
            {presetMenuOpen ? (
              <div className="clap-preset-menu" role="menu">
                <div className="clap-preset-axes">
                  {promptAxes.map((axis) => (
                    <button
                      className={`clap-preset-axis-button ${activeAxis === axis.key ? "active" : ""}`}
                      key={axis.key}
                      title={axis.hint}
                      onClick={() => setActiveAxis(axis.key)}
                      type="button"
                    >
                      {axis.label}
                    </button>
                  ))}
                </div>
                <div className="clap-preset-options">
                  {axisPresets.map((preset) => {
                    const active = selectedPresetKeys.includes(preset.key);
                    const measured = preset.measured?.[promptModel];
                    return (
                      <button
                        className={`clap-preset-option-button ${active ? "active" : ""}`}
                        key={preset.key}
                        title={preset.hint}
                        onClick={() => onTogglePreset(preset.key)}
                        type="button"
                      >
                        <span className="clap-preset-option-check" aria-hidden="true">
                          {active ? <Check size={13} strokeWidth={2.6} /> : null}
                        </span>
                        <span className="clap-preset-option-label">{preset.label}</span>
                        {measured ? (
                          <span
                            className="clap-preset-option-measured"
                            title={`Замер ROC-AUC для ${textModelLabel}: ${measured.toFixed(3)}`}
                          >
                            {measured.toFixed(2)}
                          </span>
                        ) : (
                          <span
                            className="clap-preset-option-measured unvalidated"
                            title="Надёжность не измерена: нет размеченных примеров под этот ярлык. Проверяй ушами."
                          >
                            —
                          </span>
                        )}
                      </button>
                    );
                  })}
                </div>
              </div>
            ) : null}
          </div>
          <label
            className={`clap-toolbar-button clap-negative-toggle clap-preset-toolbar-control ${clapUseNegativePrompt ? "intent-add active" : ""}`}
            title="Применять Negative как hard-negative запросы. Тип: чекбокс. Когда выключено, текст остаётся в поле, но в поиск не уходит."
          >
            <input
              type="checkbox"
              aria-label="Use negative prompt"
              checked={clapUseNegativePrompt}
              onChange={(event) => onClapUseNegativePromptChange(event.target.checked)}
            />
            <span className="clap-negative-checkbox" aria-hidden="true">
              {clapUseNegativePrompt ? <Check size={12} strokeWidth={2.4} /> : null}
            </span>
            Негативы
          </label>
        </div>
        {selectedPresets.length && advisedModel && advisedModel !== textEmbeddingFamily ? (
          <div className="clap-model-advice">
            <span>
              Выбранные оси лучше ранжирует {advisedModelLabel}. Сейчас выбрана {textModelLabel}.
            </span>
            <button
              className="clap-model-advice-switch"
              title="Переключить на модель, измеренную как лучшую для этих осей. Смешивать модели нельзя: rank fusion проверен и отклонён, он тянет сильную модель к слабой."
              onClick={() => onTextEmbeddingFamilyChange(advisedModel)}
              type="button"
            >
              Переключить на {advisedModelLabel}
            </button>
          </div>
        ) : null}
        {selectedPresets.length && advice.kind === "conflict" ? (
          <div className="clap-model-advice">
            <span>
              Оси разошлись: часть меряна на MuQ-MuLan, часть на CLAP. Одного верного ответа нет,
              а смешивать модели нельзя — фьюжн проверен и отклонён.
            </span>
          </div>
        ) : null}
        {selectedPresets.length && advice.kind === "unmeasured" ? (
          <div className="clap-model-advice">
            <span>
              Надёжность этих меток не измерена: подходящего эталона под них нет. Модель выбирай
              ушами, а выдачу проверяй на слух.
            </span>
          </div>
        ) : null}
        <label
          className="clap-negative-field clap-group-label"
          title="Hard-negative банк: по одному конкурирующему классу в строке. Пресеты заполняют это поле сами."
        >
          Negative
          <textarea
            className="clap-negative-input"
            rows={3}
            value={clapNegativeQuery}
            onChange={(event) => onClapNegativeQueryChange(event.target.value)}
            placeholder={"A four-on-the-floor house track.\nA vocal pop song."}
            title="Hard-negative банк: по одному конкурирующему классу в строке."
            disabled={!clapUseNegativePrompt}
          />
        </label>
        <div className="clap-negative-weight-row">
          <label title="Насколько сильно вычитать совпадение с негативами. Замер: там, где негативы называют реальный конкурирующий класс, качество растёт до 0.75-1.0; там, где банк негативов выдуман, оно падает монотонно.">
            Вес негативов
            <input
              type="range"
              min={negativeWeightRange.min}
              max={negativeWeightRange.max}
              step={negativeWeightRange.step}
              value={appliedNegativeWeight}
              disabled={!clapUseNegativePrompt}
              onChange={(event) => onNegativeWeightChange(Number(event.target.value))}
            />
          </label>
          <span className="clap-negative-weight-value">{appliedNegativeWeight.toFixed(2)}</span>
        </div>
        <div className="clap-prompt-hint">
          Каждая строка — отдельный промпт, банк усредняется. Несколько коротких формулировок
          устойчивее одной длинной. Сейчас в банке: {promptLineCount}.
        </div>
      </div>
      <div className="search-filter-grid clap-search-filter-grid clap-group-labels">
        <label title="Embedding family used for text-to-track retrieval">Model
          <select
            value={textEmbeddingFamily}
            onChange={(event) => onTextEmbeddingFamilyChange(event.target.value as Extract<EmbeddingSource, "clap" | "mulan">)}
          >
            <option value="mulan">MuQ-MuLan</option>
            <option value="clap">CLAP</option>
          </select>
        </label>
        <label title={limitHelp}>Limit<input type="number" value={limit} min={1} max={500} title={limitHelp} onChange={(event) => onLimitChange(Number(event.target.value))} /></label>
      </div>
      <button className="clap-text-search-button" title={textSearchTitle} disabled={busy || !textQuery.trim() || !hasStoredTextEmbeddings} onClick={handleTextSearch} type="button">
        <Search size={17} />
        Search
      </button>
      {!hasStoredTextEmbeddings ? <span className="clap-search-requirement">Requires stored {textModelLabel} embeddings. Run {textModelLabel} analysis first.</span> : null}
    </div>
  );
}
