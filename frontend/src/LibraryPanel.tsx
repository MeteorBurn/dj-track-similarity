import { Cpu, Database, FolderOpen, Minus, Play, Plus, RefreshCcw, Save, ShieldCheck, Trash2 } from "lucide-react";
import { AnalysisModel } from "./api";
import { mlAnalysisModelOrder, type AnalysisSelection } from "./analysisSelection";
import type { SonaraAnalysisSettings } from "./sonaraAnalysisSettings";

type DeviceMode = "auto" | "cpu" | "cuda";

type LibraryHelpText = {
  databasePath: string;
  musicRoot: string;
  scanWorkers: string;
  refreshTags: string;
  clearDatabase: string;
  sonaraAnalyze: string;
  maestAnalyze: string;
  mertAnalyze: string;
  muqAnalyze: string;
  clapAnalyze: string;
  writeMaestGenres: string;
  analyzeLimit: string;
  analysisDevice: string;
  analysisTrackBatchSize: string;
  analysisInferenceBatchSize: string;
};

const modelDescriptions: Record<AnalysisModel, string> = {
  sonara: "Считает темп, тональность, ритм, динамику, тембр и структуру трека.",
  maest: "Помогает понять жанровый характер трека.",
  mert: "Ищет похожее звучание от выбранного seed-трека.",
  muq: "Сохраняет дополнительный слой аудио-признаков.",
  mulan: "Связывает текстовое описание с отдельными аудио-эмбеддингами.",
  clap: "Связывает текстовое описание с аудио-звучанием."
};

function NumberStepper({
  label,
  value,
  minimum,
  maximum,
  disabled,
  classPrefix,
  onChange,
}: {
  label: string;
  value: number;
  minimum: number;
  maximum: number;
  disabled: boolean;
  classPrefix: string;
  onChange: (value: number) => void;
}) {
  const update = (value: number) => onChange(
    Math.min(maximum, Math.max(minimum, Math.trunc(value) || minimum)),
  );
  return (
    <div className="worker-control">
      <span>{label}</span>
      <div className="stepper">
        <button className={`icon-button number-stepper-decrement-button ${classPrefix}-decrement-button`} title={`Уменьшить ${label}`} disabled={disabled || value <= minimum} onClick={() => update(value - 1)} type="button"><Minus size={15} /></button>
        <input type="number" min={minimum} max={maximum} value={value} disabled={disabled} onChange={(event) => update(Number(event.target.value))} />
        <button className={`icon-button number-stepper-increment-button ${classPrefix}-increment-button`} title={`Увеличить ${label}`} disabled={disabled || value >= maximum} onClick={() => update(value + 1)} type="button"><Plus size={15} /></button>
      </div>
    </div>
  );
}

export function LibraryPanel({
  databasePath,
  onChooseDatabase,
  musicRoot,
  onMusicRootChange,
  busy,
  stageRunning,
  canStartScan,
  hasTracks,
  maestGenreTrackCount,
  scanWorkers,
  maxScanWorkers,
  adjustScanWorkers,
  onScanWorkersChange,
  analysisLimit,
  onAnalysisLimitChange,
  analysisDevice,
  onAnalysisDeviceChange,
  analysisTrackBatchSize,
  maxAnalysisTrackBatchSize,
  adjustAnalysisTrackBatchSize,
  onAnalysisTrackBatchSizeChange,
  analysisInferenceBatchSize,
  maxAnalysisInferenceBatchSize,
  adjustAnalysisInferenceBatchSize,
  onAnalysisInferenceBatchSizeChange,
  sonaraSettings,
  onSonaraSettingsChange,
  onChooseStagingFolder,
  helpText,
  onChooseFolder,
  onScan,
  onRefreshTags,
  onWriteMaestGenres,
  onClearDatabase,
  onValidateDatabase,
  analysisCounts,
  selectedAnalysisModels,
  onToggleAnalysisModel,
  onAnalyzeSelected,
  onResetAnalysis,
}: {
  databasePath: string | null;
  onChooseDatabase: () => void;
  musicRoot: string;
  onMusicRootChange: (value: string) => void;
  busy: boolean;
  stageRunning: boolean;
  canStartScan: boolean;
  hasTracks: boolean;
  maestGenreTrackCount: number;
  scanWorkers: number;
  maxScanWorkers: number;
  adjustScanWorkers: (delta: number) => void;
  onScanWorkersChange: (value: number) => void;
  analysisLimit: number;
  onAnalysisLimitChange: (value: number) => void;
  analysisDevice: DeviceMode;
  onAnalysisDeviceChange: (value: DeviceMode) => void;
  analysisTrackBatchSize: number;
  maxAnalysisTrackBatchSize: number;
  adjustAnalysisTrackBatchSize: (delta: number) => void;
  onAnalysisTrackBatchSizeChange: (value: number) => void;
  analysisInferenceBatchSize: number;
  maxAnalysisInferenceBatchSize: number;
  adjustAnalysisInferenceBatchSize: (delta: number) => void;
  onAnalysisInferenceBatchSizeChange: (value: number) => void;
  sonaraSettings: SonaraAnalysisSettings;
  onSonaraSettingsChange: (value: SonaraAnalysisSettings) => void;
  onChooseStagingFolder: () => void;
  helpText: LibraryHelpText;
  onChooseFolder: () => void;
  onScan: () => void;
  onRefreshTags: () => void;
  onWriteMaestGenres: () => void;
  onClearDatabase: () => void;
  onValidateDatabase: () => void;
  analysisCounts: Record<AnalysisSelection, number>;
  selectedAnalysisModels: AnalysisSelection[];
  onToggleAnalysisModel: (model: AnalysisSelection) => void;
  onAnalyzeSelected: () => void;
  onResetAnalysis: (adapter: AnalysisModel) => void;
}) {
  const analysisDisabled = busy || stageRunning || !hasTracks;
  const settingsDisabled = busy || stageRunning;
  const updateStaged = (changes: Partial<SonaraAnalysisSettings["staged"]>) => {
    onSonaraSettingsChange({
      ...sonaraSettings,
      staged: { ...sonaraSettings.staged, ...changes },
    });
  };

  const modelRow = (model: AnalysisModel) => (
    <div className="analysis-model-row" key={model}>
      <span className="analysis-model-check">
        <input
          className="analysis-model-checkbox"
          type="checkbox"
          aria-label={`${model.toUpperCase()} selected`}
          checked={selectedAnalysisModels.includes(model)}
          disabled={busy || stageRunning}
          onChange={() => onToggleAnalysisModel(model)}
        />
      </span>
      <span className="analysis-model-name">
        <span className="analysis-model-title">{model.toUpperCase()}</span>
        <span className="analysis-model-description">{modelDescriptions[model]}</span>
      </span>
      <span className="analysis-model-count">{analysisCounts[model] || 0}</span>
      <button className={`icon-button stop-button analysis-reset-button ${model}-reset-button`} disabled={analysisDisabled} title={`Сбросить ${model.toUpperCase()}`} onClick={() => onResetAnalysis(model)} type="button">
        <Trash2 size={16} />
      </button>
    </div>
  );

  return (
    <aside className="panel library-panel">
      <div className="panel-title"><FolderOpen size={18} /><h2>1. База и анализ</h2></div>
      <div className="path-row database-path-row">
        <input value={databasePath || ""} readOnly placeholder="Выберите SQLite базу" title={helpText.databasePath} />
        <button className="icon-button folder-picker database-picker-button" title="Выбрать SQLite базу" aria-label="Выбрать SQLite базу" disabled={busy || stageRunning} onClick={onChooseDatabase} type="button"><Database size={17} /></button>
      </div>
      <div className="path-row library-path-row">
        <input value={musicRoot} onChange={(event) => onMusicRootChange(event.target.value)} placeholder="D:/Music" title={helpText.musicRoot} />
        <button className="icon-button folder-picker library-folder-picker-button" title="Выбрать папку" aria-label="Выбрать папку" disabled={busy || stageRunning} onClick={onChooseFolder} type="button"><FolderOpen size={17} /></button>
      </div>
      <div className="worker-control" title={helpText.scanWorkers}>
        <span>Scan workers</span>
        <div className="stepper">
          <button className="icon-button scan-workers-decrement-button" title="Уменьшить количество потоков сканирования" disabled={busy || scanWorkers <= 1} onClick={() => adjustScanWorkers(-1)} aria-label="Уменьшить количество потоков сканирования" type="button"><Minus size={15} /></button>
          <input type="number" min={1} max={maxScanWorkers} value={scanWorkers} onChange={(event) => onScanWorkersChange(Math.min(maxScanWorkers, Math.max(1, Number(event.target.value) || 1)))} />
          <button className="icon-button scan-workers-increment-button" title="Увеличить количество потоков сканирования" disabled={busy || scanWorkers >= maxScanWorkers} onClick={() => adjustScanWorkers(1)} aria-label="Увеличить количество потоков сканирования" type="button"><Plus size={15} /></button>
        </div>
      </div>
      <div className="scan-action-row">
        <button className="scan-start-button" title="Загрузить треки в SQLite" disabled={busy || stageRunning || !canStartScan} onClick={onScan} type="button"><Play size={15} />Загрузить треки в базу</button>
        <button className="icon-button refresh-tags-button" disabled={busy || stageRunning || !hasTracks} title={helpText.refreshTags} onClick={onRefreshTags} type="button"><RefreshCcw size={17} /></button>
        <button className="icon-button genre-save-button" disabled={busy || stageRunning || !maestGenreTrackCount} title={helpText.writeMaestGenres} onClick={onWriteMaestGenres} type="button"><Save size={17} /></button>
        <button className="icon-button database-validation-button" disabled={busy || stageRunning || !databasePath} title="Проверить целостность и сохранённые данные базы без изменений" onClick={onValidateDatabase} type="button"><ShieldCheck size={17} /></button>
        <button className="icon-button stop-button database-clear-button" disabled={busy || stageRunning || !hasTracks} title={helpText.clearDatabase} onClick={onClearDatabase} type="button"><Trash2 size={17} /></button>
      </div>

      <div className="analysis-models-heading">
        <span>Анализ</span>
        <small>Один запуск обработает выбранные стадии и пропустит уже готовые результаты</small>
      </div>
      <div className="analysis-family-card sonara-analysis-block">
        <div className="analysis-actions">{modelRow("sonara")}</div>
        <div className="analysis-settings-grid sonara-analysis-settings">
          <div className="analysis-device sonara-analysis-mode">
            <span>Mode</span>
            <div className="segmented sonara-mode-segmented">
              <button className={`sonara-mode-button ${sonaraSettings.mode === "direct" ? "active" : ""}`} title="Читать исходные аудиофайлы напрямую" disabled={settingsDisabled} onClick={() => onSonaraSettingsChange({ ...sonaraSettings, mode: "direct" })} type="button">Direct</button>
              <button className={`sonara-mode-button ${sonaraSettings.mode === "staged" ? "active" : ""}`} title="Копировать входные файлы во временную SSD-папку" disabled={settingsDisabled} onClick={() => onSonaraSettingsChange({ ...sonaraSettings, mode: "staged" })} type="button">Staged</button>
            </div>
          </div>
          {sonaraSettings.mode === "staged" && (
            <div className="path-row sonara-staging-path-row">
              <input value={sonaraSettings.staged.folder} readOnly title="Папка для временных staging-копий SONARA" />
              <button className="icon-button folder-picker staging-folder-picker-button" title="Choose Folder для staging-копий" aria-label="Choose Folder для staging-копий" disabled={settingsDisabled} onClick={onChooseStagingFolder} type="button"><FolderOpen size={17} /></button>
            </div>
          )}
          {sonaraSettings.mode === "direct" ? (
            <NumberStepper label="BatchSize" value={sonaraSettings.directBatchSize} minimum={1} maximum={16} disabled={settingsDisabled} classPrefix="sonara-direct-batch" onChange={(directBatchSize) => onSonaraSettingsChange({ ...sonaraSettings, directBatchSize })} />
          ) : (
            <div className="sonara-staged-settings-grid">
              <NumberStepper label="Processes" value={sonaraSettings.staged.processes} minimum={1} maximum={16} disabled={settingsDisabled} classPrefix="sonara-processes" onChange={(processes) => updateStaged({ processes })} />
              <NumberStepper label="Threads" value={sonaraSettings.staged.threads} minimum={1} maximum={64} disabled={settingsDisabled} classPrefix="sonara-threads" onChange={(threads) => updateStaged({ threads })} />
              <NumberStepper label="BatchSize" value={sonaraSettings.staged.batchSize} minimum={1} maximum={16} disabled={settingsDisabled} classPrefix="sonara-staged-batch" onChange={(batchSize) => updateStaged({ batchSize })} />
              <NumberStepper label="StageSize" value={sonaraSettings.staged.stageSize} minimum={1} maximum={512} disabled={settingsDisabled} classPrefix="sonara-stage-size" onChange={(stageSize) => updateStaged({ stageSize })} />
            </div>
          )}
        </div>
      </div>

      <div className="analysis-family-card models-analysis-block">
        <div className="analysis-family-title"><strong>ML-модели</strong><small>Выберите нужные способы анализа звучания</small></div>
        <div className="analysis-actions">{mlAnalysisModelOrder.map(modelRow)}</div>
        <div className="analysis-settings-grid ml-analysis-settings">
          <div className="analysis-device" title={helpText.analysisDevice}>
            <span><Cpu size={15} /> Device</span>
            <div className="segmented">{(["auto", "cpu", "cuda"] as DeviceMode[]).map((device) => <button key={device} className={`analysis-device-button ${analysisDevice === device ? "active" : ""}`} title={`ML device: ${device}`} disabled={busy || stageRunning} onClick={() => onAnalysisDeviceChange(device)} type="button">{device.toUpperCase()}</button>)}</div>
          </div>
          <div className="worker-control">
            <span>Track batch</span>
            <div className="stepper">
              <button className="icon-button analysis-track-batch-decrement-button" title="Уменьшить ML track batch size" disabled={analysisDisabled || analysisTrackBatchSize <= 1} onClick={() => adjustAnalysisTrackBatchSize(-1)} type="button"><Minus size={15} /></button>
              <input type="number" min={1} max={maxAnalysisTrackBatchSize} value={analysisTrackBatchSize} onChange={(event) => onAnalysisTrackBatchSizeChange(Math.min(maxAnalysisTrackBatchSize, Math.max(1, Number(event.target.value) || 1)))} />
              <button className="icon-button analysis-track-batch-increment-button" title="Увеличить ML track batch size" disabled={analysisDisabled || analysisTrackBatchSize >= maxAnalysisTrackBatchSize} onClick={() => adjustAnalysisTrackBatchSize(1)} type="button"><Plus size={15} /></button>
            </div>
          </div>
          <div className="worker-control">
            <span>Inference batch</span>
            <div className="stepper">
              <button className="icon-button analysis-inference-batch-decrement-button" title="Уменьшить ML inference batch size" disabled={analysisDisabled || analysisInferenceBatchSize <= 1} onClick={() => adjustAnalysisInferenceBatchSize(-1)} type="button"><Minus size={15} /></button>
              <input type="number" min={1} max={maxAnalysisInferenceBatchSize} value={analysisInferenceBatchSize} onChange={(event) => onAnalysisInferenceBatchSizeChange(Math.min(maxAnalysisInferenceBatchSize, Math.max(1, Number(event.target.value) || 1)))} />
              <button className="icon-button analysis-inference-batch-increment-button" title="Увеличить ML inference batch size" disabled={analysisDisabled || analysisInferenceBatchSize >= maxAnalysisInferenceBatchSize} onClick={() => adjustAnalysisInferenceBatchSize(1)} type="button"><Plus size={15} /></button>
            </div>
          </div>
        </div>
      </div>

      <div className="worker-control analysis-limit" title={helpText.analyzeLimit}>
        <span>Analyze limit</span>
        <div className="stepper">
          <button className="icon-button analysis-limit-decrement-button" title="Уменьшить Analyze limit" aria-label="Уменьшить Analyze limit" disabled={busy || stageRunning || analysisLimit <= 0} onClick={() => onAnalysisLimitChange(Math.max(0, analysisLimit - 1))} type="button"><Minus size={15} /></button>
          <input type="number" min={0} max={100000} value={analysisLimit} aria-label="Analyze limit 0 = все треки; ограничивает Scan и применяется отдельно к каждой стадии анализа" onChange={(event) => onAnalysisLimitChange(Math.min(100000, Math.max(0, Number(event.target.value) || 0)))} />
          <button className="icon-button analysis-limit-increment-button" title="Увеличить Analyze limit" aria-label="Увеличить Analyze limit" disabled={busy || stageRunning || analysisLimit >= 100000} onClick={() => onAnalysisLimitChange(Math.min(100000, analysisLimit + 1))} type="button"><Plus size={15} /></button>
        </div>
        <small>0 = все треки; ограничивает Scan и каждую стадию анализа</small>
      </div>
      <button
        className="analyze-selected-button analysis-pipeline-button"
        title="Запустить отмеченные модели в порядке SONARA → ML"
        disabled={analysisDisabled || !selectedAnalysisModels.length}
        onClick={onAnalyzeSelected}
        type="button"
      >
        <Play size={15} />
        Analyze
      </button>
    </aside>
  );
}
