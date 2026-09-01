import { CopyCheck, Cpu, Database, FolderOpen, Minus, Music4, Play, Plus, RefreshCcw, Save, Settings2, ShieldCheck, Trash2 } from "lucide-react";
import { AnalysisModel } from "./api";
import { mlAnalysisModelOrder, type AnalysisSelection } from "./analysisSelection";
import { NumberStepper } from "./NumberStepper";
import type { MLAnalysisSettings } from "./mlAnalysisSettings";

type DeviceMode = "auto" | "cpu" | "cuda";

type LibraryHelpText = {
  databasePath: string;
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

export function LibraryPanel({
  databasePath,
  onChooseDatabase,
  busy,
  stageRunning,
  hasTracks,
  maestGenreTrackCount,
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
  mlSettings,
  onMLSettingsChange,
  onChooseMLStagingFolder,
  helpText,
  onOpenScanDialog,
  onOpenSonaraSettingsDialog,
  onRefreshTags,
  onWriteMaestGenres,
  onClearDatabase,
  onValidateDatabase,
  onOpenAudioDedup,
  analysisCounts,
  selectedAnalysisModels,
  onToggleAnalysisModel,
  onAnalyzeSelected,
  onResetAnalysis,
}: {
  databasePath: string | null;
  onChooseDatabase: () => void;
  busy: boolean;
  stageRunning: boolean;
  hasTracks: boolean;
  maestGenreTrackCount: number;
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
  mlSettings: MLAnalysisSettings;
  onMLSettingsChange: (value: MLAnalysisSettings) => void;
  onChooseMLStagingFolder: () => void;
  helpText: LibraryHelpText;
  onOpenScanDialog: () => void;
  onOpenSonaraSettingsDialog: () => void;
  onRefreshTags: () => void;
  onWriteMaestGenres: () => void;
  onClearDatabase: () => void;
  onValidateDatabase: () => void;
  onOpenAudioDedup: () => void;
  analysisCounts: Record<AnalysisSelection, number>;
  selectedAnalysisModels: AnalysisSelection[];
  onToggleAnalysisModel: (model: AnalysisSelection) => void;
  onAnalyzeSelected: () => void;
  onResetAnalysis: (adapter: AnalysisModel) => void;
}) {
  const analysisDisabled = busy || stageRunning || !hasTracks;
  const settingsDisabled = busy || stageRunning;
  const updateMLStaged = (changes: Partial<MLAnalysisSettings["staged"]>) => {
    onMLSettingsChange({
      ...mlSettings,
      staged: { ...mlSettings.staged, ...changes },
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
          disabled={busy || stageRunning || (model !== "sonara" && analysisCounts.sonara < 1)}
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
      <div className="scan-action-row">
        <button className="scan-settings-button" title="Открыть параметры загрузки треков" disabled={busy || stageRunning || !databasePath} onClick={onOpenScanDialog} type="button"><Music4 size={15} />Загрузить треки в базу</button>
        <button className="icon-button refresh-tags-button" disabled={busy || stageRunning || !hasTracks} title="Обновить теги" aria-label="Обновить теги" onClick={onRefreshTags} type="button"><RefreshCcw size={17} /></button>
        <button className="icon-button genre-save-button" disabled={busy || stageRunning || !maestGenreTrackCount} title="Сохранить жанры" aria-label="Сохранить жанры" onClick={onWriteMaestGenres} type="button"><Save size={17} /></button>
        <button className="icon-button database-validation-button" disabled={busy || stageRunning || !hasTracks} title="Проверить базу" aria-label="Проверить базу" onClick={onValidateDatabase} type="button"><ShieldCheck size={17} /></button>
        <button className="icon-button audio-dedup-button" disabled={busy || stageRunning || !hasTracks} title="Найти и разобрать дубликаты" aria-label="Найти и разобрать дубликаты" onClick={onOpenAudioDedup} type="button"><CopyCheck size={17} /></button>
        <button className="icon-button stop-button database-clear-button" disabled={busy || stageRunning || !hasTracks} title="Очистить базу" aria-label="Очистить базу" onClick={onClearDatabase} type="button"><Trash2 size={17} /></button>
      </div>

      <div className="analysis-models-heading">
        <span>Анализ</span>
        <small>Один запуск обработает выбранные стадии и пропустит уже готовые результаты</small>
      </div>
      <div className="analysis-family-card sonara-analysis-block">
        <div className="analysis-actions">{modelRow("sonara")}</div>
        <button className="sonara-settings-button" title="Открыть параметры анализа SONARA" disabled={settingsDisabled} onClick={onOpenSonaraSettingsDialog} type="button"><Settings2 size={15} />Настройки анализа SONARA</button>
      </div>

      <div className="analysis-family-card models-analysis-block">
        <div className="analysis-family-title"><strong>ML-модели</strong><small>Выберите нужные способы анализа звучания</small></div>
        <div className="analysis-actions">{mlAnalysisModelOrder.map(modelRow)}</div>
        <div className="analysis-settings-grid ml-analysis-settings">
          <div className="analysis-device ml-analysis-mode">
            <span>Mode</span>
            <div className="segmented ml-mode-segmented">
              <button className={`ml-mode-button ${mlSettings.mode === "direct" ? "active" : ""}`} title="Читать исходные аудиофайлы напрямую" disabled={settingsDisabled} onClick={() => onMLSettingsChange({ ...mlSettings, mode: "direct" })} type="button">Direct</button>
              <button className={`ml-mode-button ${mlSettings.mode === "staged" ? "active" : ""}`} title="Копировать входные файлы во временную SSD-папку" disabled={settingsDisabled} onClick={() => onMLSettingsChange({ ...mlSettings, mode: "staged" })} type="button">Staged</button>
            </div>
          </div>
          {mlSettings.mode === "staged" && (
            <>
              <div className="path-row ml-staging-path-row">
                <input value={mlSettings.staged.folder} readOnly title="Папка для временных staging-копий ML" />
                <button className="icon-button folder-picker ml-staging-folder-picker-button" title="Choose Folder для ML staging-копий" aria-label="Choose Folder для ML staging-копий" disabled={settingsDisabled} onClick={onChooseMLStagingFolder} type="button"><FolderOpen size={17} /></button>
              </div>
              <div className="ml-staged-settings-grid">
                <NumberStepper label="Workers" value={mlSettings.staged.workers} minimum={1} maximum={16} disabled={settingsDisabled} classPrefix="ml-workers" onChange={(workers) => updateMLStaged({ workers })} />
                <NumberStepper label="StageSize" value={mlSettings.staged.stageSize} minimum={1} maximum={512} disabled={settingsDisabled} classPrefix="ml-stage-size" onChange={(stageSize) => updateMLStaged({ stageSize })} />
              </div>
            </>
          )}
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
          <input type="number" min={0} max={100000} value={analysisLimit} aria-label="Analyze limit 0 = все треки; применяется отдельно к каждой стадии анализа" onChange={(event) => onAnalysisLimitChange(Math.min(100000, Math.max(0, Number(event.target.value) || 0)))} />
          <button className="icon-button analysis-limit-increment-button" title="Увеличить Analyze limit" aria-label="Увеличить Analyze limit" disabled={busy || stageRunning || analysisLimit >= 100000} onClick={() => onAnalysisLimitChange(Math.min(100000, analysisLimit + 1))} type="button"><Plus size={15} /></button>
        </div>
        <small>0 = все треки; применяется отдельно к каждой стадии анализа</small>
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
