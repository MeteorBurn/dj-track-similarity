import { Check, ChevronDown, ListFilter, Search, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import type { EmbeddingSource } from "./api";
import type { TextPromptAxis, TextPromptModel, TextPromptPreset } from "./textPromptPresets";
import {
  axisByKey,
  defaultNegativeWeight,
  modelAdvice,
  modelForPreset,
  presetByKey
} from "./textPromptPresets";

/**
 * Both banks are sized by the same rule, so the shorter one gets the shorter
 * field instead of a fixed box that fits neither.
 */
function bankRows(text: string) {
  return Math.min(10, Math.max(3, text.split(/\r?\n/).length));
}

/** A measured score, or a dash where that model was never scored. */
function formatMeasured(score: number | undefined) {
  return score == null ? "—" : score.toFixed(2);
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
  const [activeAxis, setActiveAxis] = useState(promptAxes[0]?.key ?? "");
  const presetMenuRef = useRef<HTMLDivElement>(null);
  const presetButtonRef = useRef<HTMLButtonElement>(null);
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
  const negativeLineCount = textNegativeQuery.split(/\r?\n/).filter((line) => line.trim()).length;
  // A preset carries the weight measured for it; a hand-written bank falls back
  // to the server default. The benchmark set these numbers, so the tab reports
  // the weight rather than offering it up for guessing.
  const appliedNegativeWeight = negativeWeight ?? defaultNegativeWeight;
  // Rank fusion was measured and rejected, so the two models are never mixed.
  // The selection instead points at whichever one was measured to rank it best,
  // and says plainly when the measurements cannot point anywhere.
  const advice = useMemo(() => modelAdvice(selectedPresetKeys), [selectedPresetKeys]);
  const advisedModel = advice.kind === "single" ? advice.model : null;
  const advisedModelLabel = advisedModel === "mulan" ? "MuQ-MuLan" : "CLAP";
  // Which axes carry the measurement the model follows, so the switch can say
  // what moved it instead of changing the select behind the user's back.
  const modelDrivingAxes = useMemo(() => {
    const labels: string[] = [];
    for (const preset of selectedPresets) {
      if (!modelForPreset(preset.key)) continue;
      const label = axisByKey(preset.axis)?.label ?? preset.axis;
      if (!labels.includes(label)) labels.push(label);
    }
    return labels;
  }, [selectedPresets]);
  const measuredPresets = useMemo(
    () =>
      selectedPresets.filter(
        (preset) => preset.measured?.clap != null || preset.measured?.mulan != null
      ),
    [selectedPresets]
  );
  const unmeasuredPresets = useMemo(
    () => selectedPresets.filter((preset) => !measuredPresets.includes(preset)),
    [selectedPresets, measuredPresets]
  );
  const drivingAxesText = `${modelDrivingAxes.length > 1 ? "осей" : "оси"} ${modelDrivingAxes.join(", ")}`;
  const modelEvidence =
    advice.kind === "single" && advisedModel === textEmbeddingFamily
      ? `${advisedModelLabel} — подставлена по замеру ${drivingAxesText}.`
      : advice.kind === "single"
        ? `Сейчас ${textModelLabel}, а замер ${drivingAxesText} указывает на ${advisedModelLabel}.`
        : advice.kind === "conflict"
          ? `Сейчас ${textModelLabel}. Выбранные оси меряны на разные модели, одного верного ответа нет, а смешивать их нельзя.`
          : `Сейчас ${textModelLabel}. Замер не указывает ни на одну модель — выбор за тобой.`;
  const activeAxisEntry = promptAxes.find((axis) => axis.key === activeAxis);
  const activeAxisModelLabel = activeAxisEntry?.model === "mulan" ? "MuQ-MuLan" : "CLAP";
  // An axis without a measured winner can still hold labels that were measured
  // one by one, and saying so is more use than a flat "no measurement".
  const activeAxisPinned = useMemo(
    () =>
      axisPresets
        .filter((preset) => preset.model)
        .map((preset) => `${preset.label} → ${preset.model === "mulan" ? "MuQ-MuLan" : "CLAP"}`),
    [axisPresets]
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
        {/* The picker leads the panel: picking measured presets is the short path
            to a working bank, and writing one by hand is the long one. */}
        <div className="text-preset-picker" ref={presetMenuRef} onKeyDown={closePresetMenuOnEscape}>
          <button
            className={`text-preset-button ${presetMenuOpen ? "active" : ""}`}
            ref={presetButtonRef}
            title="Выбрать пресеты по осям. Несколько пресетов складываются в один банк."
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
                  title={`${preset.hint} Нажмите, чтобы убрать пресет из банка.`}
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
                title="Убрать все пресеты и очистить банк"
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
                  title={`Выбрано пресетов из ${promptPresets.length} в словаре. Каждый добавляет свои строки в банк.`}
                >
                  {selectedPresets.length} / {promptPresets.length}
                </span>
                <button
                  className="text-preset-menu-close"
                  title="Закрыть выбор пресетов"
                  aria-label="Закрыть выбор пресетов"
                  onClick={() => {
                    setPresetMenuOpen(false);
                    presetButtonRef.current?.focus();
                  }}
                  type="button"
                >
                  <X size={13} strokeWidth={2.4} />
                </button>
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
                    {/* The dot marks the axes that move the model, so the rule
                        is visible before a label is picked, not after. */}
                    {axis.model ? (
                      <span className="text-preset-axis-dot" data-model={axis.model} aria-hidden="true" />
                    ) : null}
                  </button>
                ))}
              </div>
              <div className="text-preset-axis-note">
                {activeAxisEntry?.model
                  ? `Ось измерена на ${activeAxisModelLabel} — модель переключится сама.`
                  : activeAxisPinned.length
                    ? `Замера у оси нет, но отдельные метки закреплены: ${activeAxisPinned.join(", ")}.`
                    : "Замера у оси нет: размеченных примеров под её метки не набрано. Модель останется прежней — проверяй ушами."}
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
                        {active ? <Check size={14} strokeWidth={2.8} /> : null}
                      </span>
                      <span className="text-preset-option-label">
                        {preset.label}
                        {preset.model ? (
                          <span
                            className="text-preset-axis-dot"
                            data-model={preset.model}
                            aria-hidden="true"
                          />
                        ) : null}
                      </span>
                      {measured ? (
                        <span
                          className="text-preset-option-measured"
                          title={`Надёжность метки на размеченных примерах: ROC-AUC ${measured.toFixed(3)}.`}
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
        {/* Everything needed to judge a selection sits here, so the axis and
            label hints can stay plain descriptions of the sound. */}
        {selectedPresets.length ? (
          <div className="text-model-advice">
            <div className="text-evidence-row">
              <span className="text-evidence-key">Модель</span>
              <span className="text-evidence-value">{modelEvidence}</span>
            </div>
            {measuredPresets.length ? (
              <div className="text-evidence-row">
                <span className="text-evidence-key">Замер</span>
                <span className="text-evidence-value">
                  {measuredPresets
                    .map(
                      (preset) =>
                        `${preset.label} ${formatMeasured(preset.measured?.mulan)} / ${formatMeasured(preset.measured?.clap)}`
                    )
                    .join("; ")}
                  {" — ROC-AUC на размеченных примерах, MuQ-MuLan / CLAP."}
                </span>
              </div>
            ) : null}
            {unmeasuredPresets.length ? (
              <div className="text-evidence-row">
                <span className="text-evidence-key">Без замера</span>
                <span className="text-evidence-value">
                  {unmeasuredPresets.map((preset) => preset.label).join(", ")} — размеченных
                  примеров под {unmeasuredPresets.length > 1 ? "эти метки" : "эту метку"} нет,
                  надёжность неизвестна. Проверяй ушами.
                </span>
              </div>
            ) : null}
            {advisedModel && advisedModel !== textEmbeddingFamily ? (
              <button
                className="text-model-advice-switch"
                title="Переключить на модель, измеренную как лучшую для этих осей. Смешивать модели нельзя: rank fusion проверен и отклонён, он тянет сильную модель к слабой."
                onClick={() => onTextEmbeddingFamilyChange(advisedModel)}
                type="button"
              >
                Переключить на {advisedModelLabel}
              </button>
            ) : null}
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
            rows={bankRows(textQuery)}
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
                rows={bankRows(textNegativeQuery)}
                value={textNegativeQuery}
                onChange={(event) => onTextNegativeQueryChange(event.target.value)}
                placeholder={"four-on-the-floor, house, techno.\nvocal pop song."}
                title="Hard-negative банк: по одному конкурирующему классу в строке. Пресеты заполняют это поле сами."
              />
              <div className="text-negative-hint">
                Вес {appliedNegativeWeight.toFixed(2)}
                {negativeWeight === null ? " — значение по умолчанию" : " — измерен для выбранных пресетов"}.
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
      <button className="text-search-button" title={textSearchTitle} disabled={busy || !textQuery.trim() || !hasStoredTextEmbeddings} onClick={handleTextSearch} type="button">
        <Search size={17} />
        Search
      </button>
    </div>
  );
}
