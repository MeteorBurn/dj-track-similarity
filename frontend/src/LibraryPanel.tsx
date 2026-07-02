import { Cpu, Database, FolderOpen, Minus, Play, Plus, RefreshCcw, Save, Trash2 } from "lucide-react";
import { AnalysisModel } from "./api";
import { analysisSelectionOrder, type AnalysisSelection } from "./analysisSelection";

type DeviceMode = "auto" | "cpu" | "cuda";
const analysisModelOrder = analysisSelectionOrder;

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
  classifiersAnalyze: string;
  writeMaestGenres: string;
  analyzeLimit: string;
  analysisDevice: string;
  analysisTrackBatchSize: string;
  analysisInferenceBatchSize: string;
};

const analysisModelHelpKey: Record<AnalysisSelection, keyof LibraryHelpText> = {
  sonara: "sonaraAnalyze",
  maest: "maestAnalyze",
  mert: "mertAnalyze",
  muq: "muqAnalyze",
  clap: "clapAnalyze",
  classifiers: "classifiersAnalyze"
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
  analysisTrackBatchSize,
  maxAnalysisTrackBatchSize,
  adjustAnalysisTrackBatchSize,
  onAnalysisTrackBatchSizeChange,
  analysisInferenceBatchSize,
  maxAnalysisInferenceBatchSize,
  adjustAnalysisInferenceBatchSize,
  onAnalysisInferenceBatchSizeChange,
  helpText,
  onChooseFolder,
  onScan,
  onRefreshTags,
  onWriteMaestGenres,
  onClearDatabase,
  analysisCounts,
  selectedAnalysisModels,
  onToggleAnalysisModel,
  onAnalyzeSelected,
  onResetAnalysis,
  onResetClassifiers
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
  helpText: LibraryHelpText;
  onChooseFolder: () => void;
  onScan: () => void;
  onRefreshTags: () => void;
  onWriteMaestGenres: () => void;
  onClearDatabase: () => void;
  analysisCounts: Record<AnalysisSelection, number>;
  selectedAnalysisModels: AnalysisSelection[];
  onToggleAnalysisModel: (model: AnalysisSelection) => void;
  onAnalyzeSelected: () => void;
  onResetAnalysis: (adapter: AnalysisModel) => void;
  onResetClassifiers: () => void;
}) {
  const analysisDisabled = busy || stageRunning || !hasTracks;
  return (
    <aside className="panel library-panel">
      <div className="panel-title">
        <FolderOpen size={18} />
        <h2>1. База и анализ</h2>
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
        <button className="scan-start-button" title="Первично прочитать треки через Mutagen и добавить или обновить записи в SQLite" disabled={busy || stageRunning || !canStartScan} onClick={onScan}>
          <Play size={15} />
          Загрузить треки в базу
        </button>
        <button className="icon-button refresh-tags-button" disabled={busy || stageRunning || !hasTracks} title={helpText.refreshTags} aria-label="Обновить теги" onClick={onRefreshTags}>
          <RefreshCcw size={17} />
        </button>
        <button
          className="icon-button genre-save-button"
          title={`${helpText.writeMaestGenres} Доступно: ${maestGenreTrackCount}.`}
          aria-label="Сохранить MAEST жанры в теги всех доступных треков"
          disabled={busy || stageRunning || !maestGenreTrackCount}
          onClick={onWriteMaestGenres}
          type="button"
        >
          <Save size={17} />
        </button>
        <button className="icon-button stop-button database-clear-button" disabled={busy || stageRunning || !hasTracks} title={helpText.clearDatabase} aria-label="Удалить все данные из базы" onClick={onClearDatabase}>
          <Trash2 size={17} />
        </button>
      </div>
      <div className="analysis-models-heading">
        <span>Анализ моделей</span>
        <small>Один запуск обработает выбранные модели и пропустит уже готовые результаты</small>
      </div>
      <div className="analysis-actions">
        {analysisModelOrder.map((model) => {
          const isClassifiers = model === "classifiers";
          const label = isClassifiers ? "CLASSIFIERS" : model.toUpperCase();
          const title = helpText[analysisModelHelpKey[model]];
          const count = analysisCounts[model] || 0;
          return (
            <div className="analysis-model-row" key={model}>
              <span className="analysis-model-name" title={title}>{label}</span>
              <span className="analysis-model-count" title={`${label}: ${count} треков`}>{count}</span>
              <label className="analysis-model-check" title={title} aria-label={`${label} selected`}>
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
                onClick={() => {
                  if (model === "classifiers") {
                    onResetClassifiers();
                  } else {
                    onResetAnalysis(model);
                  }
                }}
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
      <div className="worker-control" title={helpText.analysisTrackBatchSize}>
        <span>Track batch size</span>
        <div className="stepper">
          <button className="icon-button analysis-track-batch-decrement-button" title="Уменьшить Track batch size" disabled={busy || analysisTrackBatchSize <= 1} onClick={() => adjustAnalysisTrackBatchSize(-1)} aria-label="Уменьшить track batch size"><Minus size={15} /></button>
          <input type="number" min={1} max={maxAnalysisTrackBatchSize} value={analysisTrackBatchSize} title={helpText.analysisTrackBatchSize} onChange={(event) => onAnalysisTrackBatchSizeChange(Math.min(maxAnalysisTrackBatchSize, Math.max(1, Number(event.target.value) || 1)))} />
          <button className="icon-button analysis-track-batch-increment-button" title="Увеличить Track batch size" disabled={busy || analysisTrackBatchSize >= maxAnalysisTrackBatchSize} onClick={() => adjustAnalysisTrackBatchSize(1)} aria-label="Увеличить track batch size"><Plus size={15} /></button>
        </div>
        <small>Сколько decoded треков держать в памяти одновременно.</small>
      </div>
      <div className="worker-control" title={helpText.analysisInferenceBatchSize}>
        <span>Inference batch size</span>
        <div className="stepper">
          <button className="icon-button analysis-inference-batch-decrement-button" title="Уменьшить Inference batch size" disabled={busy || analysisInferenceBatchSize <= 1} onClick={() => adjustAnalysisInferenceBatchSize(-1)} aria-label="Уменьшить inference batch size"><Minus size={15} /></button>
          <input type="number" min={1} max={maxAnalysisInferenceBatchSize} value={analysisInferenceBatchSize} title={helpText.analysisInferenceBatchSize} onChange={(event) => onAnalysisInferenceBatchSizeChange(Math.min(maxAnalysisInferenceBatchSize, Math.max(1, Number(event.target.value) || 1)))} />
          <button className="icon-button analysis-inference-batch-increment-button" title="Увеличить Inference batch size" disabled={busy || analysisInferenceBatchSize >= maxAnalysisInferenceBatchSize} onClick={() => adjustAnalysisInferenceBatchSize(1)} aria-label="Увеличить inference batch size"><Plus size={15} /></button>
        </div>
        <small>MAEST/MERT/CLAP forward pass; RTX 3090 default 24.</small>
      </div>
      <button
        className="analyze-selected-button"
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
