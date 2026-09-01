import { useEffect } from "react";
import { FolderOpen, Minus, Plus, X } from "lucide-react";
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
            <span>Форматы и длительность решают, что попадёт в базу.</span>
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
              <label>Min, сек<input type="number" min={1} value={settings.minDurationSeconds} disabled={disabled} onChange={(event) => onSettingsChange({ ...settings, minDurationSeconds: event.target.value })} /></label>
              <label>Max, сек<input type="number" min={1} value={settings.maxDurationSeconds} disabled={disabled} onChange={(event) => onSettingsChange({ ...settings, maxDurationSeconds: event.target.value })} /></label>
              <div className="worker-control">
                <span>Workers</span>
                <div className="stepper">
                  <button className="icon-button scan-import-workers-decrement-button" title="Уменьшить workers" disabled={disabled || settings.workers <= 1} onClick={() => onSettingsChange({ ...settings, workers: settings.workers - 1 })} type="button"><Minus size={15} /></button>
                  <input type="number" min={1} max={maxWorkers} value={settings.workers} disabled={disabled} onChange={(event) => onSettingsChange({ ...settings, workers: Math.min(maxWorkers, Math.max(1, Number(event.target.value) || 1)) })} />
                  <button className="icon-button scan-import-workers-increment-button" title="Увеличить workers" disabled={disabled || settings.workers >= maxWorkers} onClick={() => onSettingsChange({ ...settings, workers: settings.workers + 1 })} type="button"><Plus size={15} /></button>
                </div>
              </div>
            </div>
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
          <button className="scan-import-ok-button" title="Закрыть" disabled={disabled} onClick={onClose} type="button">OK</button>
        </footer>
      </section>
    </div>
  );
}
