import { Cpu, Database, FolderOpen, Minus, Play, Plus, RefreshCcw, Save, Square, Trash2 } from "lucide-react";
import { AnalysisJobStatus, AnalysisModel, ScanStats } from "./api";
import { stageIndicatorLabel } from "./jobUi";

type DeviceMode = "auto" | "cpu" | "cuda";
const analysisModelOrder: AnalysisModel[] = ["sonara", "maest", "mert", "clap"];

type LibraryHelpText = {
  databasePath: string;
  musicRoot: string;
  scanWorkers: string;
  refreshTags: string;
  clearDatabase: string;
  sonaraAnalyze: string;
  maestAnalyze: string;
  mertAnalyze: string;
  clapAnalyze: string;
  writeMaestGenres: string;
  analyzeLimit: string;
  analysisDevice: string;
  analysisBatchSize: string;
};

const analysisModelHelpKey: Record<AnalysisModel, keyof LibraryHelpText> = {
  sonara: "sonaraAnalyze",
  maest: "maestAnalyze",
  mert: "mertAnalyze",
  clap: "clapAnalyze"
};

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
  analysisBatchSize,
  maxAnalysisBatchSize,
  adjustAnalysisBatchSize,
  onAnalysisBatchSizeChange,
  scanJob,
  analysisJob,
  helpText,
  onStopActiveStage,
  onChooseFolder,
  onScan,
  onRefreshTags,
  onWriteMaestGenres,
  onClearDatabase,
  selectedAnalysisModels,
  onToggleAnalysisModel,
  onAnalyzeSelected,
  onResetAnalysis
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
  analysisBatchSize: number;
  maxAnalysisBatchSize: number;
  adjustAnalysisBatchSize: (delta: number) => void;
  onAnalysisBatchSizeChange: (value: number) => void;
  scanJob: ScanStats | null;
  analysisJob: AnalysisJobStatus | null;
  helpText: LibraryHelpText;
  onStopActiveStage: () => void;
  onChooseFolder: () => void;
  onScan: () => void;
  onRefreshTags: () => void;
  onWriteMaestGenres: () => void;
  onClearDatabase: () => void;
  selectedAnalysisModels: AnalysisModel[];
  onToggleAnalysisModel: (model: AnalysisModel) => void;
  onAnalyzeSelected: () => void;
  onResetAnalysis: (adapter: AnalysisModel) => void;
}) {
  const analysisDisabled = busy || stageRunning || !hasTracks;
  return (
    <aside className="panel library-panel">
      <div className="panel-title">
        <FolderOpen size={18} />
        <h2>1. База и анализ</h2>
        <div className="panel-title-actions process-controls">
          <button className="icon-button stop-button stop-active-stage-button" title="Остановить текущий scan или анализ" aria-label="Остановить текущий scan или анализ" disabled={busy || !stageRunning} onClick={onStopActiveStage}>
            <Square size={15} />
          </button>
          <span className={`process-indicator ${stageRunning ? "running" : ""}`} title={stageIndicatorLabel(scanJob, analysisJob)} aria-label={stageIndicatorLabel(scanJob, analysisJob)}>
            <RefreshCcw size={17} />
          </span>
        </div>
      </div>
      <div className="path-row database-path-row">
        <input value={databasePath || ""} readOnly placeholder="Выберите SQLite базу" title={helpText.databasePath} />
        <button className="icon-button folder-picker database-picker-button" title="Выбрать SQLite базу" aria-label="Выбрать SQLite базу" disabled={busy || stageRunning} onClick={onChooseDatabase}>
          <Database size={17} />
        </button>
      </div>
      <div className="path-row library-path-row">
        <input value={musicRoot} onChange={(event) => onMusicRootChange(event.target.value)} placeholder="D:/Music" title={helpText.musicRoot} />
        <button className="icon-button folder-picker library-folder-picker-button" title="Выбрать папку" aria-label="Выбрать папку" disabled={busy || stageRunning} onClick={onChooseFolder}>
          <FolderOpen size={17} />
        </button>
      </div>
      <div className="worker-control" title={helpText.scanWorkers}>
        <span>Scan workers</span>
        <div className="stepper">
          <button className="icon-button scan-workers-decrement-button" title="Уменьшить количество потоков сканирования" disabled={busy || scanWorkers <= 1} onClick={() => adjustScanWorkers(-1)} aria-label="Уменьшить количество потоков сканирования"><Minus size={15} /></button>
          <input type="number" min={1} max={maxScanWorkers} value={scanWorkers} title={helpText.scanWorkers} onChange={(event) => onScanWorkersChange(Math.min(maxScanWorkers, Math.max(1, Number(event.target.value) || 1)))} />
          <button className="icon-button scan-workers-increment-button" title="Увеличить количество потоков сканирования" disabled={busy || scanWorkers >= maxScanWorkers} onClick={() => adjustScanWorkers(1)} aria-label="Увеличить количество потоков сканирования"><Plus size={15} /></button>
        </div>
        <small>Для чтения метаданных: 1-{maxScanWorkers}</small>
      </div>
      <div className="scan-action-row">
        <button className="primary scan-start-button" title="Первично прочитать треки через Mutagen и добавить или обновить записи в SQLite" disabled={busy || stageRunning || !canStartScan} onClick={onScan}>
          <Play size={15} />
          Загрузить треки в базу
        </button>
        <button className="icon-button refresh-tags-button" disabled={busy || stageRunning || !hasTracks} title={helpText.refreshTags} aria-label="Обновить теги" onClick={onRefreshTags}>
          <RefreshCcw size={15} />
        </button>
        <button
          className="icon-button genre-save-button"
          title={`${helpText.writeMaestGenres} Доступно: ${maestGenreTrackCount}.`}
          aria-label="Сохранить MAEST жанры в теги всех доступных треков"
          disabled={busy || stageRunning || !maestGenreTrackCount}
          onClick={onWriteMaestGenres}
          type="button"
        >
          <Save size={15} />
        </button>
        <button className="icon-button stop-button database-clear-button" disabled={busy || stageRunning || !hasTracks} title={helpText.clearDatabase} aria-label="Удалить все данные из базы" onClick={onClearDatabase}>
          <Trash2 size={15} />
        </button>
      </div>
      <div className="analysis-section-title">
        <span>Анализ моделей</span>
        <small>Один запуск обработает выбранные модели и пропустит уже готовые результаты</small>
      </div>
      <div className="analysis-actions">
        {analysisModelOrder.map((model) => {
          const label = model.toUpperCase();
          return (
            <div className="analysis-model-row" key={model}>
              <span className="analysis-model-name" title={helpText[analysisModelHelpKey[model]]}>{label}</span>
              <label className="analysis-model-check" title={helpText[analysisModelHelpKey[model]]} aria-label={`${label} selected`}>
                <input
                  className="analysis-model-checkbox"
                  type="checkbox"
                  checked={selectedAnalysisModels.includes(model)}
                  disabled={busy || stageRunning}
                  onChange={() => onToggleAnalysisModel(model)}
                />
              </label>
              <button
                className={`analysis-reset-button ${model}-reset-button`}
                disabled={analysisDisabled}
                title={`Reset ${label}`}
                aria-label={`Reset ${label}`}
                onClick={() => onResetAnalysis(model)}
                type="button"
              >
                Reset
                <Trash2 size={14} />
              </button>
            </div>
          );
        })}
      </div>
      <label className="analysis-limit" title={helpText.analyzeLimit}>
        Analyze limit
        <input type="number" min={0} max={100000} value={analysisLimit} title={helpText.analyzeLimit} onChange={(event) => onAnalysisLimitChange(Number(event.target.value))} />
        <small>0 = вся библиотека</small>
      </label>
      <div className="analysis-device" title={helpText.analysisDevice}>
        <span><Cpu size={15} /> Device</span>
        <div className="segmented">
          {(["auto", "cpu", "cuda"] as DeviceMode[]).map((device) => (
            <button
              key={device}
              className={`analysis-device-button ${analysisDevice === device ? "active" : ""}`}
              disabled={busy || stageRunning}
              title={helpText.analysisDevice}
              onClick={() => onAnalysisDeviceChange(device)}
            >
              {device.toUpperCase()}
            </button>
          ))}
        </div>
        <small>Auto выбирает CUDA, если PyTorch видит GPU; иначе CPU.</small>
      </div>
      <div className="worker-control" title={helpText.analysisBatchSize}>
        <span>Embedding batch size</span>
        <div className="stepper">
          <button className="icon-button analysis-batch-decrement-button" title="Уменьшить Embedding batch size" disabled={busy || analysisBatchSize <= 1} onClick={() => adjustAnalysisBatchSize(-1)} aria-label="Уменьшить batch size"><Minus size={15} /></button>
          <input type="number" min={1} max={maxAnalysisBatchSize} value={analysisBatchSize} title={helpText.analysisBatchSize} onChange={(event) => onAnalysisBatchSizeChange(Math.min(maxAnalysisBatchSize, Math.max(1, Number(event.target.value) || 1)))} />
          <button className="icon-button analysis-batch-increment-button" title="Увеличить Embedding batch size" disabled={busy || analysisBatchSize >= maxAnalysisBatchSize} onClick={() => adjustAnalysisBatchSize(1)} aria-label="Увеличить batch size"><Plus size={15} /></button>
        </div>
        <small>SONARA: параллельные треки. MAEST/MERT/CLAP: inference batch; CPU 1-4, CUDA начни с 4-8.</small>
      </div>
      <button
        className="primary analyze-selected-button"
        disabled={analysisDisabled || selectedAnalysisModels.length === 0}
        title="Запустить анализ выбранных моделей для треков с отсутствующими результатами"
        onClick={onAnalyzeSelected}
        type="button"
      >
        <Play size={15} />
        Analyze
      </button>
    </aside>
  );
}
