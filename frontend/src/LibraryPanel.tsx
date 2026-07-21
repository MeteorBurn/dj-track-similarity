import { Cpu, Database, FolderOpen, Minus, Play, Plus, RefreshCcw, Save, Trash2 } from "lucide-react";
import { AnalysisJobStatus, AnalysisModel, AnalysisPipelineStatus, PromotedClassifier, SonaraOutput } from "./api";
import { mlAnalysisModelOrder, type AnalysisSelection } from "./analysisSelection";

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
  classifiersAnalyze: string;
  writeMaestGenres: string;
  analyzeLimit: string;
  analysisDevice: string;
  analysisTrackBatchSize: string;
  analysisInferenceBatchSize: string;
};

const modelDescriptions: Record<AnalysisModel, string> = {
  sonara: "SONARA/Symphonia · native batch",
  maest: "Жанровые признаки и embedding через общий FFmpeg decode.",
  mert: "Embedding для похожего звучания через общий FFmpeg decode.",
  muq: "Дополнительный аудио-embedding через общий FFmpeg decode.",
  clap: "Текстово-аудио embedding через общий FFmpeg decode."
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
  sonaraBatchSize,
  onSonaraBatchSizeChange,
  classifiers,
  analysisJob,
  pipelineJob,
  helpText,
  onChooseFolder,
  onScan,
  onRefreshTags,
  onWriteMaestGenres,
  onClearDatabase,
  analysisCounts,
  selectedAnalysisModels,
  onToggleAnalysisModel,
  sonaraOutputs,
  onToggleSonaraOutput,
  onAnalyzeSonara,
  onAnalyzeMl,
  onAnalyzeClassifiers,
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
  sonaraBatchSize: number;
  onSonaraBatchSizeChange: (value: number) => void;
  classifiers: PromotedClassifier[];
  analysisJob: AnalysisJobStatus | null;
  pipelineJob: AnalysisPipelineStatus | null;
  helpText: LibraryHelpText;
  onChooseFolder: () => void;
  onScan: () => void;
  onRefreshTags: () => void;
  onWriteMaestGenres: () => void;
  onClearDatabase: () => void;
  analysisCounts: Record<AnalysisSelection, number>;
  selectedAnalysisModels: AnalysisSelection[];
  onToggleAnalysisModel: (model: AnalysisSelection) => void;
  sonaraOutputs: SonaraOutput[];
  onToggleSonaraOutput: (output: SonaraOutput) => void;
  onAnalyzeSonara: () => void;
  onAnalyzeMl: () => void;
  onAnalyzeClassifiers: () => void;
  onAnalyzeSelected: () => void;
  onResetAnalysis: (adapter: AnalysisModel) => void;
  onResetClassifiers: () => void;
}) {
  const analysisDisabled = busy || stageRunning || !hasTracks;
  const readyClassifiers = classifiers.reduce((sum, item) => sum + (item.ready || 0), 0);
  const notReadyClassifiers = classifiers.reduce((sum, item) => sum + (item.not_ready || 0), 0);
  const blockerCount = classifiers.filter((item) => item.readiness_blockers?.length).length;

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
        <button className="icon-button folder-picker database-picker-button" title="Выбрать SQLite базу" aria-label="Выбрать SQLite базу" disabled={busy || stageRunning} onClick={onChooseDatabase}><Database size={17} /></button>
      </div>
      <div className="path-row library-path-row">
        <input value={musicRoot} onChange={(event) => onMusicRootChange(event.target.value)} placeholder="D:/Music" title={helpText.musicRoot} />
        <button className="icon-button folder-picker library-folder-picker-button" title="Выбрать папку" aria-label="Выбрать папку" disabled={busy || stageRunning} onClick={onChooseFolder}><FolderOpen size={17} /></button>
      </div>
      <div className="worker-control" title={helpText.scanWorkers}>
        <span>Scan workers</span>
        <div className="stepper">
          <button className="icon-button scan-workers-decrement-button" title="Уменьшить количество потоков сканирования" disabled={busy || scanWorkers <= 1} onClick={() => adjustScanWorkers(-1)} aria-label="Уменьшить количество потоков сканирования"><Minus size={15} /></button>
          <input type="number" min={1} max={maxScanWorkers} value={scanWorkers} onChange={(event) => onScanWorkersChange(Math.min(maxScanWorkers, Math.max(1, Number(event.target.value) || 1)))} />
          <button className="icon-button scan-workers-increment-button" title="Увеличить количество потоков сканирования" disabled={busy || scanWorkers >= maxScanWorkers} onClick={() => adjustScanWorkers(1)} aria-label="Увеличить количество потоков сканирования"><Plus size={15} /></button>
        </div>
      </div>
      <div className="scan-action-row">
        <button className="scan-start-button" title="Загрузить треки в SQLite" disabled={busy || stageRunning || !canStartScan} onClick={onScan}><Play size={15} />Загрузить треки в базу</button>
        <button className="icon-button refresh-tags-button" disabled={busy || stageRunning || !hasTracks} title={helpText.refreshTags} onClick={onRefreshTags}><RefreshCcw size={17} /></button>
        <button className="icon-button genre-save-button" disabled={busy || stageRunning || !maestGenreTrackCount} title={helpText.writeMaestGenres} onClick={onWriteMaestGenres}><Save size={17} /></button>
        <button className="icon-button stop-button database-clear-button" disabled={busy || stageRunning || !hasTracks} title={helpText.clearDatabase} onClick={onClearDatabase}><Trash2 size={17} /></button>
      </div>

      <div className="analysis-models-heading"><span>SONARA</span><small>Нативный decode; FFmpeg и Python audio wrapper не используются</small></div>
      <div className="analysis-actions">{modelRow("sonara")}</div>
      <fieldset className="sonara-output-options" disabled={busy || stageRunning}>
        <legend>SONARA data</legend>
        {(["core", "timeline", "representations"] as SonaraOutput[]).map((output) => (
          <label key={output}>
            <input type="checkbox" checked={sonaraOutputs.includes(output)} onChange={() => onToggleSonaraOutput(output)} />
            <span><b>{output[0].toUpperCase() + output.slice(1)}</b><small>{output === "core" ? "По умолчанию" : "Явный opt-in"}</small></span>
          </label>
        ))}
      </fieldset>
      <div className="worker-control">
        <span>Native batch size</span>
        <div className="stepper">
          <button className="icon-button sonara-batch-decrement-button" title="Уменьшить native batch size" disabled={analysisDisabled || sonaraBatchSize <= 1} onClick={() => onSonaraBatchSizeChange(sonaraBatchSize - 1)}><Minus size={15} /></button>
          <input type="number" min={1} max={128} value={sonaraBatchSize} onChange={(event) => onSonaraBatchSizeChange(Math.min(128, Math.max(1, Number(event.target.value) || 1)))} />
          <button className="icon-button sonara-batch-increment-button" title="Увеличить native batch size" disabled={analysisDisabled || sonaraBatchSize >= 128} onClick={() => onSonaraBatchSizeChange(sonaraBatchSize + 1)}><Plus size={15} /></button>
        </div>
        <small>SONARA/Symphonia · native batch</small>
      </div>
      <button className="analyze-selected-button sonara-analyze-button" title="Запустить отдельный native SONARA job" disabled={analysisDisabled || !sonaraOutputs.length} onClick={onAnalyzeSonara}><Play size={15} />Run SONARA</button>

      <div className="analysis-models-heading"><span>ML MODELS</span><small>MAEST/MERT/MuQ/CLAP · общий FFmpeg decode</small></div>
      <div className="analysis-actions">{mlAnalysisModelOrder.map(modelRow)}</div>
      <div className="analysis-device" title={helpText.analysisDevice}>
        <span><Cpu size={15} /> Device</span>
        <div className="segmented">{(["auto", "cpu", "cuda"] as DeviceMode[]).map((device) => <button key={device} className={`analysis-device-button ${analysisDevice === device ? "active" : ""}`} title={`ML device: ${device}`} disabled={busy || stageRunning} onClick={() => onAnalysisDeviceChange(device)}>{device.toUpperCase()}</button>)}</div>
      </div>
      <div className="worker-control">
        <span>Track batch size</span>
        <div className="stepper">
          <button className="icon-button analysis-track-batch-decrement-button" title="Уменьшить ML track batch size" disabled={analysisDisabled || analysisTrackBatchSize <= 1} onClick={() => adjustAnalysisTrackBatchSize(-1)}><Minus size={15} /></button>
          <input type="number" min={1} max={maxAnalysisTrackBatchSize} value={analysisTrackBatchSize} onChange={(event) => onAnalysisTrackBatchSizeChange(Math.min(maxAnalysisTrackBatchSize, Math.max(1, Number(event.target.value) || 1)))} />
          <button className="icon-button analysis-track-batch-increment-button" title="Увеличить ML track batch size" disabled={analysisDisabled || analysisTrackBatchSize >= maxAnalysisTrackBatchSize} onClick={() => adjustAnalysisTrackBatchSize(1)}><Plus size={15} /></button>
        </div>
      </div>
      <div className="worker-control">
        <span>Inference batch size</span>
        <div className="stepper">
          <button className="icon-button analysis-inference-batch-decrement-button" title="Уменьшить ML inference batch size" disabled={analysisDisabled || analysisInferenceBatchSize <= 1} onClick={() => adjustAnalysisInferenceBatchSize(-1)}><Minus size={15} /></button>
          <input type="number" min={1} max={maxAnalysisInferenceBatchSize} value={analysisInferenceBatchSize} onChange={(event) => onAnalysisInferenceBatchSizeChange(Math.min(maxAnalysisInferenceBatchSize, Math.max(1, Number(event.target.value) || 1)))} />
          <button className="icon-button analysis-inference-batch-increment-button" title="Увеличить ML inference batch size" disabled={analysisDisabled || analysisInferenceBatchSize >= maxAnalysisInferenceBatchSize} onClick={() => adjustAnalysisInferenceBatchSize(1)}><Plus size={15} /></button>
        </div>
      </div>
      <button className="analyze-selected-button ml-analyze-button" title="Запустить отдельный ML job" disabled={analysisDisabled || !mlAnalysisModelOrder.some((model) => selectedAnalysisModels.includes(model))} onClick={onAnalyzeMl}><Play size={15} />Run ML</button>

      <div className="analysis-models-heading"><span>CLASSIFIERS</span><small>Отдельный job без чтения аудио</small></div>
      <div className="analysis-model-row">
        <span className="analysis-model-check"><input type="checkbox" aria-label="CLASSIFIERS selected" checked={selectedAnalysisModels.includes("classifiers")} disabled={busy || stageRunning} onChange={() => onToggleAnalysisModel("classifiers")} /></span>
        <span className="analysis-model-name"><span className="analysis-model-title">CLASSIFIERS</span><span className="analysis-model-description">ready {readyClassifiers} · not ready {notReadyClassifiers}{blockerCount ? ` · blockers ${blockerCount}` : ""}</span></span>
        <span className="analysis-model-count">{analysisCounts.classifiers || 0}</span>
        <button className="icon-button stop-button analysis-reset-button classifiers-reset-button" title="Сбросить CLASSIFIERS" disabled={analysisDisabled} onClick={onResetClassifiers}><Trash2 size={16} /></button>
      </div>
      {classifiers.flatMap((item) => item.readiness_blockers || []).slice(0, 3).map((blocker) => <small className="analysis-muted" key={blocker}>{blocker}</small>)}
      <button className="analyze-selected-button classifiers-analyze-button" title="Запустить отдельный CLASSIFIERS job" disabled={analysisDisabled || !classifiers.some((item) => item.is_scoring_compatible !== false)} onClick={onAnalyzeClassifiers}><Play size={15} />Run CLASSIFIERS</button>

      <label className="analysis-limit" title={helpText.analyzeLimit}>Analyze limit<input type="number" min={0} max={100000} value={analysisLimit} onChange={(event) => onAnalysisLimitChange(Number(event.target.value))} /><small>0 = вся библиотека; применяется отдельно к каждой стадии</small></label>
      {analysisJob ? <small className="analysis-muted">Job {analysisJob.state} · {analysisJob.processed}/{analysisJob.total} · {analysisJob.current_model || analysisJob.models?.join(", ")}</small> : null}
      {pipelineJob ? <small className="analysis-muted">Pipeline {pipelineJob.state} · {pipelineJob.order.map((stage) => `${stage}:${pipelineJob.stages[stage]?.state}`).join(" → ")}</small> : null}
      <button className="analyze-selected-button analysis-pipeline-button" title="Поставить выбранные стадии в очередь SONARA → ML → CLASSIFIERS" disabled={analysisDisabled || !selectedAnalysisModels.length} onClick={onAnalyzeSelected}><Play size={15} />Run selected pipeline</button>
    </aside>
  );
}
