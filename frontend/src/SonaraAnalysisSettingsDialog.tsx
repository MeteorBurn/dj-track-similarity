import { useEffect } from "react";
import { FolderOpen, Lock, X } from "lucide-react";

import { NumberStepper } from "./NumberStepper";
import {
  applySonaraBpmChange,
  matchingSonaraBpmPreset,
  maxSonaraBpm,
  minSonaraBpm,
  sonaraBpmPresets,
  type SonaraAnalysisSettings,
} from "./sonaraAnalysisSettings";

export function SonaraAnalysisSettingsDialog({
  busy,
  stageRunning,
  sonaraSettings,
  onSonaraSettingsChange,
  sonaraBpmRange,
  sonaraBpmRangeLocked,
  onSonaraBpmRangeChange,
  onChooseSonaraStagingFolder,
  onClose,
}: {
  busy: boolean;
  stageRunning: boolean;
  sonaraSettings: SonaraAnalysisSettings;
  onSonaraSettingsChange: (value: SonaraAnalysisSettings) => void;
  sonaraBpmRange: { bpmMin: number; bpmMax: number };
  // The library fixes its range with the first SONARA analysis; until then the
  // dialog is where it is chosen.
  sonaraBpmRangeLocked: boolean;
  onSonaraBpmRangeChange: (range: { bpmMin: number; bpmMax: number }) => void;
  onChooseSonaraStagingFolder: () => void;
  onClose: () => void;
}) {
  const disabled = busy || stageRunning;
  const activeBpmPreset = matchingSonaraBpmPreset(sonaraBpmRange);

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
              <span className={`sonara-settings-bpm-preset-custom ${activeBpmPreset ? "" : "selected"}`}>
                {activeBpmPreset ? `${activeBpmPreset.bpmMin}–${activeBpmPreset.bpmMax}` : "Свой диапазон"}
              </span>
            </div>
            <p className="sonara-settings-section-description">Диапазон BPM определяет, в каких пределах SONARA ищет темп трека. Правильный диапазон помогает избежать ошибок вроде 64 вместо 128 BPM. Для большинства библиотек подойдут готовые диапазоны Rekordbox, VirtualDJ или Mixed In Key, при необходимости можно задать свой.</p>
            <div className="sonara-settings-bpm-presets" aria-label="Пресеты диапазона BPM">
              {sonaraBpmPresets.map((preset) => {
                const selected = activeBpmPreset?.key === preset.key;
                return <button
                  key={preset.key}
                  className={`sonara-settings-bpm-preset-chip ${selected ? "selected" : ""}`}
                  aria-pressed={selected}
                  disabled={disabled || sonaraBpmRangeLocked}
                  title={`${preset.label}: ${preset.bpmMin}–${preset.bpmMax} BPM`}
                  onClick={() => onSonaraBpmRangeChange({ bpmMin: preset.bpmMin, bpmMax: preset.bpmMax })}
                  type="button"
                >{preset.label}</button>;
              })}
            </div>
            <div className="sonara-settings-bpm-controls">
              <label>BPM Min<input
                type="number"
                min={minSonaraBpm}
                max={Math.floor(maxSonaraBpm / 2)}
                value={sonaraBpmRange.bpmMin}
                disabled={disabled || sonaraBpmRangeLocked}
                onChange={(event) => onSonaraBpmRangeChange(applySonaraBpmChange(sonaraBpmRange, { bpmMin: Number(event.target.value) || minSonaraBpm }))}
              /></label>
              <label>BPM Max<input
                type="number"
                min={2 * minSonaraBpm}
                max={maxSonaraBpm}
                value={sonaraBpmRange.bpmMax}
                disabled={disabled || sonaraBpmRangeLocked}
                onChange={(event) => onSonaraBpmRangeChange(applySonaraBpmChange(sonaraBpmRange, { bpmMax: Number(event.target.value) || 2 * minSonaraBpm }))}
              /></label>
            </div>
            <p className="sonara-settings-bpm-hint">{sonaraBpmRangeLocked
              ? "База уже проанализирована этим диапазоном. Чтобы задать другой, сбросьте анализ SONARA."
              : "Выберите пресет или введите свой диапазон. Задаётся один раз: первый анализ SONARA закрепит его за всей базой. Верхняя граница должна быть минимум вдвое больше нижней."}</p>
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
                <input value={sonaraSettings.staged.folder} readOnly title="Папка для временных staging-копий SONARA" />
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
