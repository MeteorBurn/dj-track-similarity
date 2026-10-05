import { useEffect } from "react";
import { FolderOpen, X } from "lucide-react";

import { NumberStepper } from "./NumberStepper";
import { scanFormats, type ScanImportSettings } from "./scanImportSettings";

export function ScanImportDialog({
  settings,
  onSettingsChange,
  busy,
  stageRunning,
  maxWorkers,
  onChooseFolder,
  onClose,
}: {
  settings: ScanImportSettings;
  onSettingsChange: (settings: ScanImportSettings) => void;
  busy: boolean;
  stageRunning: boolean;
  maxWorkers: number;
  onChooseFolder: () => Promise<string | null>;
  onClose: () => void;
}) {
  const disabled = busy || stageRunning;

  useEffect(() => {
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !disabled) onClose();
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [disabled, onClose]);

  const chooseFolder = async () => {
    const root = await onChooseFolder();
    if (root) onSettingsChange({ ...settings, root });
  };

  const toggleFormat = (key: string) => {
    onSettingsChange({
      ...settings,
      selectedFormats: settings.selectedFormats.includes(key)
        ? settings.selectedFormats.filter((format) => format !== key)
        : [...settings.selectedFormats, key],
    });
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

  const selectedFormatCount = settings.selectedFormats.length;

  return (
    <div className="scan-import-backdrop" role="presentation">
      <section className="scan-import-dialog" role="dialog" aria-modal="true" aria-labelledby="scan-import-title">
        <header className="dialog-title scan-import-title">
          <div className="scan-import-title-copy">
            <h2 id="scan-import-title">Настройка параметров загрузки треков в базу</h2>
            <span>Папка, форматы и длительность треков, которые попадут в базу.</span>
          </div>
          <button className="icon-button scan-import-close-button" title="Закрыть" aria-label="Закрыть" disabled={disabled} onClick={onClose} type="button"><X size={16} /></button>
        </header>
        <div className="scan-import-body">
          <section className="settings-row" aria-labelledby="scan-root-title">
            <div className="settings-row-text">
              <h3 className="settings-row-title" id="scan-root-title">Папка с треками</h3>
              <p className="settings-row-description">Выберите папку с музыкой, из которой треки будут загружаться в базу. Сканирование рекурсивное: учитываются все вложенные папки.</p>
            </div>
            <div className="settings-row-controls">
              <div className="path-row">
                <input name="scan-root" value={settings.root} readOnly placeholder="Папка не выбрана" aria-label="Папка с треками" title={settings.root || undefined} />
                <button className="icon-button folder-picker scan-import-folder-button" title="Выбрать папку" aria-label="Выбрать папку" disabled={disabled} onClick={() => void chooseFolder()} type="button"><FolderOpen size={17} /></button>
              </div>
            </div>
          </section>
          <section className="settings-row" aria-labelledby="scan-formats-title">
            <div className="settings-row-text">
              <h3 className="settings-row-title" id="scan-formats-title">
                Форматы файлов
                <span className="settings-row-aside">{selectedFormatCount} из {scanFormats.length}</span>
              </h3>
              <p className="settings-row-description">Выберите форматы файлов, которые будут загружаться в базу. Файлы остальных форматов при сканировании пропускаются.</p>
            </div>
            <div className="settings-row-controls">
              <div className="scan-import-formats" role="group" aria-label="Форматы файлов">
                {scanFormats.map(formatChip)}
              </div>
            </div>
          </section>
          <section className="settings-row" aria-labelledby="scan-duration-title">
            <div className="settings-row-text">
              <h3 className="settings-row-title" id="scan-duration-title">Длительность</h3>
              <p className="settings-row-description">Задайте минимальную и максимальную длительность треков в секундах. Файлы короче или длиннее, например джинглы или записи целых миксов, в базу не попадут.</p>
            </div>
            <div className="settings-row-controls">
              <div className="scan-import-settings">
                <label>Min, сек<input name="scan-min-duration" type="number" min={1} value={settings.minDurationSeconds} disabled={disabled} onChange={(event) => onSettingsChange({ ...settings, minDurationSeconds: event.target.value })} /></label>
                <label>Max, сек<input name="scan-max-duration" type="number" min={1} value={settings.maxDurationSeconds} disabled={disabled} onChange={(event) => onSettingsChange({ ...settings, maxDurationSeconds: event.target.value })} /></label>
              </div>
            </div>
          </section>
          <section className="settings-row" aria-labelledby="scan-speed-title">
            <div className="settings-row-text">
              <h3 className="settings-row-title" id="scan-speed-title">Скорость сканирования</h3>
              <p className="settings-row-description">Выберите, сколько файлов читается параллельно. Больше параллельных чтений ускоряет загрузку, особенно с SSD; на HDD выигрыш обычно меньше.</p>
            </div>
            <div className="settings-row-controls">
              <NumberStepper label="Workers" hint="Сколько файлов читается параллельно" value={settings.workers} minimum={1} maximum={maxWorkers} disabled={disabled} classPrefix="scan-import-workers" onChange={(workers) => onSettingsChange({ ...settings, workers })} />
            </div>
          </section>
        </div>
        <footer className="scan-import-footer">
          <button className="scan-import-ok-button" title="Закрыть" disabled={disabled} onClick={onClose} type="button">OK</button>
        </footer>
      </section>
    </div>
  );
}
