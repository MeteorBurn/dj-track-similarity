import { Check, ChevronDown, ListFilter, Search, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import type { EmbeddingSource } from "./api";
import type { TextPromptAxis, TextPromptModel, TextPromptPreset } from "./textPromptPresets";
import {
  axisByKey,
  defaultNegativeWeight,
  presetByKey,
  resolveNegativeWeight,
  resolvePromptVariants,
  selectedPromptOverlaps,
  textPromptCategories
} from "./textPromptPresets";

/**
 * Both banks grow with their content between a floor and a ceiling, so the
 * shorter one gets the shorter field instead of a fixed box that fits neither.
 *
 */
function bankRows(text: string, min: number, max: number) {
  return Math.min(max, Math.max(min, text.split(/\r?\n/).length));
}

export function TextSearchTab({
  textQuery,
  textNegativeQuery,
  textUseNegativePrompt,
  onTextUseNegativePromptChange,
  textEmbeddingFamily,
  onTextEmbeddingFamilyChange,
  textCompareModels,
  onTextCompareModelsChange,
  selectedPresetKeys,
  onTogglePreset,
  onClearPresets,
  promptAxes,
  promptPresets,
  negativeWeight,
  limit,
  onLimitChange,
  textPromptHelp,
  limitHelp,
  hasStoredTextEmbeddings,
  textModelLoadingLabel,
  busy,
  textSearchTitle,
  handleTextSearch
}: {
  textQuery: string;
  textNegativeQuery: string;
  textUseNegativePrompt: boolean;
  onTextUseNegativePromptChange: (value: boolean) => void;
  textEmbeddingFamily: Extract<EmbeddingSource, "clap" | "mulan">;
  onTextEmbeddingFamilyChange: (value: Extract<EmbeddingSource, "clap" | "mulan">) => void;
  textCompareModels: boolean;
  onTextCompareModelsChange: (value: boolean) => void;
  selectedPresetKeys: string[];
  onTogglePreset: (key: string) => void;
  onClearPresets: () => void;
  promptAxes: TextPromptAxis[];
  promptPresets: TextPromptPreset[];
  negativeWeight: number | null;
  limit: number;
  onLimitChange: (value: number) => void;
  textPromptHelp: string;
  limitHelp: string;
  hasStoredTextEmbeddings: boolean;
  /** Models the running search is loading into memory first, or null. */
  textModelLoadingLabel: string | null;
  busy: boolean;
  textSearchTitle: string;
  handleTextSearch: () => void;
}) {
  const [presetMenuOpen, setPresetMenuOpen] = useState(false);
  // Filtering keeps a growing label bank easy to navigate.
  const [labelFilter, setLabelFilter] = useState("");
  // The label under the pointer or the keyboard focus, previewed under the
  // list. A tooltip could not hold a whole prompt bank.
  const [previewPresetKey, setPreviewPresetKey] = useState<string | null>(null);
  const presetMenuRef = useRef<HTMLDivElement>(null);
  const presetButtonRef = useRef<HTMLButtonElement>(null);
  const textModelLabel = textEmbeddingFamily === "mulan" ? "MuQ-MuLan" : "CLAP";
  const promptModel: TextPromptModel = textEmbeddingFamily;
  const selectedPresets = useMemo(
    () => selectedPresetKeys.map((key) => presetByKey(key)).filter(Boolean) as TextPromptPreset[],
    [selectedPresetKeys]
  );
  const overlaps = selectedPromptOverlaps(selectedPresetKeys);
  const overlapNotice = overlaps.length ? (
    <div className="text-preset-overlap" role="status">
      <strong>Возможное пересечение лейблов</strong>
      <ul>
        {overlaps.map((overlap) => (
          <li key={overlap.keys.join("|")}>
            <strong>
              {overlap.keys.map((key) => {
                const preset = presetByKey(key);
                return preset
                  ? `${axisByKey(preset.axis)?.label ?? preset.axis}: ${preset.label}`
                  : key;
              }).join(" + ")}
            </strong>
            {" — "}{overlap.description}
          </li>
        ))}
      </ul>
      <span>Выбор можно оставить.</span>
    </div>
  ) : null;
  const previewPreset = useMemo(
    () => (previewPresetKey ? presetByKey(previewPresetKey) : undefined)
      ?? selectedPresets[selectedPresets.length - 1],
    [previewPresetKey, selectedPresets]
  );
  const previewPositive = useMemo(
    () => (previewPreset ? resolvePromptVariants(previewPreset.positive, promptModel) : []),
    [previewPreset, promptModel]
  );
  // A preset weighted at zero contributes no negatives at all, so the column
  // shows why it is empty instead of listing lines the bank will never carry.
  const previewNegativeWeight = previewPreset
    ? resolveNegativeWeight(previewPreset.negativeWeight, promptModel)
    : 0;
  const previewNegative = useMemo(
    () =>
      previewPreset && previewNegativeWeight > 0
        ? resolvePromptVariants(previewPreset.negative, promptModel)
        : [],
    [previewPreset, previewNegativeWeight, promptModel]
  );
  const promptLineCount = textQuery.split(/\r?\n/).filter((line) => line.trim()).length;
  const negativeLineCount = textNegativeQuery.split(/\r?\n/).filter((line) => line.trim()).length;
  // Display the model-specific composed weight used by the request builder.
  const appliedNegativeWeight = negativeWeight ?? defaultNegativeWeight;
  // The picker is one scrolling panel: a category is a divider, an axis is a
  // block under it, and the labels live inside the block. Filtering narrows the
  // labels and drops whatever axis and category is left holding none.
  const groups = useMemo(() => {
    const needle = labelFilter.trim().toLowerCase();
    const matches = (preset: TextPromptPreset) =>
      !needle
      || preset.label.toLowerCase().includes(needle)
      || preset.hint.toLowerCase().includes(needle);
    return textPromptCategories
      .map((category) => ({
        category,
        axes: promptAxes
          .filter((axis) => axis.category === category.key)
          .map((axis) => ({
            axis,
            presets: promptPresets.filter(
              (preset) => preset.axis === axis.key && matches(preset)
            )
          }))
          .filter((entry) => entry.presets.length > 0)
      }))
      .filter((group) => group.axes.length > 0);
  }, [promptAxes, promptPresets, labelFilter]);

  const visibleCount = useMemo(
    () => groups.reduce((total, group) => total + group.axes.reduce((n, e) => n + e.presets.length, 0), 0),
    [groups]
  );

  useEffect(() => {
    if (!presetMenuOpen) return;
    function closePresetMenuOnOutsideClick(event: PointerEvent) {
      const target = event.target;
      if (target instanceof Node && !presetMenuRef.current?.contains(target)) {
        closePresetMenu();
      }
    }
    document.addEventListener("pointerdown", closePresetMenuOnOutsideClick);
    return () => document.removeEventListener("pointerdown", closePresetMenuOnOutsideClick);
  }, [presetMenuOpen]);

  function closePresetMenu() {
    setPresetMenuOpen(false);
    setPreviewPresetKey(null);
  }

  // Escape closes the picker and hands focus back to the control that owns it,
  // so the keyboard never gets stranded inside an open menu.
  function closePresetMenuOnEscape(event: { key: string; stopPropagation: () => void }) {
    if (event.key !== "Escape" || !presetMenuOpen) return;
    event.stopPropagation();
    closePresetMenu();
    presetButtonRef.current?.focus();
  }

  return (
    <div className="search-tab-panel">
      <div className="text-search-box text-prompt-box">
        {/* Selected labels are the only source of the model's prompt bank. */}
        <div className="text-preset-picker" ref={presetMenuRef} onKeyDown={closePresetMenuOnEscape}>
          <button
            className={`text-preset-button ${presetMenuOpen ? "active" : ""}`}
            ref={presetButtonRef}
            title="Выбрать метки: не больше одной на каждой оси. Новая метка заменяет выбранную на той же оси."
            aria-label="Выбрать prompt preset"
            aria-expanded={presetMenuOpen}
            aria-haspopup="true"
            onClick={() => presetMenuOpen ? closePresetMenu() : setPresetMenuOpen(true)}
            type="button"
          >
            <ListFilter size={16} />
            <span className="text-preset-button-label">Presets</span>
            <span className="text-preset-button-state">
              {selectedPresets.length ? `${selectedPresets.length} выбрано` : "не выбрано"}
            </span>
            <ChevronDown className="text-preset-button-caret" size={15} />
          </button>
          {selectedPresets.length ? (
            <div className="text-preset-chips">
              {selectedPresets.map((preset) => (
                <button
                  className="text-preset-chip"
                  data-axis={preset.axis}
                  key={preset.key}
                  title={preset.hint}
                  aria-label={`Убрать метку ${axisByKey(preset.axis)?.label ?? preset.axis}: ${preset.label}`}
                  onClick={() => onTogglePreset(preset.key)}
                  type="button"
                >
                  {/* Labels repeat across axes, so a chip names the axis it came
                      from rather than leaving the bank ambiguous. */}
                  <span className="text-preset-chip-axis">
                    {axisByKey(preset.axis)?.label ?? preset.axis}
                  </span>
                  {preset.label}
                  <X size={12} strokeWidth={2.6} />
                </button>
              ))}
              <button
                className="text-preset-chip-clear"
                title="Убрать все метки и очистить банк"
                onClick={onClearPresets}
                type="button"
              >
                Clear
              </button>
            </div>
          ) : null}
          {!presetMenuOpen ? overlapNotice : null}
          {presetMenuOpen ? (
            <div className="text-preset-menu" role="group" aria-label="Prompt presets">
              <div className="text-preset-menu-header">
                <span className="text-preset-menu-title">Prompt presets</span>
                <span
                  className="text-preset-menu-count"
                  title={`Выбрано меток из ${promptPresets.length} в словаре. Каждая добавляет свои строки в банк.`}
                >
                  {selectedPresets.length} / {promptPresets.length}
                </span>
                <button
                  className="text-preset-menu-close"
                  title="Закрыть выбор меток"
                  aria-label="Закрыть выбор меток"
                  onClick={() => {
                    closePresetMenu();
                    presetButtonRef.current?.focus();
                  }}
                  type="button"
                >
                  <X size={13} strokeWidth={2.4} />
                </button>
              </div>
              {overlapNotice}
              <div className="preset-search-field">
              <Search size={17} aria-hidden="true" />
              <input
                className="text-preset-filter"
                type="search"
                value={labelFilter}
                placeholder="Найти метку или описание…"
                aria-label="Фильтр меток"
                title="Сужает список по названию метки и её описанию. Пустые оси скрываются."
                onChange={(event) => setLabelFilter(event.target.value)}
              />
              </div>
              <div className="text-preset-scroll" onMouseLeave={() => setPreviewPresetKey(null)}>
                {groups.map((group) => (
                  <section className="text-preset-category" key={group.category.key}>
                    <h4 className="text-preset-category-title">{group.category.label}</h4>
                    {group.axes.map(({ axis, presets }) => {
                      const chosen = presets.filter((preset) =>
                        selectedPresetKeys.includes(preset.key)
                      ).length;
                      return (
                        <div className="text-preset-axis-block" data-axis={axis.key} key={axis.key}>
                          <div className="text-preset-axis-head" title={axis.hint}>
                            <span className="text-preset-axis-name">{axis.label}</span>
                            <span className="text-preset-axis-count">
                              {chosen ? `${chosen} / ${presets.length}` : presets.length}
                            </span>
                          </div>
                          <div className="text-preset-axis-labels">
                            {presets.map((preset) => {
                              const active = selectedPresetKeys.includes(preset.key);
                              return (
                                <button
                                  className={`text-preset-label ${active ? "active" : ""}`}
                                  aria-pressed={active}
                                  key={preset.key}
                                  title={preset.hint}
                                  onClick={() => onTogglePreset(preset.key)}
                                  onFocus={() => setPreviewPresetKey(preset.key)}
                                  onBlur={() => setPreviewPresetKey(null)}
                                  onMouseEnter={() => setPreviewPresetKey(preset.key)}
                                  type="button"
                                >
                                  {active ? (
                                    <Check size={12} strokeWidth={3} aria-hidden="true" />
                                  ) : null}
                                  {preset.label}
                                </button>
                              );
                            })}
                          </div>
                        </div>
                      );
                    })}
                  </section>
                ))}
                {visibleCount === 0 ? (
                  <p className="text-preset-empty">Под фильтр «{labelFilter}» не подходит ни одна метка.</p>
                ) : null}
              </div>
              {/* The bank is what a label actually does, and it is far too long
                  for a tooltip, so it gets read as two columns right here. */}
              <div className="text-preset-preview">
                {previewPreset ? (
                  <>
                    <div className="text-preset-preview-hint">{previewPreset.hint}</div>
                    <div className="text-preset-preview-columns">
                      <div className="text-preset-preview-column">
                        <span className="text-preset-preview-heading">
                          Positive · строк: {previewPositive.length}
                        </span>
                        <ul>
                          {previewPositive.map((line) => (
                            <li key={line}>{line}</li>
                          ))}
                        </ul>
                      </div>
                      <div className="text-preset-preview-column">
                        <span className="text-preset-preview-heading">
                          {previewNegative.length
                            ? `Negative · вес ${previewNegativeWeight.toFixed(2)}`
                            : "Negative"}
                        </span>
                        {previewNegative.length ? (
                          <ul>
                            {previewNegative.map((line) => (
                              <li key={line}>{line}</li>
                            ))}
                          </ul>
                        ) : (
                          <p className="text-preset-preview-empty">
                            У этой метки нет негативных промптов для {textModelLabel}.
                          </p>
                        )}
                      </div>
                    </div>
                  </>
                ) : (
                  <div className="text-preset-preview-idle">
                    Наведи на метку — покажет строки, которые она добавит в банк для {textModelLabel}.
                  </div>
                )}
              </div>
            </div>
          ) : null}
        </div>
        {!presetMenuOpen && selectedPresets.map((preset) => (
          <div className="text-preset-preview-hint" key={preset.key}>{preset.hint}</div>
        ))}
        <div className="text-prompt-hint">Банк выбранных меток · {textModelLabel}</div>
        <label className="text-prompt-field" title={textPromptHelp}>
          <span className="text-field-head">
            Prompt bank
            <span
              className="text-field-count"
              title="Сколько непустых строк уйдёт в банк. Строки усредняются в один вектор."
            >
              {promptLineCount}
            </span>
          </span>
          <textarea
            className="text-prompt-input"
            rows={bankRows(textQuery, 8, 18)}
            value={textQuery}
            readOnly
            placeholder="Выберите метку, чтобы увидеть банк промптов."
            title={textPromptHelp}
          />
        </label>
        <div className="text-prompt-hint">
          Каждая строка — отдельный промпт. Их эмбеддинги усредняются внутри выбранной модели.
        </div>
        {/* Switching negatives off leaves the selected labels unchanged. */}
        <div className="text-negative-section">
          <button
            className={`text-negative-toggle ${textUseNegativePrompt ? "active" : ""}`}
            role="switch"
            aria-checked={textUseNegativePrompt}
            title="Применять Negative как hard-negative запросы. Когда выключено, текст сохраняется, но в поиск не уходит."
            onClick={() => onTextUseNegativePromptChange(!textUseNegativePrompt)}
            type="button"
          >
            <span className="text-negative-checkbox" aria-hidden="true">
              {textUseNegativePrompt ? <Check size={13} strokeWidth={2.4} /> : null}
            </span>
            <span className="text-negative-toggle-label">Negatives</span>
            <span className="text-negative-toggle-state">
              {textUseNegativePrompt
                ? negativeLineCount
                  ? `строк: ${negativeLineCount} · вес ${appliedNegativeWeight.toFixed(2)}`
                  : "строк: 0"
                : "выключены"}
            </span>
          </button>
          {textUseNegativePrompt ? (
            <textarea
              className="text-negative-input"
              aria-label="Hard-negative банк"
              rows={bankRows(textNegativeQuery, 5, 12)}
              value={textNegativeQuery}
              readOnly
              placeholder="У выбранных меток нет негативных промптов."
              title="Негативные промпты выбранных меток. Вес определяется автоматически для каждой модели."
            />
          ) : negativeLineCount ? (
            <div className="text-negative-parked">
              Негативы выключены. Сохранено строк: {negativeLineCount} — вернутся вместе с тумблером.
            </div>
          ) : null}
        </div>
      </div>
      {/* Which model ranks a label best is not written down anywhere: it is
          decided by running both and keeping what the ear kept. Each reads its
          own variant of the bank, because that is the pair that ships and there
          is no neutral wording to compare on. Opt-in: two searches and two sets
          of weights resident are a price for settling a model, not for finding
          a track. */}
      <button
        className={`text-compare-toggle ${textCompareModels ? "active" : ""}`}
        role="switch"
        aria-checked={textCompareModels}
        title="Искать обеими моделями и показать две выдачи рядом. Каждая получает свой вариант банка и автоматически учитывает оценки этого запроса."
        onClick={() => onTextCompareModelsChange(!textCompareModels)}
        type="button"
      >
        <span className="text-compare-checkbox" aria-hidden="true">
          {textCompareModels ? <Check size={13} strokeWidth={2.4} /> : null}
        </span>
        <span className="text-compare-label">A/B</span>
        <span className="text-compare-state">
          {textCompareModels ? "MuQ-MuLan и CLAP" : "одна модель"}
        </span>
      </button>
      <div className="search-filter-grid text-search-filter-grid text-group-labels">
        <label title={textCompareModels ? "В режиме A/B ищут обе модели; выбор задаёт, чей вариант банка показан в поле" : "Embedding family used for text-to-track retrieval"}>Model
          <select
            value={textEmbeddingFamily}
            onChange={(event) => onTextEmbeddingFamilyChange(event.target.value as Extract<EmbeddingSource, "clap" | "mulan">)}
          >
            <option value="clap">CLAP</option>
            <option value="mulan">MuQ-MuLan</option>
          </select>
        </label>
        <label title={limitHelp}>Limit<input type="number" value={limit} min={1} max={500} title={limitHelp} onChange={(event) => onLimitChange(Number(event.target.value))} /></label>
      </div>
      {!hasStoredTextEmbeddings ? <span className="text-search-requirement">Requires stored {textModelLabel} embeddings. Run {textModelLabel} analysis first.</span> : null}
      {textModelLoadingLabel ? (
        <span className="text-warmup-state" role="status">
          {textModelLoadingLabel} выполняет поиск…
        </span>
      ) : null}
      <button className="text-search-button" title={textSearchTitle} disabled={busy || !textQuery.trim() || !hasStoredTextEmbeddings} onClick={handleTextSearch} type="button">
        <Search size={17} />
        {textCompareModels ? "Search · A/B" : "Search"}
      </button>
    </div>
  );
}
