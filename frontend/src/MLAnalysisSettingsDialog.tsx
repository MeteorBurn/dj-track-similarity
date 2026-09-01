import { useEffect } from "react";
import { Cpu, FolderOpen, X } from "lucide-react";

import { NumberStepper } from "./NumberStepper";
import type { MLAnalysisSettings } from "./mlAnalysisSettings";

type DeviceMode = "auto" | "cpu" | "cuda";

export function MLAnalysisSettingsDialog({
  busy,
  stageRunning,
  hasTracks,
  mlSettings,
  onMLSettingsChange,
  onChooseMLStagingFolder,
  analysisDevice,
  onAnalysisDeviceChange,
  analysisTrackBatchSize,
  maxAnalysisTrackBatchSize,
  onAnalysisTrackBatchSizeChange,
  analysisInferenceBatchSize,
  maxAnalysisInferenceBatchSize,
  onAnalysisInferenceBatchSizeChange,
  onClose,
}: {
  busy: boolean;
  stageRunning: boolean;
  hasTracks: boolean;
  mlSettings: MLAnalysisSettings;
  onMLSettingsChange: (value: MLAnalysisSettings) => void;
  onChooseMLStagingFolder: () => void;
  analysisDevice: DeviceMode;
  onAnalysisDeviceChange: (value: DeviceMode) => void;
  analysisTrackBatchSize: number;
  maxAnalysisTrackBatchSize: number;
  onAnalysisTrackBatchSizeChange: (value: number) => void;
  analysisInferenceBatchSize: number;
  maxAnalysisInferenceBatchSize: number;
  onAnalysisInferenceBatchSizeChange: (value: number) => void;
  onClose: () => void;
}) {
  const disabled = busy || stageRunning;
  // Track/Inference batch size only mean anything once there is something to
  // batch; every other field here (device, mode, staging) can be set up front.
  const batchDisabled = disabled || !hasTracks;

  useEffect(() => {
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !disabled) onClose();
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [disabled, onClose]);

  const updateStaged = (changes: Partial<MLAnalysisSettings["staged"]>) => {
    onMLSettingsChange({
      ...mlSettings,
      staged: { ...mlSettings.staged, ...changes },
    });
  };

  return (
    <div className="ml-settings-backdrop" role="presentation">
      <section className="ml-settings-dialog" role="dialog" aria-modal="true" aria-labelledby="ml-settings-title">
        <header className="dialog-title ml-settings-title">
          <div className="ml-settings-title-copy">
            <h2 id="ml-settings-title">Настройки анализа ML моделями</h2>
            <span>Device и режим чтения файлов решают, как MAEST, MERT, MuQ, MuLan и CLAP считают эмбеддинги.</span>
          </div>
          <button className="icon-button ml-settings-close-button" title="Закрыть" aria-label="Закрыть" disabled={disabled} onClick={onClose} type="button"><X size={16} /></button>
        </header>
        <div className="ml-settings-body">
          <section className="ml-settings-section">
            <div className="ml-settings-section-title">
              <span>Устройство</span>
            </div>
            <p className="ml-settings-section-description">Устройство — определяет, какое оборудование компьютера будет использоваться для анализа. CPU использует основной процессор и работает практически на любом ПК. CUDA переносит вычисления на совместимую видеокарту NVIDIA и обычно значительно ускоряет анализ. AUTO автоматически выбирает самый подходящий доступный вариант. У SONARA такого выбора нет — это нативный Rust-анализ признаков, который всегда идёт на CPU.</p>
            <div className="analysis-device ml-settings-device">
              <span><Cpu size={15} /> Device</span>
              <div className="segmented">{(["auto", "cpu", "cuda"] as DeviceMode[]).map((device) => <button key={device} className={`analysis-device-button ${analysisDevice === device ? "active" : ""}`} title={`ML device: ${device}`} disabled={disabled} onClick={() => onAnalysisDeviceChange(device)} type="button">{device.toUpperCase()}</button>)}</div>
            </div>
          </section>
          <section className="ml-settings-section">
            <div className="ml-settings-section-title">
              <span>Режим анализа</span>
            </div>
            <p className="ml-settings-section-description">Direct — треки декодируются и передаются в ML-модели прямо с исходного диска. Staged ускоряет анализ за счёт временного копирования треков партиями на более быстрый накопитель и обработки уже с него; в отличие от SONARA здесь нет отдельных Processes/Threads — копированием партий управляет один параметр Workers, а инференс сразу проходит по всем выбранным моделям. Для Staged рекомендуется выбрать директорию на самом быстром доступном накопителе, желательно SSD.</p>
            <div className="analysis-device ml-analysis-mode">
              <span>Mode</span>
              <div className="segmented ml-mode-segmented">
                <button className={`ml-mode-button ${mlSettings.mode === "direct" ? "active" : ""}`} title="Читать исходные аудиофайлы напрямую" disabled={disabled} onClick={() => onMLSettingsChange({ ...mlSettings, mode: "direct" })} type="button">Direct</button>
                <button className={`ml-mode-button ${mlSettings.mode === "staged" ? "active" : ""}`} title="Копировать входные файлы во временную SSD-папку" disabled={disabled} onClick={() => onMLSettingsChange({ ...mlSettings, mode: "staged" })} type="button">Staged</button>
              </div>
            </div>
            {mlSettings.mode === "staged" && (
              <>
                <div className="path-row ml-staging-path-row">
                  <input value={mlSettings.staged.folder} readOnly title="Папка для временных staging-копий ML" />
                  <button className="icon-button folder-picker ml-staging-folder-picker-button" title="Choose Folder для ML staging-копий" aria-label="Choose Folder для ML staging-копий" disabled={disabled} onClick={onChooseMLStagingFolder} type="button"><FolderOpen size={17} /></button>
                </div>
                <div className="ml-staged-settings-grid">
                  <NumberStepper label="Workers" value={mlSettings.staged.workers} minimum={1} maximum={16} disabled={disabled} classPrefix="ml-workers" onChange={(workers) => updateStaged({ workers })} />
                  <NumberStepper label="StageSize" value={mlSettings.staged.stageSize} minimum={1} maximum={512} disabled={disabled} classPrefix="ml-stage-size" onChange={(stageSize) => updateStaged({ stageSize })} />
                </div>
              </>
            )}
          </section>
          <section className="ml-settings-section">
            <div className="ml-settings-section-title">
              <span>Размер батчей</span>
            </div>
            <p className="ml-settings-section-description">Track batch — сколько треков декодировать и держать в памяти за один job batch. Тип: целое число 1-64. Измеренный дефолт для этой машины: 8. Inference batch — сколько окон или семплов MAEST, MERT, MuQ и CLAP прогоняют за один forward pass модели. Тип: целое число 1-128. Измеренный дефолт для RTX 3090: 16. Оба параметра действуют одинаково в режимах Direct и Staged.</p>
            <div className="ml-settings-batch-grid">
              <NumberStepper label="Track batch" value={analysisTrackBatchSize} minimum={1} maximum={maxAnalysisTrackBatchSize} disabled={batchDisabled} classPrefix="analysis-track-batch" onChange={onAnalysisTrackBatchSizeChange} />
              <NumberStepper label="Inference batch" value={analysisInferenceBatchSize} minimum={1} maximum={maxAnalysisInferenceBatchSize} disabled={batchDisabled} classPrefix="analysis-inference-batch" onChange={onAnalysisInferenceBatchSizeChange} />
            </div>
          </section>
        </div>
        <footer className="ml-settings-footer">
          <button className="ml-settings-ok-button" title="Закрыть" disabled={disabled} onClick={onClose} type="button">OK</button>
        </footer>
      </section>
    </div>
  );
}
