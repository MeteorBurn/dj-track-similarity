import { Cpu, FolderOpen, Gauge, Minus, Play, Plus, RefreshCcw, Search, Square, Tags, Trash2, Wand2 } from "lucide-react";
import { AnalysisJobStatus, GenreTagJobStatus, ScanStats } from "./api";
import { ActivityEvent, AnalysisButton, stageIndicatorLabel, UnifiedLog } from "./jobUi";

type DeviceMode = "auto" | "cpu" | "cuda";
type AnalysisAdapter = "mert" | "clap" | "fake";
type ResetAdapter = "sonara" | "maest" | "mert" | "clap" | "fake";

type LibraryHelpText = {
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

export function LibraryPanel({
  musicRoot,
  onMusicRootChange,
  busy,
  stageRunning,
  canStartScan,
  hasTracks,
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
  processLogKind,
  scanJob,
  analysisJob,
  genreTagJob,
  activityLog,
  helpText,
  onStopActiveStage,
  onChooseFolder,
  onScan,
  onRefreshTags,
  onClearDatabase,
  onSonaraAnalyze,
  onGenreAnalyze,
  onAnalyze,
  onResetAnalysis
}: {
  musicRoot: string;
  onMusicRootChange: (value: string) => void;
  busy: boolean;
  stageRunning: boolean;
  canStartScan: boolean;
  hasTracks: boolean;
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
  processLogKind: "scan" | "analysis" | "genre_tags";
  scanJob: ScanStats | null;
  analysisJob: AnalysisJobStatus | null;
  genreTagJob: GenreTagJobStatus | null;
  activityLog: ActivityEvent[];
  helpText: LibraryHelpText;
  onStopActiveStage: () => void;
  onChooseFolder: () => void;
  onScan: () => void;
  onRefreshTags: () => void;
  onClearDatabase: () => void;
  onSonaraAnalyze: () => void;
  onGenreAnalyze: () => void;
  onAnalyze: (adapter: AnalysisAdapter) => void;
  onResetAnalysis: (adapter: ResetAdapter) => void;
}) {
  return (
    <aside className="panel library-panel">
      <div className="panel-title">
        <FolderOpen size={18} />
        <h2>1. База и анализ</h2>
        <div className="panel-title-actions process-controls">
          <button className="icon-button stop-button" title="Остановить текущий scan или анализ" aria-label="Остановить текущий scan или анализ" disabled={busy || !stageRunning} onClick={onStopActiveStage}>
            <Square size={15} />
          </button>
          <span className={`process-indicator ${stageRunning ? "running" : ""}`} title={stageIndicatorLabel(scanJob, analysisJob)} aria-label={stageIndicatorLabel(scanJob, analysisJob)}>
            <RefreshCcw size={17} />
          </span>
        </div>
      </div>
      <div className="path-row library-path-row">
        <input value={musicRoot} onChange={(event) => onMusicRootChange(event.target.value)} placeholder="D:/Music" title={helpText.musicRoot} />
        <button className="icon-button folder-picker" title="Выбрать папку" aria-label="Выбрать папку" disabled={busy || stageRunning} onClick={onChooseFolder}>
          <FolderOpen size={17} />
        </button>
      </div>
      <div className="worker-control" title={helpText.scanWorkers}>
        <span>Scan workers</span>
        <div className="stepper">
          <button className="icon-button" disabled={busy || scanWorkers <= 1} onClick={() => adjustScanWorkers(-1)} aria-label="Уменьшить количество потоков сканирования"><Minus size={15} /></button>
          <input type="number" min={1} max={maxScanWorkers} value={scanWorkers} title={helpText.scanWorkers} onChange={(event) => onScanWorkersChange(Math.min(maxScanWorkers, Math.max(1, Number(event.target.value) || 1)))} />
          <button className="icon-button" disabled={busy || scanWorkers >= maxScanWorkers} onClick={() => adjustScanWorkers(1)} aria-label="Увеличить количество потоков сканирования"><Plus size={15} /></button>
        </div>
        <small>Для чтения метаданных: 1-{maxScanWorkers}</small>
      </div>
      <div className="scan-action-row">
        <button className="primary scan-start-button" title="Первично прочитать треки через Mutagen и добавить или обновить записи в SQLite" disabled={busy || stageRunning || !canStartScan} onClick={onScan}>
          <Play size={15} />
          Загрузить треки в базу
        </button>
        <button className="secondary-mini refresh-tags-button" disabled={busy || stageRunning || !hasTracks} title={helpText.refreshTags} onClick={onRefreshTags}>
          <Tags size={14} />
          Обновить теги
        </button>
        <button className="icon-button stop-button database-clear-button" disabled={busy || stageRunning || !hasTracks} title={helpText.clearDatabase} aria-label="Удалить все данные из базы" onClick={onClearDatabase}>
          <Trash2 size={15} />
        </button>
      </div>
      <div className="analysis-section-title">
        <span>Анализ моделей</span>
        <small>Запуск отдельных алгоритмов для текущей базы</small>
      </div>
      <div className="analysis-actions">
        <AnalysisButton label="SONARA" icon={<Gauge size={16} />} disabled={busy || stageRunning || !hasTracks} title={helpText.sonaraAnalyze} onRun={onSonaraAnalyze} onReset={() => onResetAnalysis("sonara")} />
        <AnalysisButton label="MAEST" icon={<Tags size={16} />} disabled={busy || stageRunning || !hasTracks} title={helpText.maestAnalyze} onRun={onGenreAnalyze} onReset={() => onResetAnalysis("maest")} />
        <AnalysisButton label="MERT" icon={<Wand2 size={16} />} disabled={busy || stageRunning || !hasTracks} title={helpText.mertAnalyze} onRun={() => onAnalyze("mert")} onReset={() => onResetAnalysis("mert")} />
        <AnalysisButton label="CLAP" icon={<Search size={16} />} disabled={busy || stageRunning || !hasTracks} title={helpText.clapAnalyze} onRun={() => onAnalyze("clap")} onReset={() => onResetAnalysis("clap")} />
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
              className={analysisDevice === device ? "active" : ""}
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
          <button className="icon-button" disabled={busy || analysisBatchSize <= 1} onClick={() => adjustAnalysisBatchSize(-1)} aria-label="Уменьшить batch size"><Minus size={15} /></button>
          <input type="number" min={1} max={maxAnalysisBatchSize} value={analysisBatchSize} title={helpText.analysisBatchSize} onChange={(event) => onAnalysisBatchSizeChange(Math.min(maxAnalysisBatchSize, Math.max(1, Number(event.target.value) || 1)))} />
          <button className="icon-button" disabled={busy || analysisBatchSize >= maxAnalysisBatchSize} onClick={() => adjustAnalysisBatchSize(1)} aria-label="Увеличить batch size"><Plus size={15} /></button>
        </div>
        <small>SONARA: параллельные треки. MAEST/MERT/CLAP: inference batch; CPU 1-4, CUDA начни с 4-8.</small>
        <button className="secondary-mini" disabled={busy || stageRunning || !hasTracks} onClick={() => onAnalyze("fake")}>
          <Gauge size={14} />
          Smoke
        </button>
      </div>
      <UnifiedLog
        processKind={processLogKind}
        scanJob={scanJob}
        analysisJob={analysisJob}
        genreTagJob={genreTagJob}
        events={activityLog}
      />
    </aside>
  );
}
