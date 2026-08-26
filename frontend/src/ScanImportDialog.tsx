import { useEffect, useState } from "react";
import { FolderOpen, Lock, Minus, Play, Plus, X } from "lucide-react";

import {
  applySonaraBpmChange,
  matchingSonaraBpmPreset,
  maxSonaraBpm,
  minSonaraBpm,
  sonaraBpmPresets,
} from "./sonaraAnalysisSettings";

export type ScanImportRequest = {
  root: string;
  workers: number;
  limit?: number;
  extensions: string[];
  min_duration_seconds?: number;
  max_duration_seconds?: number;
};

type ScanImportSettings = {
  root: string;
  selectedFormats: string[];
  minDurationSeconds: string;
  maxDurationSeconds: string;
  scanLimit: number;
  workers: number;
};

const scanFormats = [
  { key: "aac", label: "AAC", extensions: [".aac"] },
  { key: "aif", label: "AIF", extensions: [".aif"] },
  { key: "aiff", label: "AIFF", extensions: [".aiff"] },
  { key: "alac", label: "ALAC", extensions: [".alac"] },
  { key: "ape", label: "APE", extensions: [".ape"] },
  { key: "flac", label: "FLAC", extensions: [".flac"] },
  { key: "m4a", label: "M4A", extensions: [".m4a"] },
  { key: "mp3", label: "MP3", extensions: [".mp3"] },
  { key: "ogg", label: "OGG", extensions: [".ogg"] },
  { key: "opus", label: "OPUS", extensions: [".opus"] },
  { key: "wav", label: "WAV", extensions: [".wav"] },
  { key: "wave", label: "WAVE", extensions: [".wave"] },
  { key: "wma", label: "WMA", extensions: [".wma"] },
  { key: "wv", label: "WavPack", extensions: [".wv"] },
] as const;

export function defaultScanImportSettings(): ScanImportSettings {
  return {
    root: "",
    selectedFormats: scanFormats.map((format) => format.key),
    minDurationSeconds: "120",
    maxDurationSeconds: "1200",
    scanLimit: 0,
    workers: 8,
  };
}

function boundValue(value: string): number | undefined {
  if (!value.trim()) return undefined;
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : undefined;
}

export function ScanImportDialog({
  busy,
  stageRunning,
  maxWorkers,
  sonaraBpmRange,
  sonaraBpmRangeLocked,
  onSonaraBpmRangeChange,
  onChooseFolder,
  onClose,
  onStart,
}: {
  busy: boolean;
  stageRunning: boolean;
  maxWorkers: number;
  sonaraBpmRange: { bpmMin: number; bpmMax: number };
  // The library fixes its range with the first SONARA analysis; until then the
  // dialog is where it is chosen.
  sonaraBpmRangeLocked: boolean;
  onSonaraBpmRangeChange: (range: { bpmMin: number; bpmMax: number }) => void;
  onChooseFolder: () => Promise<string | null>;
  onClose: () => void;
  onStart: (request: ScanImportRequest) => Promise<void>;
}) {
  const [settings, setSettings] = useState(defaultScanImportSettings);
  const [validationError, setValidationError] = useState("");
  const disabled = busy || stageRunning;
  const minDurationSeconds = boundValue(settings.minDurationSeconds);
  const maxDurationSeconds = boundValue(settings.maxDurationSeconds);
  const hasInvalidBound = Boolean(
    (settings.minDurationSeconds.trim() && minDurationSeconds == null)
    || (settings.maxDurationSeconds.trim() && maxDurationSeconds == null)
    || (minDurationSeconds != null && maxDurationSeconds != null && minDurationSeconds > maxDurationSeconds),
  );
  const canStart = Boolean(settings.root && settings.selectedFormats.length && !hasInvalidBound && !disabled);
  const activeBpmPreset = matchingSonaraBpmPreset(sonaraBpmRange);

  useEffect(() => {
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !disabled) onClose();
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [disabled, onClose]);

  const chooseFolder = async () => {
    const root = await onChooseFolder();
    if (root) {
      setSettings((current) => ({ ...current, root }));
      setValidationError("");
    }
  };

  const toggleFormat = (key: string) => {
    setSettings((current) => ({
      ...current,
      selectedFormats: current.selectedFormats.includes(key)
        ? current.selectedFormats.filter((format) => format !== key)
        : [...current.selectedFormats, key],
    }));
  };

  const formatChip = (format: (typeof scanFormats)[number]) => {
    const selected = settings.selectedFormats.includes(format.key);
    return <button
      key={format.key}
      className={`scan-import-format-chip ${selected ? "selected" : ""}`}
      aria-pressed={selected}
      disabled={disabled}
      title={`${selected ? "Исключить" : "Включить"} ${format.label}`}
      onClick={() => toggleFormat(format.key)}
      type="button"
    >{format.label}</button>;
  };

  const start = async () => {
    if (!canStart) {
      setValidationError("Выберите папку, хотя бы один формат и корректный диапазон длительности.");
      return;
    }
    setValidationError("");
    await onStart({
      root: settings.root,
      workers: settings.workers,
      limit: settings.scanLimit > 0 ? settings.scanLimit : undefined,
      extensions: scanFormats
        .filter((format) => settings.selectedFormats.includes(format.key))
        .flatMap((format) => format.extensions),
      min_duration_seconds: minDurationSeconds,
      max_duration_seconds: maxDurationSeconds,
    });
  };

  const selectedFormatCount = settings.selectedFormats.length;

  return (
    <div className="scan-import-backdrop" role="presentation">
      <section className="scan-import-dialog" role="dialog" aria-modal="true" aria-labelledby="scan-import-title">
        <header className="dialog-title scan-import-title">
          <div className="scan-import-title-copy">
            <h2 id="scan-import-title">Настройка параметров загрузки треков в базу</h2>
            <span>Форматы, длительность и диапазон BPM решают, что попадёт в базу.</span>
          </div>
          <button className="icon-button scan-import-close-button" title="Закрыть" aria-label="Закрыть" disabled={disabled} onClick={onClose} type="button"><X size={16} /></button>
        </header>
        <div className="scan-import-body">
          <section className="scan-import-section">
            <div className="scan-import-section-title">
              <span>Форматы файлов</span>
              <span className="scan-import-section-counter">{selectedFormatCount} из {scanFormats.length}</span>
            </div>
            <div className="scan-import-formats" aria-label="Форматы треков">
              {scanFormats.map(formatChip)}
            </div>
          </section>
          <section className="scan-import-section">
            <div className="scan-import-section-title">
              <span>Границы отбора</span>
            </div>
            <div className="scan-import-settings">
              <div className="worker-control scan-import-limit-control">
                <span title="Сканирование останавливается, когда в базу добавлено столько новых треков. 0 = без ограничения.">Scan limit</span>
                <div className="stepper">
                  <button className="icon-button scan-import-limit-decrement-button" title="Уменьшить Scan limit" disabled={disabled || settings.scanLimit <= 0} onClick={() => setSettings((current) => ({ ...current, scanLimit: Math.max(0, current.scanLimit - 1) }))} type="button"><Minus size={15} /></button>
                  <input type="number" min={0} max={100000} value={settings.scanLimit} aria-label="Scan limit: сколько новых треков добавить в базу, 0 = все подходящие" disabled={disabled} onChange={(event) => setSettings((current) => ({ ...current, scanLimit: Math.min(100000, Math.max(0, Number(event.target.value) || 0)) }))} />
                  <button className="icon-button scan-import-limit-increment-button" title="Увеличить Scan limit" disabled={disabled || settings.scanLimit >= 100000} onClick={() => setSettings((current) => ({ ...current, scanLimit: current.scanLimit + 1 }))} type="button"><Plus size={15} /></button>
                </div>
              </div>
              <label>Min, сек<input type="number" min={1} value={settings.minDurationSeconds} disabled={disabled} onChange={(event) => setSettings((current) => ({ ...current, minDurationSeconds: event.target.value }))} /></label>
              <label>Max, сек<input type="number" min={1} value={settings.maxDurationSeconds} disabled={disabled} onChange={(event) => setSettings((current) => ({ ...current, maxDurationSeconds: event.target.value }))} /></label>
              <div className="worker-control">
                <span>Workers</span>
                <div className="stepper">
                  <button className="icon-button scan-import-workers-decrement-button" title="Уменьшить workers" disabled={disabled || settings.workers <= 1} onClick={() => setSettings((current) => ({ ...current, workers: current.workers - 1 }))} type="button"><Minus size={15} /></button>
                  <input type="number" min={1} max={maxWorkers} value={settings.workers} disabled={disabled} onChange={(event) => setSettings((current) => ({ ...current, workers: Math.min(maxWorkers, Math.max(1, Number(event.target.value) || 1)) }))} />
                  <button className="icon-button scan-import-workers-increment-button" title="Увеличить workers" disabled={disabled || settings.workers >= maxWorkers} onClick={() => setSettings((current) => ({ ...current, workers: current.workers + 1 }))} type="button"><Plus size={15} /></button>
                </div>
              </div>
            </div>
          </section>
          <section className="scan-import-section scan-import-bpm-range">
            <div className="scan-import-section-title">
              <span>Диапазон BPM для анализа SONARA</span>
              {sonaraBpmRangeLocked && <Lock size={13} aria-hidden="true" />}
              <span className={`scan-import-bpm-preset-custom ${activeBpmPreset ? "" : "selected"}`}>
                {activeBpmPreset ? `${activeBpmPreset.bpmMin}–${activeBpmPreset.bpmMax}` : "Свой диапазон"}
              </span>
            </div>
            <div className="scan-import-bpm-presets" aria-label="Пресеты диапазона BPM">
              {sonaraBpmPresets.map((preset) => {
                const selected = activeBpmPreset?.key === preset.key;
                return <button
                  key={preset.key}
                  className={`scan-import-bpm-preset-chip ${selected ? "selected" : ""}`}
                  aria-pressed={selected}
                  disabled={disabled || sonaraBpmRangeLocked}
                  title={`${preset.label}: ${preset.bpmMin}–${preset.bpmMax} BPM`}
                  onClick={() => onSonaraBpmRangeChange({ bpmMin: preset.bpmMin, bpmMax: preset.bpmMax })}
                  type="button"
                >{preset.label}</button>;
              })}
            </div>
            <div className="scan-import-bpm-controls">
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
            <p className="scan-import-bpm-hint">{sonaraBpmRangeLocked
              ? "База уже проанализирована этим диапазоном. Чтобы задать другой, сбросьте анализ SONARA."
              : "Выберите пресет или введите свой диапазон. Задаётся один раз: первый анализ SONARA закрепит его за всей базой. Верхняя граница должна быть минимум вдвое больше нижней."}</p>
          </section>
          <section className="scan-import-section">
            <div className="scan-import-section-title">
              <span>Папка с треками</span>
            </div>
            <p className="scan-import-description">Выберите папку как источник для загрузки треков в базу: сканирование папок выполняется рекурсивно.</p>
            <div className="path-row scan-import-path-row">
              <input value={settings.root} readOnly placeholder="Папка не выбрана" aria-label="Папка с треками" />
              <button className="icon-button folder-picker scan-import-folder-button" title="Выбрать папку на сервере" aria-label="Выбрать папку на сервере" disabled={disabled} onClick={() => void chooseFolder()} type="button"><FolderOpen size={17} /></button>
            </div>
          </section>
        </div>
        <footer className="scan-import-footer">
          {validationError && <p className="scan-import-validation" role="alert">{validationError}</p>}
          <button className="scan-import-submit-button" title="Запустить загрузку треков с выбранными параметрами" disabled={!canStart} onClick={() => void start()} type="button"><Play size={15} />Старт</button>
        </footer>
      </section>
    </div>
  );
}
