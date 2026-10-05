import { useEffect } from "react";
import { FolderOpen, X } from "lucide-react";

import { NumberStepper } from "./NumberStepper";
import type { MLAnalysisSettings } from "./mlAnalysisSettings";

type DeviceMode = "auto" | "cpu" | "cuda";

const deviceChoices: readonly { key: DeviceMode; title: string }[] = [
  { key: "auto", title: "CUDA, если она доступна, иначе CPU" },
  { key: "cpu", title: "Основной процессор, работает на любом ПК" },
  { key: "cuda", title: "Видеокарта NVIDIA" },
];

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
            <h2 id="ml-settings-title">Настройки анализа ML-моделей</h2>
            <span>Устройство, чтение файлов и размер батчей для MAEST, MERT-v2, MuQ, MuLan и CLAP.</span>
          </div>
          <button className="icon-button ml-settings-close-button" title="Закрыть" aria-label="Закрыть" disabled={disabled} onClick={onClose} type="button"><X size={16} /></button>
        </header>
        <div className="ml-settings-body">
          <section className="settings-row" aria-labelledby="ml-device-title">
            <div className="settings-row-text">
              <h3 className="settings-row-title" id="ml-device-title">Устройство</h3>
              <p className="settings-row-description">Выберите устройство, на котором ML-модели будут анализировать треки. CPU работает на любом компьютере, но медленно. GPU (CUDA) выполняет вычисления на видеокарте и обрабатывает библиотеку в разы быстрее. Для CUDA нужны видеокарта NVIDIA и драйвер NVIDIA с поддержкой CUDA 13, отдельный CUDA Toolkit не нужен. AUTO выбирает CUDA, если она доступна, иначе CPU.</p>
            </div>
            <div className="settings-row-controls">
              <div className="segmented" role="group" aria-label="Устройство">{deviceChoices.map((device) => <button key={device.key} className={analysisDevice === device.key ? "active" : ""} aria-pressed={analysisDevice === device.key} title={device.title} disabled={disabled} onClick={() => onAnalysisDeviceChange(device.key)} type="button">{device.key.toUpperCase()}</button>)}</div>
            </div>
          </section>
          <section className="settings-row" aria-labelledby="ml-reading-title">
            <div className="settings-row-text">
              <h3 className="settings-row-title" id="ml-reading-title">Чтение файлов</h3>
              <p className="settings-row-description">Выберите, откуда модели будут читать треки. Direct читает их прямо с исходного диска и подходит, если библиотека лежит на SSD. Staged заранее копирует порции треков во временную папку и готовит их, пока модели обрабатывают предыдущие, поэтому видеокарта не простаивает, когда библиотека на HDD, USB-диске или в сети. Для Staged нужна папка на быстром диске (лучше SSD) со свободным местом, копии удаляются после обработки.</p>
            </div>
            <div className="settings-row-controls">
              <div className="segmented ml-mode-segmented" role="group" aria-label="Чтение файлов">
                <button className={`ml-mode-button ${mlSettings.mode === "direct" ? "active" : ""}`} aria-pressed={mlSettings.mode === "direct"} title="Декодировать треки прямо с исходного диска" disabled={disabled} onClick={() => onMLSettingsChange({ ...mlSettings, mode: "direct" })} type="button">Direct</button>
                <button className={`ml-mode-button ${mlSettings.mode === "staged" ? "active" : ""}`} aria-pressed={mlSettings.mode === "staged"} title="Копировать треки во временную папку и декодировать оттуда" disabled={disabled} onClick={() => onMLSettingsChange({ ...mlSettings, mode: "staged" })} type="button">Staged</button>
              </div>
              {mlSettings.mode === "staged" && (
                <>
                  <div className="path-row ml-staging-path-row">
                    <input name="ml-staging-folder" value={mlSettings.staged.folder} readOnly placeholder="Папка для временных копий не выбрана" title="Папка для временных копий треков" />
                    <button className="icon-button folder-picker ml-staging-folder-picker-button" title="Выбрать папку для временных копий" aria-label="Выбрать папку для временных копий" disabled={disabled} onClick={onChooseMLStagingFolder} type="button"><FolderOpen size={17} /></button>
                  </div>
                  <div className="ml-staged-settings-grid">
                    <NumberStepper label="Workers" hint="Сколько треков копируются и декодируются параллельно" value={mlSettings.staged.workers} minimum={1} maximum={16} disabled={disabled} classPrefix="ml-workers" onChange={(workers) => updateStaged({ workers })} />
                    <NumberStepper label="StageSize" hint="Сколько скопированных треков может лежать во временной папке одновременно" value={mlSettings.staged.stageSize} minimum={1} maximum={512} disabled={disabled} classPrefix="ml-stage-size" onChange={(stageSize) => updateStaged({ stageSize })} />
                  </div>
                </>
              )}
            </div>
          </section>
          <section className="settings-row" aria-labelledby="ml-batch-title">
            <div className="settings-row-text">
              <h3 className="settings-row-title" id="ml-batch-title">Размер батчей</h3>
              <p className="settings-row-description">Выберите, сколько треков и фрагментов аудио обрабатывать за один шаг. Track batch задаёт, сколько треков декодируется и держится в оперативной памяти одновременно, Inference batch задаёт, сколько фрагментов аудио модель обрабатывает за один проход. Большие значения обычно ускоряют анализ, но требуют больше оперативной и видеопамяти; при нехватке памяти уменьшите их. Настройки одинаково действуют в Direct и Staged.{hasTracks ? "" : " Станут доступны, когда в базе появятся треки."}</p>
            </div>
            <div className="settings-row-controls">
              <div className="ml-settings-batch-grid">
                <NumberStepper label="Track batch" hint="Сколько треков декодируется и держится в памяти за один шаг" value={analysisTrackBatchSize} minimum={1} maximum={maxAnalysisTrackBatchSize} disabled={batchDisabled} classPrefix="analysis-track-batch" onChange={onAnalysisTrackBatchSizeChange} />
                <NumberStepper label="Inference batch" hint="Сколько фрагментов аудио модель обрабатывает за один проход. Больше обычно быстрее, но занимает больше видеопамяти" value={analysisInferenceBatchSize} minimum={1} maximum={maxAnalysisInferenceBatchSize} disabled={batchDisabled} classPrefix="analysis-inference-batch" onChange={onAnalysisInferenceBatchSizeChange} />
              </div>
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
