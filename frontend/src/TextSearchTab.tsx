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

export function TextSearchTab({
  textQuery,
  onTextQueryChange,
  textNegativeQuery,
  onTextNegativeQueryChange,
  textUseNegativePrompt,
  onTextUseNegativePromptChange,
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
  textNegativeQuery: string;
  onTextNegativeQueryChange: (value: string) => void;
  textUseNegativePrompt: boolean;
  onTextUseNegativePromptChange: (value: boolean) => void;
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
      <div className="text-search-box text-prompt-box">
        <label className="text-prompt-field text-group-label" title={textPromptHelp}>
          Prompt bank
          <textarea
            className="text-prompt-input"
            rows={4}
            value={textQuery}
            onChange={(event) => onTextQueryChange(event.target.value)}
            placeholder={"breakbeat.\nsyncopated drums, off-grid rhythm, shuffled hits."}
            title={textPromptHelp}
          />
        </label>
        <div className="text-prompt-toolbar">
          <div className="text-prompt-actions" ref={presetMenuRef}>
            <button
              className={`text-toolbar-button text-search-toolbar-control text-preset-menu-button ${presetMenuOpen ? "active" : ""}`}
              title="Выбрать пресеты по осям. Несколько пресетов складываются в один банк."
              aria-label="Выбрать prompt preset"
              aria-expanded={presetMenuOpen}
              onClick={() => setPresetMenuOpen((current) => !current)}
              type="button"
            >
              <ListFilter size={12} />
              Presets
            </button>
            {selectedPresets.length ? (
              <div className="text-preset-chips">
                {selectedPresets.map((preset) => (
                  <button
                    className="text-preset-chip"
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
                  className="text-preset-chip-clear"
                  title="Убрать все пресеты и очистить банк"
                  onClick={onClearPresets}
                  type="button"
                >
                  Clear
                </button>
              </div>
            ) : null}
            {presetMenuOpen ? (
              <div className="text-preset-menu">
                <div className="text-preset-menu-header">
                  <span className="text-preset-menu-title">Prompt presets</span>
                  <span
                    className="text-preset-menu-count"
                    title={`Выбрано пресетов из ${promptPresets.length} в словаре. Каждый добавляет свои строки в банк.`}
                  >
                    {selectedPresets.length} / {promptPresets.length}
                  </span>
                </div>
                <div className="text-preset-axes">
                  {promptAxes.map((axis) => (
                    <button
                      className={`text-preset-axis-button ${activeAxis === axis.key ? "active" : ""}`}
                      aria-pressed={activeAxis === axis.key}
                      key={axis.key}
                      title={axis.hint}
                      onClick={() => setActiveAxis(axis.key)}
                      type="button"
                    >
                      {axis.label}
                    </button>
                  ))}
                </div>
                <div className="text-preset-options">
                  {axisPresets.map((preset) => {
                    const active = selectedPresetKeys.includes(preset.key);
                    const measured = preset.measured?.[promptModel];
                    return (
                      <button
                        className={`text-preset-option-button ${active ? "active" : ""}`}
                        aria-pressed={active}
                        key={preset.key}
                        title={preset.hint}
                        onClick={() => onTogglePreset(preset.key)}
                        type="button"
                      >
                        <span className="text-preset-option-check" aria-hidden="true">
                          {active ? <Check size={12} strokeWidth={2.8} /> : null}
                        </span>
                        <span className="text-preset-option-label">{preset.label}</span>
                        {measured ? (
                          <span
                            className="text-preset-option-measured"
                            title={`Замер ROC-AUC для ${textModelLabel}: ${measured.toFixed(3)}`}
                          >
                            {measured.toFixed(2)}
                          </span>
                        ) : (
                          <span
                            className="text-preset-option-measured unvalidated"
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
            className={`text-toolbar-button text-negative-toggle text-search-toolbar-control ${textUseNegativePrompt ? "intent-add active" : ""}`}
            title="Применять Negative как hard-negative запросы. Тип: чекбокс. Когда выключено, текст остаётся в поле, но в поиск не уходит."
          >
            <input
              type="checkbox"
              aria-label="Use negative prompt"
              checked={textUseNegativePrompt}
              onChange={(event) => onTextUseNegativePromptChange(event.target.checked)}
            />
            <span className="text-negative-checkbox" aria-hidden="true">
              {textUseNegativePrompt ? <Check size={12} strokeWidth={2.4} /> : null}
            </span>
            Negatives
          </label>
        </div>
        {selectedPresets.length && advisedModel && advisedModel !== textEmbeddingFamily ? (
          <div className="text-model-advice">
            <span>
              Выбранные оси лучше ранжирует {advisedModelLabel}. Сейчас выбрана {textModelLabel}.
            </span>
            <button
              className="text-model-advice-switch"
              title="Переключить на модель, измеренную как лучшую для этих осей. Смешивать модели нельзя: rank fusion проверен и отклонён, он тянет сильную модель к слабой."
              onClick={() => onTextEmbeddingFamilyChange(advisedModel)}
              type="button"
            >
              Переключить на {advisedModelLabel}
            </button>
          </div>
        ) : null}
        {selectedPresets.length && advice.kind === "conflict" ? (
          <div className="text-model-advice">
            <span>
              Оси разошлись: часть меряна на MuQ-MuLan, часть на CLAP. Одного верного ответа нет,
              а смешивать модели нельзя — фьюжн проверен и отклонён.
            </span>
          </div>
        ) : null}
        {selectedPresets.length && advice.kind === "unmeasured" ? (
          <div className="text-model-advice">
            <span>
              Надёжность этих меток не измерена: подходящего эталона под них нет. Модель выбирай
              ушами, а выдачу проверяй на слух.
            </span>
          </div>
        ) : null}
        <label
          className="text-negative-field text-group-label"
          title="Hard-negative банк: по одному конкурирующему классу в строке. Пресеты заполняют это поле сами."
        >
          Negative
          <textarea
            className="text-negative-input"
            rows={3}
            value={textNegativeQuery}
            onChange={(event) => onTextNegativeQueryChange(event.target.value)}
            placeholder={"four-on-the-floor, house, techno.\nvocal pop song."}
            title="Hard-negative банк: по одному конкурирующему классу в строке."
            disabled={!textUseNegativePrompt}
          />
        </label>
        <div className="text-negative-weight-row">
          <label title="Насколько сильно вычитать совпадение с негативами. Замер: там, где негативы называют реальный конкурирующий класс, качество растёт до 0.75-1.0; там, где банк негативов выдуман, оно падает монотонно.">
            Вес негативов
            <input
              type="range"
              min={negativeWeightRange.min}
              max={negativeWeightRange.max}
              step={negativeWeightRange.step}
              value={appliedNegativeWeight}
              disabled={!textUseNegativePrompt}
              onChange={(event) => onNegativeWeightChange(Number(event.target.value))}
            />
          </label>
          <span className="text-negative-weight-value">{appliedNegativeWeight.toFixed(2)}</span>
        </div>
        <div className="text-prompt-hint">
          Каждая строка — отдельный промпт, банк усредняется. Несколько коротких формулировок
          устойчивее одной длинной. Сейчас в банке: {promptLineCount}.
        </div>
      </div>
      <div className="search-filter-grid text-search-filter-grid text-group-labels">
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
      <button className="text-search-button" title={textSearchTitle} disabled={busy || !textQuery.trim() || !hasStoredTextEmbeddings} onClick={handleTextSearch} type="button">
        <Search size={17} />
        Search
      </button>
      {!hasStoredTextEmbeddings ? <span className="text-search-requirement">Requires stored {textModelLabel} embeddings. Run {textModelLabel} analysis first.</span> : null}
    </div>
  );
}
