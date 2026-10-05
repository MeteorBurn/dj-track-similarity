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
  { key: "none", label: "Не использовать", title: "Темп SONARA как есть, без сворачивания" },
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
            <span>Диапазон BPM и чтение файлов для анализа SONARA. Считает всегда на CPU.</span>
          </div>
          <button className="icon-button sonara-settings-close-button" title="Закрыть" aria-label="Закрыть" disabled={disabled} onClick={onClose} type="button"><X size={16} /></button>
        </header>
        <div className="sonara-settings-body">
          <section className="settings-row" aria-labelledby="sonara-bpm-range-title">
            <div className="settings-row-text">
              <h3 className="settings-row-title" id="sonara-bpm-range-title">
                Диапазон BPM
                {sonaraBpmRangeLocked && <Lock size={13} aria-hidden="true" />}
                <span className={`settings-row-aside ${activeBpmChoice === "custom" ? "selected" : ""}`}>
                  {sonaraBpmRange ? `${sonaraBpmRange.bpmMin}–${sonaraBpmRange.bpmMax}` : "Без диапазона"}
                </span>
              </h3>
              <p className="settings-row-description">Выберите диапазон, в который SONARA приведёт темп треков. Алгоритмы определения темпа часто путают половинный и двойной темп (64 BPM вместо 128), поэтому темп ниже диапазона удваивается, выше делится пополам, а биты и сетка строятся по исправленному значению. Пресеты повторяют окна Rekordbox и Mixed In Key, чтобы BPM совпадал с этими программами. «Не использовать» оставляет темп SONARA как есть.</p>
            </div>
            <div className="settings-row-controls">
              <div className="segmented sonara-bpm-segmented" role="group" aria-label="Диапазон BPM">
                {bpmRangeChoices.map((choice) => {
                  const selected = activeBpmChoice === choice.key;
                  return <button
                    key={choice.key}
                    className={selected ? "active" : ""}
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
                : activeBpmChoice === "custom"
                  ? "Первый анализ SONARA закрепит выбор за базой. Диапазон должен охватывать октаву: BPM Max + 1 не меньше 2 × BPM Min, например 68–135."
                  : "Первый анализ SONARA закрепит выбор за базой."}</p>
            </div>
          </section>
          <section className="settings-row" aria-labelledby="sonara-reading-title">
            <div className="settings-row-text">
              <h3 className="settings-row-title" id="sonara-reading-title">Чтение файлов</h3>
              <p className="settings-row-description">Выберите, откуда SONARA будет читать треки. Direct читает их прямо с исходного диска и подходит, если библиотека лежит на SSD. Staged заранее копирует порции треков во временную папку и анализирует их там несколькими процессами, поэтому анализ не упирается в медленный HDD, USB-диск или сеть. Для Staged нужна папка на быстром диске (лучше SSD) со свободным местом, копии удаляются после обработки.</p>
            </div>
            <div className="settings-row-controls">
              <div className="segmented sonara-mode-segmented" role="group" aria-label="Чтение файлов">
                <button className={`sonara-mode-button ${sonaraSettings.mode === "direct" ? "active" : ""}`} aria-pressed={sonaraSettings.mode === "direct"} title="Анализировать треки прямо с исходного диска" disabled={disabled} onClick={() => onSonaraSettingsChange({ ...sonaraSettings, mode: "direct" })} type="button">Direct</button>
                <button className={`sonara-mode-button ${sonaraSettings.mode === "staged" ? "active" : ""}`} aria-pressed={sonaraSettings.mode === "staged"} title="Копировать треки во временную папку и анализировать оттуда" disabled={disabled} onClick={() => onSonaraSettingsChange({ ...sonaraSettings, mode: "staged" })} type="button">Staged</button>
              </div>
              {sonaraSettings.mode === "staged" && (
                <div className="path-row sonara-staging-path-row">
                  <input name="sonara-staging-folder" value={sonaraSettings.staged.folder} readOnly placeholder="Папка для временных копий не выбрана" title="Папка для временных копий треков" />
                  <button className="icon-button folder-picker staging-folder-picker-button" title="Выбрать папку для временных копий" aria-label="Выбрать папку для временных копий" disabled={disabled} onClick={onChooseSonaraStagingFolder} type="button"><FolderOpen size={17} /></button>
                </div>
              )}
              {sonaraSettings.mode === "direct" ? (
                <NumberStepper label="BatchSize" hint="Сколько файлов SONARA анализирует параллельно за один вызов" value={sonaraSettings.directBatchSize} minimum={1} maximum={16} disabled={disabled} classPrefix="sonara-direct-batch" onChange={(directBatchSize) => onSonaraSettingsChange({ ...sonaraSettings, directBatchSize })} />
              ) : (
                <div className="sonara-stepper-grid">
                  <NumberStepper label="Processes" hint="Сколько процессов SONARA работают параллельно" value={sonaraSettings.staged.processes} minimum={1} maximum={16} disabled={disabled} classPrefix="sonara-processes" onChange={(processes) => updateStaged({ processes })} />
                  <NumberStepper label="Threads" hint="Сколько потоков у каждого процесса" value={sonaraSettings.staged.threads} minimum={1} maximum={64} disabled={disabled} classPrefix="sonara-threads" onChange={(threads) => updateStaged({ threads })} />
                  <NumberStepper label="BatchSize" hint="Сколько файлов каждый процесс анализирует за один вызов" value={sonaraSettings.staged.batchSize} minimum={1} maximum={16} disabled={disabled} classPrefix="sonara-staged-batch" onChange={(batchSize) => updateStaged({ batchSize })} />
                  <NumberStepper label="StageSize" hint="Сколько скопированных треков может лежать во временной папке одновременно" value={sonaraSettings.staged.stageSize} minimum={1} maximum={512} disabled={disabled} classPrefix="sonara-stage-size" onChange={(stageSize) => updateStaged({ stageSize })} />
                </div>
              )}
            </div>
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
      disabled={disabled}
      onChange={(event) => setDraft(event.target.value)}
      onBlur={commit}
      onKeyDown={(event) => {
        if (event.key === "Enter") event.currentTarget.blur();
      }}
    /></label>
  );
}
