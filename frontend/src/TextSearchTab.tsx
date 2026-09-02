import { Check, ChevronDown, ListFilter, Search, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import type { EmbeddingSource } from "./api";
import { api } from "./apiClient";
import type { TextPromptAxis, TextPromptModel, TextPromptPreset } from "./textPromptPresets";
import {
  axisByKey,
  defaultNegativeWeight,
  presetByKey,
  resolveNegativeWeight,
  resolvePromptVariants,
  textPromptCategories
} from "./textPromptPresets";

/**
 * Both banks grow with their content between a floor and a ceiling, so the
 * shorter one gets the shorter field instead of a fixed box that fits neither.
 *
 * The floors are generous on purpose: a selection of four labels already merges
 * sixteen positive lines, and reading a bank through a three-row slot meant
 * scrolling inside a textarea to see what the search would actually send.
 */
function bankRows(text: string, min: number, max: number) {
  return Math.min(max, Math.max(min, text.split(/\r?\n/).length));
}

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
  // Sixteen axes and 240 labels do not fit a window at once, and scrolling to a
  // remembered label is slower than typing three letters of it.
  const [labelFilter, setLabelFilter] = useState("");
  // The label under the pointer or the keyboard focus, previewed under the
  // list. A tooltip could not hold a whole prompt bank.
  const [previewPresetKey, setPreviewPresetKey] = useState<string | null>(null);
  // null while there is nothing to warm; the search itself still loads the
  // model, so a failed warmup costs the wait back rather than blocking.
  const [warmupState, setWarmupState] = useState<"warming" | "ready" | "failed" | null>(null);
  const presetMenuRef = useRef<HTMLDivElement>(null);
  const presetButtonRef = useRef<HTMLButtonElement>(null);
  const textModelLabel = textEmbeddingFamily === "mulan" ? "MuQ-MuLan" : "CLAP";
  const promptModel: TextPromptModel = textEmbeddingFamily;
  const selectedPresets = useMemo(
    () => selectedPresetKeys.map((key) => presetByKey(key)).filter(Boolean) as TextPromptPreset[],
    [selectedPresetKeys]
  );
  const previewPreset = useMemo(
    () => (previewPresetKey ? presetByKey(previewPresetKey) : undefined),
    [previewPresetKey]
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
  // A preset carries the weight measured for it; a hand-written bank falls back
  // to the server default. The benchmark set these numbers, so the tab reports
  // the weight rather than offering it up for guessing.
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
        setPresetMenuOpen(false);
      }
    }
    document.addEventListener("pointerdown", closePresetMenuOnOutsideClick);
    return () => document.removeEventListener("pointerdown", closePresetMenuOnOutsideClick);
  }, [presetMenuOpen]);

  // The first embedding after an idle period deserializes the pinned weights,
  // which is tens of seconds of silence under the first search. Opening the tab
  // or switching the model starts that load now instead. It only runs where a
  // search is possible at all, so a library with no text embeddings never pays
  // for weights it cannot use.
  useEffect(() => {
    if (!hasStoredTextEmbeddings) {
      setWarmupState(null);
      return;
    }
    const controller = new AbortController();
    setWarmupState("warming");
    api
      .textSearchWarmup({ analysis_family: textEmbeddingFamily }, { signal: controller.signal })
      .then(() => setWarmupState("ready"))
      .catch(() => {
        if (!controller.signal.aborted) setWarmupState("failed");
      });
    return () => controller.abort();
  }, [hasStoredTextEmbeddings, textEmbeddingFamily]);

  // Escape closes the picker and hands focus back to the control that owns it,
  // so the keyboard never gets stranded inside an open menu.
  function closePresetMenuOnEscape(event: { key: string; stopPropagation: () => void }) {
    if (event.key !== "Escape" || !presetMenuOpen) return;
    event.stopPropagation();
    setPresetMenuOpen(false);
    presetButtonRef.current?.focus();
  }

  return (
    <div className="search-tab-panel">
      <div className="text-search-box text-prompt-box">
        {/* The picker leads the panel: picking presets is the short path to a
            working bank, and writing one by hand is the long one. */}
        <div className="text-preset-picker" ref={presetMenuRef} onKeyDown={closePresetMenuOnEscape}>
          <button
            className={`text-preset-button ${presetMenuOpen ? "active" : ""}`}
            ref={presetButtonRef}
            title="Выбрать метки. Несколько меток складываются в один банк."
            aria-label="Выбрать prompt preset"
            aria-expanded={presetMenuOpen}
            aria-haspopup="true"
            onClick={() => setPresetMenuOpen((current) => !current)}
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
                  key={preset.key}
                  title={`${preset.hint} Нажмите, чтобы убрать метку из банка.`}
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
                    setPresetMenuOpen(false);
                    presetButtonRef.current?.focus();
                  }}
                  type="button"
                >
                  <X size={13} strokeWidth={2.4} />
                </button>
              </div>
              <input
                className="text-preset-filter"
                type="search"
                value={labelFilter}
                placeholder="Фильтр по метке"
                aria-label="Фильтр меток"
                title="Сужает список по названию метки и её описанию. Пустые оси скрываются."
                onChange={(event) => setLabelFilter(event.target.value)}
              />
              <div className="text-preset-scroll" onMouseLeave={() => setPreviewPresetKey(null)}>
                {groups.map((group) => (
                  <section className="text-preset-category" key={group.category.key}>
                    <h4 className="text-preset-category-title">{group.category.label}</h4>
                    {group.axes.map(({ axis, presets }) => {
                      const chosen = presets.filter((preset) =>
                        selectedPresetKeys.includes(preset.key)
                      ).length;
                      return (
                        <div className="text-preset-axis-block" key={axis.key}>
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
                            Вес 0 — у этой метки нет конкурирующего класса, который стоило бы вычитать.
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
        {/* Which model ranks a label best is not declared anywhere yet: it is
            decided by running both against the same bank and keeping what the
            ear kept. Until that comparison has run, the tab says so instead of
            pointing at a model it cannot justify. */}
        {selectedPresets.length ? (
          <div className="text-model-advice">
            <div className="text-evidence-row">
              <span className="text-evidence-key">Модель</span>
              <span className="text-evidence-value">
                Сейчас {textModelLabel}. Ни у одной метки нет замера, который указывал бы на модель —
                прогоняй обе и сравнивай на слух. Смешивать их нельзя: rank fusion проверен и отклонён.
              </span>
            </div>
          </div>
        ) : null}
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
            onChange={(event) => onTextQueryChange(event.target.value)}
            placeholder={"breakbeat.\nsyncopated drums, off-grid rhythm, shuffled hits."}
            title={textPromptHelp}
          />
        </label>
        <div className="text-prompt-hint">
          Каждая строка — отдельный промпт, банк усредняется. Несколько коротких формулировок
          устойчивее одной длинной.
        </div>
        {/* The toggle heads its own section, so switching negatives off takes the
            field and the weight with it instead of leaving two dead controls. */}
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
                ? `строк: ${negativeLineCount} · вес ${appliedNegativeWeight.toFixed(2)}`
                : "выключены"}
            </span>
          </button>
          {textUseNegativePrompt ? (
            <>
              <textarea
                className="text-negative-input"
                aria-label="Hard-negative банк"
                rows={bankRows(textNegativeQuery, 5, 12)}
                value={textNegativeQuery}
                onChange={(event) => onTextNegativeQueryChange(event.target.value)}
                placeholder={"four-on-the-floor, house, techno.\nvocal pop song."}
                title="Hard-negative банк: по одному конкурирующему классу в строке. Метки заполняют это поле сами."
              />
              <div className="text-negative-hint">
                Вес {appliedNegativeWeight.toFixed(2)}
                {negativeWeight === null ? " — значение по умолчанию" : " — пришёл с выбранными метками"}.
                Негативы помогают, только когда называют реальный конкурирующий класс; выдуманный
                банк по замеру ухудшает выдачу монотонно.
              </div>
            </>
          ) : negativeLineCount ? (
            <div className="text-negative-parked">
              Негативы выключены. Сохранено строк: {negativeLineCount} — вернутся вместе с тумблером.
            </div>
          ) : null}
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
      {!hasStoredTextEmbeddings ? <span className="text-search-requirement">Requires stored {textModelLabel} embeddings. Run {textModelLabel} analysis first.</span> : null}
      {warmupState && warmupState !== "ready" ? (
        <span className={`text-warmup-state ${warmupState}`} role="status">
          {warmupState === "warming"
            ? `${textModelLabel} загружается — первый поиск не будет ждать веса.`
            : `Прогреть ${textModelLabel} не удалось — веса загрузит сам поиск.`}
        </span>
      ) : null}
      <button className="text-search-button" title={textSearchTitle} disabled={busy || !textQuery.trim() || !hasStoredTextEmbeddings} onClick={handleTextSearch} type="button">
        <Search size={17} />
        Search
      </button>
    </div>
  );
}
