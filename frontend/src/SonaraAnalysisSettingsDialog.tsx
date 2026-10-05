import { useEffect, useState } from "react";
import { FolderOpen, Lock, X } from "lucide-react";

import { NumberStepper } from "./NumberStepper";
import {
  applySonaraBpmChange,
  maxSonaraBpm,
  maxSonaraBpmMin,
  minSonaraBpm,
  minSonaraBpmMax,
  sonaraBpmPresets,
  sonaraBpmRangeChoiceOf,
  type SonaraAnalysisSettings,
  type SonaraBpmRange,
  type SonaraBpmRangeChoice,
} from "./sonaraAnalysisSettings";

const bpmRangeChoices: readonly { key: SonaraBpmRangeChoice; label: string; title: string }[] = [
  ...sonaraBpmPresets.map((preset) => ({
    key: preset.key,
    label: preset.label,
    title: `${preset.label}: ${preset.bpmMin}–${preset.bpmMax} BPM`,
  })),
  { key: "custom", label: "Свой диапазон", title: "Границы задаются в полях BPM Min и BPM Max" },
  { key: "none", label: "Не использовать", title: "Темп SONARA без сворачивания по октавам" },
];

export function SonaraAnalysisSettingsDialog({
  busy,
  stageRunning,
  sonaraSettings,
  onSonaraSettingsChange,
  sonaraBpmRange,
  sonaraBpmRangeLocked,
  onChooseSonaraStagingFolder,
  onClose,
}: {
  busy: boolean;
  stageRunning: boolean;
  sonaraSettings: SonaraAnalysisSettings;
  onSonaraSettingsChange: (value: SonaraAnalysisSettings) => void;
  // The range the next run uses: the library's once locked, else the selected one.
  sonaraBpmRange: SonaraBpmRange;
  // The library fixes its range with the first SONARA analysis; until then the
  // dialog is where it is chosen.
  sonaraBpmRangeLocked: boolean;
  onChooseSonaraStagingFolder: () => void;
  onClose: () => void;
}) {
  const disabled = busy || stageRunning;
  const activeBpmChoice = sonaraBpmRangeLocked
    ? sonaraBpmRangeChoiceOf(sonaraBpmRange)
    : sonaraSettings.bpmRange;
  const customBpmEditable = !disabled && !sonaraBpmRangeLocked && activeBpmChoice === "custom";
  const changeCustomBpm = (change: { bpmMin?: number; bpmMax?: number }) => {
    onSonaraSettingsChange({
      ...sonaraSettings,
      ...applySonaraBpmChange(sonaraSettings, change),
    });
  };

  useEffect(() => {
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !disabled) onClose();
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [disabled, onClose]);

  const updateStaged = (changes: Partial<SonaraAnalysisSettings["staged"]>) => {
    onSonaraSettingsChange({
      ...sonaraSettings,
      staged: { ...sonaraSettings.staged, ...changes },
    });
  };

  return (
    <div className="sonara-settings-backdrop" role="presentation">
      <section className="sonara-settings-dialog" role="dialog" aria-modal="true" aria-labelledby="sonara-settings-title">
        <header className="dialog-title sonara-settings-title">
          <div className="sonara-settings-title-copy">
            <h2 id="sonara-settings-title">Настройки анализа SONARA</h2>
            <span>Режим чтения файлов и диапазон BPM решают, как проходит нативный анализ SONARA.</span>
          </div>
          <button className="icon-button sonara-settings-close-button" title="Закрыть" aria-label="Закрыть" disabled={disabled} onClick={onClose} type="button"><X size={16} /></button>
        </header>
        <div className="sonara-settings-body">
          <section className="sonara-settings-section sonara-settings-bpm-range">
            <div className="sonara-settings-section-title">
              <span>Диапазон BPM для анализа SONARA</span>
              {sonaraBpmRangeLocked && <Lock size={13} aria-hidden="true" />}
              <span className={`sonara-settings-bpm-preset-custom ${activeBpmChoice === "custom" ? "selected" : ""}`}>
                {sonaraBpmRange ? `${sonaraBpmRange.bpmMin}–${sonaraBpmRange.bpmMax}` : "Без диапазона"}
              </span>
            </div>
            <p className="sonara-settings-section-description">SONARA выбирает темп трека без учёта диапазона. Если найденный темп выходит за границы, он сворачивается по октавам: ниже нижней границы удваивается, выше верхней делится пополам, и биты, сетка и зависящие от темпа признаки строятся уже по нему. Темп внутри диапазона не меняется. «Не использовать» оставляет темп SONARA как есть.</p>
            <div className="sonara-settings-bpm-presets" aria-label="Диапазон BPM">
              {bpmRangeChoices.map((choice) => {
                const selected = activeBpmChoice === choice.key;
                return <button
                  key={choice.key}
                  className={`sonara-settings-bpm-preset-chip ${selected ? "selected" : ""}`}
                  aria-pressed={selected}
                  disabled={disabled || sonaraBpmRangeLocked}
                  title={choice.title}
                  onClick={() => onSonaraSettingsChange({ ...sonaraSettings, bpmRange: choice.key })}
                  type="button"
                >{choice.label}</button>;
              })}
            </div>
            <div className="sonara-settings-bpm-controls">
              <BpmBoundInput
                label="BPM Min"
                name="sonara-bpm-min"
                minimum={minSonaraBpm}
                maximum={maxSonaraBpmMin}
                value={sonaraBpmRange?.bpmMin ?? null}
                disabled={!customBpmEditable}
                onCommit={(bpmMin) => changeCustomBpm({ bpmMin })}
              />
              <BpmBoundInput
                label="BPM Max"
                name="sonara-bpm-max"
                minimum={minSonaraBpmMax}
                maximum={maxSonaraBpm}
                value={sonaraBpmRange?.bpmMax ?? null}
                disabled={!customBpmEditable}
                onCommit={(bpmMax) => changeCustomBpm({ bpmMax })}
              />
            </div>
            <p className="sonara-settings-bpm-hint">{sonaraBpmRangeLocked
              ? "База уже проанализирована с этим выбором. Чтобы изменить его, сбросьте анализ SONARA."
              : "Задаётся один раз: первый анализ SONARA закрепит выбор за всей базой. Свой диапазон должен охватывать октаву: верхняя граница + 1 не меньше удвоенной нижней, как 68–135 в Rekordbox."}</p>
          </section>
          <section className="sonara-settings-section">
            <div className="sonara-settings-section-title">
              <span>Режим анализа</span>
            </div>
            <p className="sonara-settings-section-description">Direct — треки декодируются и анализируются прямо с исходного диска. Staged ускоряет анализ за счёт временного копирования треков на более быстрый накопитель и обработки уже с него. Для Staged рекомендуется выбрать директорию на самом быстром доступном накопителе, желательно SSD. Это особенно полезно для библиотек, где исходный диск не успевает за скоростью анализа.</p>
            <div className="analysis-device sonara-analysis-mode">
              <span>Mode</span>
              <div className="segmented sonara-mode-segmented">
                <button className={`sonara-mode-button ${sonaraSettings.mode === "direct" ? "active" : ""}`} title="Читать исходные аудиофайлы напрямую" disabled={disabled} onClick={() => onSonaraSettingsChange({ ...sonaraSettings, mode: "direct" })} type="button">Direct</button>
                <button className={`sonara-mode-button ${sonaraSettings.mode === "staged" ? "active" : ""}`} title="Копировать входные файлы во временную SSD-папку" disabled={disabled} onClick={() => onSonaraSettingsChange({ ...sonaraSettings, mode: "staged" })} type="button">Staged</button>
              </div>
            </div>
            {sonaraSettings.mode === "staged" && (
              <div className="path-row sonara-staging-path-row">
                <input name="sonara-staging-folder" value={sonaraSettings.staged.folder} readOnly title="Папка для временных staging-копий SONARA" />
                <button className="icon-button folder-picker staging-folder-picker-button" title="Choose Folder для staging-копий" aria-label="Choose Folder для staging-копий" disabled={disabled} onClick={onChooseSonaraStagingFolder} type="button"><FolderOpen size={17} /></button>
              </div>
            )}
            {sonaraSettings.mode === "direct" ? (
              <NumberStepper label="BatchSize" value={sonaraSettings.directBatchSize} minimum={1} maximum={16} disabled={disabled} classPrefix="sonara-direct-batch" onChange={(directBatchSize) => onSonaraSettingsChange({ ...sonaraSettings, directBatchSize })} />
            ) : (
              <div className="sonara-staged-settings-grid">
                <NumberStepper label="Processes" value={sonaraSettings.staged.processes} minimum={1} maximum={16} disabled={disabled} classPrefix="sonara-processes" onChange={(processes) => updateStaged({ processes })} />
                <NumberStepper label="Threads" value={sonaraSettings.staged.threads} minimum={1} maximum={64} disabled={disabled} classPrefix="sonara-threads" onChange={(threads) => updateStaged({ threads })} />
                <NumberStepper label="BatchSize" value={sonaraSettings.staged.batchSize} minimum={1} maximum={16} disabled={disabled} classPrefix="sonara-staged-batch" onChange={(batchSize) => updateStaged({ batchSize })} />
                <NumberStepper label="StageSize" value={sonaraSettings.staged.stageSize} minimum={1} maximum={512} disabled={disabled} classPrefix="sonara-stage-size" onChange={(stageSize) => updateStaged({ stageSize })} />
              </div>
            )}
          </section>
        </div>
        <footer className="sonara-settings-footer">
          <button className="sonara-settings-ok-button" title="Закрыть" disabled={disabled} onClick={onClose} type="button">OK</button>
        </footer>
      </section>
    </div>
  );
}

// A range bound typed freely and applied on blur or Enter: clamping on every
// keystroke would turn the first digit of 48 into the lower limit.
function BpmBoundInput({
  label,
  name,
  minimum,
  maximum,
  value,
  disabled,
  onCommit,
}: {
  label: string;
  name: string;
  minimum: number;
  maximum: number;
  value: number | null;
  disabled: boolean;
  onCommit: (value: number) => void;
}) {
  const [draft, setDraft] = useState<string | null>(null);
  const commit = () => {
    if (draft === null) return;
    const parsed = Number(draft);
    setDraft(null);
    // An emptied or unreadable field keeps the bound it had.
    if (draft.trim() !== "" && Number.isFinite(parsed)) onCommit(parsed);
  };
  return (
    <label>{label}<input
      name={name}
      type="number"
      min={minimum}
      max={maximum}
      value={draft ?? value ?? ""}
      placeholder="—"
      disabled={disabled}
      onChange={(event) => setDraft(event.target.value)}
      onBlur={commit}
      onKeyDown={(event) => {
        if (event.key === "Enter") event.currentTarget.blur();
      }}
    /></label>
  );
}
