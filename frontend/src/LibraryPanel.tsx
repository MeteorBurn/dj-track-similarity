import { Cpu, Database, FolderOpen, Minus, Play, Plus, RefreshCcw, Save, Trash2 } from "lucide-react";
import { AnalysisJobStatus, AnalysisModel, AnalysisPipelineStatus, PromotedClassifier, SonaraOutput } from "./api";
import { audioAnalysisModelOrder, mlAnalysisModelOrder, type AnalysisSelection } from "./analysisSelection";

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
  sonara: "Считает темп, тональность, ритм, динамику, тембр и структуру трека.",
  maest: "Помогает понять жанровый характер трека.",
  mert: "Ищет похожее звучание от выбранного seed-трека.",
  muq: "Сохраняет дополнительный слой аудио-признаков.",
  clap: "Связывает текстовое описание с аудио-звучанием."
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
  onToggleAllAnalysisModels,
  sonaraOutputs,
  onToggleSonaraOutput,
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
  onToggleAllAnalysisModels: () => void;
  sonaraOutputs: SonaraOutput[];
  onToggleSonaraOutput: (output: SonaraOutput) => void;
  onAnalyzeSelected: () => void;
  onResetAnalysis: (adapter: AnalysisModel) => void;
  onResetClassifiers: () => void;
}) {
  const analysisDisabled = busy || stageRunning || !hasTracks;
  const readyClassifiers = classifiers.reduce((sum, item) => sum + (item.ready || 0), 0);
  const notReadyClassifiers = classifiers.reduce((sum, item) => sum + (item.not_ready || 0), 0);
  const blockerCount = classifiers.filter((item) => item.readiness_blockers?.length).length;
  const sonaraSelected = selectedAnalysisModels.includes("sonara");
  const classifiersSelected = selectedAnalysisModels.includes("classifiers");
  const fullAnalysisSelected = selectedAnalysisModels.length === audioAnalysisModelOrder.length + 1;

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

      <div className="analysis-models-heading analysis-models-heading-with-full">
        <span>Анализ</span>
        <label className="analysis-full-check" title="Выбрать все стадии анализа">
          <input type="checkbox" checked={fullAnalysisSelected} disabled={busy || stageRunning} onChange={onToggleAllAnalysisModels} />
          FULL
        </label>
        <small>Один запуск обработает выбранные стадии и пропустит уже готовые результаты</small>
      </div>
      <div className="analysis-family-card sonara-analysis-block">
        <div className="analysis-actions">{modelRow("sonara")}</div>
        <fieldset className="sonara-output-options" disabled={busy || stageRunning || !sonaraSelected}>
          <legend>SONARA data</legend>
          <label title="Лёгкие скалярные признаки и короткие агрегированные векторы в основной базе.">
            <input type="checkbox" checked={sonaraOutputs.includes("core")} onChange={() => onToggleSonaraOutput("core")} />
            <span><b>Core</b><small>Основные признаки</small></span>
          </label>
          <label title="Полные временные ряды, события и сегменты в соседней Timeline-базе.">
            <input type="checkbox" checked={sonaraOutputs.includes("timeline")} onChange={() => onToggleSonaraOutput("timeline")} />
            <span><b>Timeline</b><small>События и кривые</small></span>
          </label>
          <label title="SONARA embedding и fingerprint в соседней Representations-базе.">
            <input type="checkbox" checked={sonaraOutputs.includes("representations")} onChange={() => onToggleSonaraOutput("representations")} />
            <span><b>Representations</b><small>Embedding и fingerprint</small></span>
          </label>
        </fieldset>
        <div className="analysis-settings-grid sonara-analysis-settings">
          <div className="worker-control">
            <span>SONARA batch</span>
            <div className="stepper">
              <button className="icon-button sonara-batch-decrement-button" title="Уменьшить native batch size" disabled={analysisDisabled || sonaraBatchSize <= 1} onClick={() => onSonaraBatchSizeChange(sonaraBatchSize - 1)}><Minus size={15} /></button>
              <input type="number" min={1} max={16} value={sonaraBatchSize} onChange={(event) => onSonaraBatchSizeChange(Math.min(16, Math.max(1, Number(event.target.value) || 1)))} />
              <button className="icon-button sonara-batch-increment-button" title="Увеличить native batch size" disabled={analysisDisabled || sonaraBatchSize >= 16} onClick={() => onSonaraBatchSizeChange(sonaraBatchSize + 1)}><Plus size={15} /></button>
            </div>
          </div>
        </div>
      </div>

      <div className="analysis-family-card models-analysis-block">
        <div className="analysis-family-title"><strong>ML-модели</strong><small>Выберите нужные способы анализа звучания</small></div>
        <div className="analysis-actions">{mlAnalysisModelOrder.map(modelRow)}</div>
        <div className="analysis-settings-grid ml-analysis-settings">
          <div className="analysis-device" title={helpText.analysisDevice}>
            <span><Cpu size={15} /> Device</span>
            <div className="segmented">{(["auto", "cpu", "cuda"] as DeviceMode[]).map((device) => <button key={device} className={`analysis-device-button ${analysisDevice === device ? "active" : ""}`} title={`ML device: ${device}`} disabled={busy || stageRunning} onClick={() => onAnalysisDeviceChange(device)}>{device.toUpperCase()}</button>)}</div>
          </div>
          <div className="worker-control">
            <span>Track batch</span>
            <div className="stepper">
              <button className="icon-button analysis-track-batch-decrement-button" title="Уменьшить ML track batch size" disabled={analysisDisabled || analysisTrackBatchSize <= 1} onClick={() => adjustAnalysisTrackBatchSize(-1)}><Minus size={15} /></button>
              <input type="number" min={1} max={maxAnalysisTrackBatchSize} value={analysisTrackBatchSize} onChange={(event) => onAnalysisTrackBatchSizeChange(Math.min(maxAnalysisTrackBatchSize, Math.max(1, Number(event.target.value) || 1)))} />
              <button className="icon-button analysis-track-batch-increment-button" title="Увеличить ML track batch size" disabled={analysisDisabled || analysisTrackBatchSize >= maxAnalysisTrackBatchSize} onClick={() => adjustAnalysisTrackBatchSize(1)}><Plus size={15} /></button>
            </div>
          </div>
          <div className="worker-control">
            <span>Inference batch</span>
            <div className="stepper">
              <button className="icon-button analysis-inference-batch-decrement-button" title="Уменьшить ML inference batch size" disabled={analysisDisabled || analysisInferenceBatchSize <= 1} onClick={() => adjustAnalysisInferenceBatchSize(-1)}><Minus size={15} /></button>
              <input type="number" min={1} max={maxAnalysisInferenceBatchSize} value={analysisInferenceBatchSize} onChange={(event) => onAnalysisInferenceBatchSizeChange(Math.min(maxAnalysisInferenceBatchSize, Math.max(1, Number(event.target.value) || 1)))} />
              <button className="icon-button analysis-inference-batch-increment-button" title="Увеличить ML inference batch size" disabled={analysisDisabled || analysisInferenceBatchSize >= maxAnalysisInferenceBatchSize} onClick={() => adjustAnalysisInferenceBatchSize(1)}><Plus size={15} /></button>
            </div>
          </div>
        </div>
      </div>

      <div className="analysis-family-card classifiers-analysis-card">
        <div className="analysis-actions classifiers-analysis-block">
          <div className="analysis-model-row">
            <span className="analysis-model-check"><input className="analysis-model-checkbox" type="checkbox" aria-label="CLASSIFIERS selected" checked={classifiersSelected} disabled={busy || stageRunning} onChange={() => onToggleAnalysisModel("classifiers")} /></span>
            <span className="analysis-model-name"><span className="analysis-model-title">CLASSIFIERS</span><span className="analysis-model-description">Отдельный анализ по локальным профилям · ready {readyClassifiers} · not ready {notReadyClassifiers}{blockerCount ? ` · blockers ${blockerCount}` : ""}</span></span>
            <span className="analysis-model-count">{analysisCounts.classifiers || 0}</span>
            <button className="icon-button stop-button analysis-reset-button classifiers-reset-button" title="Сбросить CLASSIFIERS" disabled={analysisDisabled} onClick={onResetClassifiers}><Trash2 size={16} /></button>
          </div>
        </div>
        {classifiers.flatMap((item) => item.readiness_blockers || []).slice(0, 3).map((blocker) => <small className="analysis-muted" key={blocker}>{blocker}</small>)}
      </div>

      <div className="worker-control analysis-limit" title={helpText.analyzeLimit}>
        <span>Analyze limit</span>
        <div className="stepper">
          <button className="icon-button analysis-limit-decrement-button" title="Уменьшить Analyze limit" aria-label="Уменьшить Analyze limit" disabled={busy || stageRunning || analysisLimit <= 0} onClick={() => onAnalysisLimitChange(Math.max(0, analysisLimit - 1))}><Minus size={15} /></button>
          <input type="number" min={0} max={100000} value={analysisLimit} aria-label="Analyze limit 0 = вся библиотека; применяется отдельно к каждой стадии" onChange={(event) => onAnalysisLimitChange(Math.min(100000, Math.max(0, Number(event.target.value) || 0)))} />
          <button className="icon-button analysis-limit-increment-button" title="Увеличить Analyze limit" aria-label="Увеличить Analyze limit" disabled={busy || stageRunning || analysisLimit >= 100000} onClick={() => onAnalysisLimitChange(Math.min(100000, analysisLimit + 1))}><Plus size={15} /></button>
        </div>
        <small>0 = вся библиотека; применяется отдельно к каждой стадии</small>
      </div>
      {analysisJob ? <small className="analysis-muted">Job {analysisJob.state} · {analysisJob.processed}/{analysisJob.total} · {analysisJob.current_model || analysisJob.models?.join(", ")}</small> : null}
      {pipelineJob ? <small className="analysis-muted">Pipeline {pipelineJob.state} · {pipelineJob.order.map((stage) => `${stage}:${pipelineJob.stages[stage]?.state}`).join(" → ")}</small> : null}
      <button className="analyze-selected-button analysis-pipeline-button" title="Запустить отмеченные модели в порядке SONARA → ML → CLASSIFIERS" disabled={analysisDisabled || !selectedAnalysisModels.length || (sonaraSelected && !sonaraOutputs.length)} onClick={onAnalyzeSelected}><Play size={15} />Analyze</button>
    </aside>
  );
}
