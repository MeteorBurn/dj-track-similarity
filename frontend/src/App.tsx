import {
  Download,
  FolderOpen,
  ListMusic,
  Minus,
  Play,
  Plus,
  RefreshCcw,
  Save,
  Search,
  Square,
  Tags,
  Trash2,
  Wand2,
  X
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { AnalysisJobStatus, api, ScanStats, SearchResult, Track } from "./api";

type Notice = { kind: "ok" | "error" | "idle"; text: string };
type ActivityEvent = { id: number; time: number; level: "info" | "ok" | "warn" | "error"; message: string; detail?: string };

const defaultNotice: Notice = { kind: "idle", text: "Готово к работе" };

function optimalWorkerLimit() {
  const cores = typeof navigator === "undefined" ? 4 : navigator.hardwareConcurrency || 4;
  return Math.max(1, Math.min(8, Math.floor(cores / 2) || 1));
}

export function App() {
  const [tracks, setTracks] = useState<Track[]>([]);
  const [query, setQuery] = useState("");
  const [musicRoot, setMusicRoot] = useState("");
  const [outputDir, setOutputDir] = useState("");
  const [seeds, setSeeds] = useState<number[]>([]);
  const [results, setResults] = useState<SearchResult[]>([]);
  const [playlist, setPlaylist] = useState<Track[]>([]);
  const [playlistName, setPlaylistName] = useState("seamless-set");
  const [playlistId, setPlaylistId] = useState<number | null>(null);
  const [preview, setPreview] = useState<Track | null>(null);
  const [analysisJob, setAnalysisJob] = useState<AnalysisJobStatus | null>(null);
  const [scanJob, setScanJob] = useState<ScanStats | null>(null);
  const [processLogKind, setProcessLogKind] = useState<"scan" | "analysis">("scan");
  const [analysisLimit, setAnalysisLimit] = useState(10);
  const [workerCount, setWorkerCount] = useState(1);
  const [notice, setNotice] = useState<Notice>(defaultNotice);
  const [activityLog, setActivityLog] = useState<ActivityEvent[]>([
    { id: 1, time: Date.now(), level: "info", message: "Интерфейс загружен" }
  ]);
  const [busy, setBusy] = useState(false);
  const [filters, setFilters] = useState({
    bpmTolerance: 4,
    keyCompatibility: true,
    energyEnabled: false,
    energyMin: 0,
    energyMax: 1,
    minSimilarity: 0.15,
    epsilon: 0.04,
    noise: 0,
    lookback: 2,
    limit: 50
  });

  const seedSet = useMemo(() => new Set(seeds), [seeds]);
  const playlistSet = useMemo(() => new Set(playlist.map((track) => track.id)), [playlist]);
  const filteredTracks = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return tracks;
    return tracks.filter((track) =>
      [track.artist, track.title, track.album, track.path].some((value) => value?.toLowerCase().includes(needle))
    );
  }, [tracks, query]);
  const seedTracks = useMemo(() => seeds.map((id) => tracks.find((track) => track.id === id)).filter(Boolean) as Track[], [seeds, tracks]);
  const scanRunning = Boolean(scanJob?.state && ["queued", "running"].includes(scanJob.state));
  const analysisRunning = Boolean(analysisJob && ["queued", "running"].includes(analysisJob.state));
  const stageRunning = scanRunning || analysisRunning;
  const canStartStage = Boolean(musicRoot || analysisJob?.state === "cancelled");
  const maxWorkers = useMemo(() => optimalWorkerLimit(), []);

  useEffect(() => {
    void refreshTracks();
    void api.latestScanJob().then((job) => {
      if (job) {
        setScanJob(job);
        setProcessLogKind("scan");
      }
    }).catch(() => undefined);
    void api.latestAnalyzeJob().then((job) => {
      if (job) {
        setAnalysisJob(job);
        if (["queued", "running"].includes(job.state)) setProcessLogKind("analysis");
      }
    }).catch(() => undefined);
  }, []);

  useEffect(() => {
    if (!scanJob?.job_id || !["queued", "running"].includes(scanJob.state || "")) return;
    const timer = window.setInterval(() => {
      void api.scanJob(scanJob.job_id!).then((job) => {
        setScanJob(job);
        if (["completed", "cancelled", "failed"].includes(job.state || "")) {
          void refreshTracks();
          if (job.state === "completed") {
            appendActivity("ok", "Сканирование завершено", scanSummary(job));
          }
          if (job.state === "cancelled") {
            appendActivity("warn", "Сканирование остановлено", scanSummary(job));
          }
        }
      }).catch((error) => {
        setNotice({ kind: "error", text: error instanceof Error ? error.message : String(error) });
      });
    }, 1200);
    return () => window.clearInterval(timer);
  }, [scanJob?.job_id, scanJob?.state]);

  useEffect(() => {
    if (!analysisJob || !["queued", "running"].includes(analysisJob.state)) return;
    const timer = window.setInterval(() => {
      void api.analyzeJob(analysisJob.job_id).then((job) => {
        setAnalysisJob(job);
        if (["completed", "cancelled", "failed"].includes(job.state)) {
          void refreshTracks();
        }
      }).catch((error) => {
        setNotice({ kind: "error", text: error instanceof Error ? error.message : String(error) });
      });
    }, 1500);
    return () => window.clearInterval(timer);
  }, [analysisJob?.job_id, analysisJob?.state]);

  async function run<T>(action: () => Promise<T>, ok: (value: T) => string | void) {
    setBusy(true);
    try {
      const value = await action();
      await refreshTracks();
      const text = ok(value);
      setNotice({ kind: "ok", text: text || "Готово" });
      return value;
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      setNotice({ kind: "error", text: message });
      appendActivity("error", "Ошибка", message);
    } finally {
      setBusy(false);
    }
  }

  function appendActivity(level: ActivityEvent["level"], message: string, detail?: string) {
    setActivityLog((current) => [
      { id: Date.now() + Math.random(), time: Date.now(), level, message, detail },
      ...current
    ].slice(0, 80));
  }

  async function refreshTracks() {
    const nextTracks = await api.tracks();
    setTracks(nextTracks);
  }

  function addSeed(track: Track) {
    setSeeds((current) => (current.includes(track.id) ? current : [...current, track.id]));
  }

  function removeSeed(trackId: number) {
    setSeeds((current) => current.filter((id) => id !== trackId));
  }

  function addToPlaylist(track: Track) {
    if (!playlistSet.has(track.id)) {
      appendActivity("ok", "Добавлен в сет", displayTrack(track));
    }
    setPlaylistId(null);
    setPlaylist((current) => (current.some((item) => item.id === track.id) ? current : [...current, track]));
  }

  function removeFromPlaylist(trackId: number) {
    const removed = playlist.find((track) => track.id === trackId);
    if (removed) {
      appendActivity("warn", "Убран из сета", displayTrack(removed));
    }
    setPlaylistId(null);
    setPlaylist((current) => current.filter((track) => track.id !== trackId));
  }

  function togglePlaylist(track: Track) {
    if (playlistSet.has(track.id)) {
      removeFromPlaylist(track.id);
    } else {
      addToPlaylist(track);
    }
  }

  async function handleSearch() {
    if (!seeds.length) {
      setNotice({ kind: "error", text: "Выберите seed-треки" });
      return;
    }
    const lookbackTrackIds = filters.lookback > 0 ? playlist.slice(-filters.lookback).map((track) => track.id) : [];
    appendActivity("info", "Поиск запущен", `${seeds.length} seed · lookback ${lookbackTrackIds.length}`);
    await run(
      () =>
        api.search({
          seed_track_ids: seeds,
          lookback_track_ids: lookbackTrackIds,
          limit: filters.limit,
          bpm_tolerance: filters.bpmTolerance,
          key_compatibility: filters.keyCompatibility ? "compatible" : null,
          energy_min: filters.energyEnabled ? filters.energyMin : null,
          energy_max: filters.energyEnabled ? filters.energyMax : null,
          min_similarity: filters.minSimilarity,
          epsilon: filters.epsilon,
          noise: filters.noise
        }),
      (value) => {
        setResults(value);
        appendActivity("ok", "Поиск завершен", `Найдено: ${value.length}`);
        return `Найдено: ${value.length}`;
      }
    );
  }

  async function handleScan() {
    appendActivity("info", "Сканирование запущено", musicRoot);
    setProcessLogKind("scan");
    setScanJob(null);
    await run(
      () => api.scan(musicRoot, workerCount),
      (value) => {
        setScanJob(value);
        const detail = value.job_id ? `job ${value.job_id.slice(0, 8)} · ${value.total || 0} файлов` : scanSummary(value);
        appendActivity("ok", "Scan job создан", detail);
        return detail;
      }
    );
  }

  async function handleChooseFolder() {
    await run(
      () => api.chooseFolder(),
      (value) => {
        if (!value.path) {
          appendActivity("info", "Выбор папки отменен");
          return "Выбор папки отменен";
        }
        setMusicRoot(value.path);
        appendActivity("ok", "Папка выбрана", value.path);
        return value.path;
      }
    );
  }

  async function handleCancelScan() {
    if (!scanJob?.job_id) return;
    await run(
      () => api.cancelScanJob(scanJob.job_id!),
      (job) => {
        setScanJob(job);
        appendActivity("warn", "Scan cancel requested", job.job_id?.slice(0, 8));
        return `Cancel requested: ${job.job_id?.slice(0, 8)}`;
      }
    );
  }

  async function handleCreatePlaylist() {
    if (!playlist.length) {
      setNotice({ kind: "error", text: "Плейлист пуст" });
      return;
    }
    await run(
      () => api.createPlaylist(playlistName || "seamless-set", playlist.map((track) => track.id)),
      (value) => {
        setPlaylistId(value.id);
        appendActivity("ok", "Плейлист сохранен", `#${value.id} · ${value.track_ids.length} треков`);
        return `Плейлист #${value.id}`;
      }
    );
  }

  async function handleAnalyze(adapter: "mert" | "fake") {
    const limit = analysisLimit > 0 ? analysisLimit : undefined;
    appendActivity("info", `${adapter.toUpperCase()} анализ запущен`, limit ? `limit ${limit}` : "вся библиотека");
    setProcessLogKind("analysis");
    setAnalysisJob(null);
    await run(
      () => api.analyze(adapter, limit, workerCount),
      (job) => {
        setAnalysisJob(job);
        appendActivity("ok", "Analysis job создан", `${job.job_id.slice(0, 8)} · ${job.total} треков`);
        return `${adapter.toUpperCase()} job ${job.job_id.slice(0, 8)}: ${job.total} треков`;
      }
    );
  }

  async function handleCancelAnalyze() {
    if (!analysisJob) return;
    await run(
      () => api.cancelAnalyzeJob(analysisJob.job_id),
      (job) => {
        setAnalysisJob(job);
        appendActivity("warn", "Analysis cancel requested", job.job_id.slice(0, 8));
        return `Cancel requested: ${job.job_id.slice(0, 8)}`;
      }
    );
  }

  async function handleStageControl() {
    if (stageRunning) {
      return;
    }
    if (scanJob?.state === "cancelled" && musicRoot) {
      await handleScan();
      return;
    }
    if (analysisJob?.state === "cancelled") {
      await handleAnalyze(analysisJob.adapter_name === "fake" ? "fake" : "mert");
      return;
    }
    if (musicRoot) {
      await handleScan();
    }
  }

  async function handleStopActiveStage() {
    if (scanRunning) {
      await handleCancelScan();
      return;
    }
    if (analysisRunning) {
      await handleCancelAnalyze();
    }
  }

  async function handleExport(format: "m3u" | "csv") {
    if (!playlistId) {
      setNotice({ kind: "error", text: "Сначала сохраните плейлист" });
      return;
    }
    await run(() => api.exportPlaylist(playlistId, outputDir || ".", format), (value) => {
      appendActivity("ok", `Экспорт ${format.toUpperCase()}`, value.path);
      return value.path;
    });
  }

  async function handleTags(apply: boolean) {
    const ids = playlist.length ? playlist.map((track) => track.id) : seeds;
    if (!ids.length) {
      setNotice({ kind: "error", text: "Выберите треки" });
      return;
    }
    await run(() => (apply ? api.tagApply(ids) : api.tagPreview(ids)), (value) => {
      appendActivity(apply ? "ok" : "info", apply ? "Теги записаны" : "Tag preview", `${value.length} треков`);
      return `${apply ? "Записано" : "Preview"}: ${value.length}`;
    });
  }

  function adjustWorkers(delta: number) {
    setWorkerCount((current) => Math.min(maxWorkers, Math.max(1, current + delta)));
  }

  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <h1>dj-track-similarity</h1>
          <span className="meta">{tracks.length} треков · {tracks.filter((track) => track.embedding_model).length} с эмбеддингами</span>
        </div>
        <div className={`notice ${notice.kind}`}>{notice.text}</div>
      </header>

      <section className="workspace">
        <aside className="panel library-panel">
          <div className="panel-title">
            <FolderOpen size={18} />
            <h2>1. База и анализ</h2>
          </div>
          <div className="path-row library-path-row">
            <input value={musicRoot} onChange={(event) => setMusicRoot(event.target.value)} placeholder="D:/Music" />
            <button className="icon-button folder-picker" title="Выбрать папку" aria-label="Выбрать папку" disabled={busy || stageRunning} onClick={() => void handleChooseFolder()}>
              <FolderOpen size={17} />
            </button>
          </div>
          <div className="stage-control-row">
            <button className="primary stage-control" disabled={busy || stageRunning || !canStartStage} onClick={() => void handleStageControl()}>
              Старт
            </button>
            <button className="icon-button stop-button" title="Остановить текущий этап" aria-label="Остановить текущий этап" disabled={busy || !stageRunning} onClick={() => void handleStopActiveStage()}>
              <Square size={15} />
            </button>
            <span className={`process-indicator ${stageRunning ? "running" : ""}`} title={stageIndicatorLabel(scanJob, analysisJob)} aria-label={stageIndicatorLabel(scanJob, analysisJob)}>
              <RefreshCcw size={17} />
            </span>
          </div>
          <ProcessLog kind={processLogKind} scanJob={scanJob} analysisJob={analysisJob} />
          <ActivityLog events={activityLog} />
          <div className="action-row">
            <button disabled={busy || stageRunning} onClick={() => void handleAnalyze("mert")}>
              <Wand2 size={16} />
              MERT
            </button>
          </div>
          <label className="analysis-limit">
            Analyze limit
            <input type="number" min={0} max={100000} value={analysisLimit} onChange={(event) => setAnalysisLimit(Number(event.target.value))} />
          </label>
          <div className="worker-control">
            <span>Потоки</span>
            <div className="stepper">
              <button className="icon-button" disabled={busy || workerCount <= 1} onClick={() => adjustWorkers(-1)} aria-label="Уменьшить количество потоков"><Minus size={15} /></button>
              <input type="number" min={1} max={maxWorkers} value={workerCount} onChange={(event) => setWorkerCount(Math.min(maxWorkers, Math.max(1, Number(event.target.value) || 1)))} />
              <button className="icon-button" disabled={busy || workerCount >= maxWorkers} onClick={() => adjustWorkers(1)} aria-label="Увеличить количество потоков"><Plus size={15} /></button>
            </div>
            <small>1-{maxWorkers} оптимум</small>
          </div>
        </aside>

        <section className="panel track-panel">
          <div className="panel-title">
            <ListMusic size={18} />
            <h2>2. Библиотека и прослушивание</h2>
          </div>
          <div className="search-input">
            <Search size={16} />
            <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="artist, title, path" />
          </div>
          <div className="player library-player">
            <span>{preview ? displayTrack(preview) : "Preview"}</span>
            {preview && <audio controls src={`/media/${preview.id}`} />}
          </div>
          <TrackList
            tracks={filteredTracks}
            seedSet={seedSet}
            playlistSet={playlistSet}
            onSeed={addSeed}
            onTogglePlaylist={togglePlaylist}
            onPreview={setPreview}
          />
        </section>

        <aside className="panel search-panel">
          <section className="search-section">
            <div className="panel-title">
              <Search size={18} />
              <h2>3. Поиск и прослушивание</h2>
            </div>
          <div className="seed-strip">
            {seedTracks.map((track) => (
              <button className="seed-chip" key={track.id} onClick={() => removeSeed(track.id)}>
                {displayTrack(track)}
                <X size={14} />
              </button>
            ))}
          </div>
          <div className="filters">
            <label>BPM ±<input type="number" value={filters.bpmTolerance} min={0} max={32} onChange={(event) => setFilters({ ...filters, bpmTolerance: Number(event.target.value) })} /></label>
            <label>Similarity<input type="number" value={filters.minSimilarity} min={0} max={1} step={0.01} onChange={(event) => setFilters({ ...filters, minSimilarity: Number(event.target.value) })} /></label>
            <label>Epsilon<input type="number" value={filters.epsilon} min={0} max={1} step={0.01} onChange={(event) => setFilters({ ...filters, epsilon: Number(event.target.value) })} /></label>
            <label>Noise<input type="number" value={filters.noise} min={0} max={1} step={0.01} onChange={(event) => setFilters({ ...filters, noise: Number(event.target.value) })} /></label>
            <label>Lookback<input type="number" value={filters.lookback} min={0} max={12} onChange={(event) => setFilters({ ...filters, lookback: Number(event.target.value) })} /></label>
            <label>Energy min<input type="number" disabled={!filters.energyEnabled} value={filters.energyMin} min={0} max={1} step={0.01} onChange={(event) => setFilters({ ...filters, energyMin: Number(event.target.value) })} /></label>
            <label>Energy max<input type="number" disabled={!filters.energyEnabled} value={filters.energyMax} min={0} max={1} step={0.01} onChange={(event) => setFilters({ ...filters, energyMax: Number(event.target.value) })} /></label>
            <label>Limit<input type="number" value={filters.limit} min={1} max={500} onChange={(event) => setFilters({ ...filters, limit: Number(event.target.value) })} /></label>
            <label className="toggle"><input type="checkbox" checked={filters.keyCompatibility} onChange={(event) => setFilters({ ...filters, keyCompatibility: event.target.checked })} />Key</label>
            <label className="toggle"><input type="checkbox" checked={filters.energyEnabled} onChange={(event) => setFilters({ ...filters, energyEnabled: event.target.checked })} />Energy</label>
          </div>
          <button className="primary" disabled={busy || !seeds.length} onClick={() => void handleSearch()}>
            <Search size={17} />
            Найти
          </button>
          <div className="results-list">
            {results.map(({ track, score }) => (
              <ResultRow key={track.id} track={track} score={score} inPlaylist={playlistSet.has(track.id)} onTogglePlaylist={togglePlaylist} onPreview={setPreview} />
            ))}
          </div>
          </section>
          <section className="playlist-section">
          <div className="panel-title">
            <ListMusic size={18} />
            <h2>Сет и экспорт</h2>
            <span className="panel-counter">{playlist.length}</span>
          </div>
          <input value={playlistName} onChange={(event) => setPlaylistName(event.target.value)} />
          <span className={`save-state ${playlistId ? "saved" : "dirty"}`}>
            {playlistId ? `Сохранен #${playlistId}` : playlist.length ? "Есть несохраненные изменения" : "Сет пуст"}
          </span>
          <div className="playlist-list">
            {playlist.length === 0 ? (
              <div className="empty-state">
                Добавляй треки из библиотеки или результатов поиска кнопкой <Plus size={14} />.
              </div>
            ) : (
              playlist.map((track, index) => (
                <div className="playlist-row" key={track.id}>
                  <span className="row-index">{index + 1}</span>
                  <button className="icon-button" title="Preview" aria-label={`Preview ${displayTrack(track)}`} onClick={() => setPreview(track)}><Play size={15} /></button>
                  <div className="track-copy">
                    <strong>{displayTrack(track)}</strong>
                    <span>{trackInfo(track)}</span>
                  </div>
                  <button className="icon-button intent-remove" title="Убрать из сета" aria-label={`Убрать ${displayTrack(track)} из сета`} onClick={() => removeFromPlaylist(track.id)}><Trash2 size={15} /></button>
                </div>
              ))
            )}
          </div>
          <button className="primary" disabled={busy || !playlist.length} onClick={() => void handleCreatePlaylist()}>
            <Save size={17} />
            Сохранить
          </button>
          <div className="path-row output-row">
            <input value={outputDir} onChange={(event) => setOutputDir(event.target.value)} placeholder="D:/Exports" />
          </div>
          <div className="action-row">
            <button disabled={busy || !playlistId} onClick={() => void handleExport("m3u")}><Download size={16} />M3U</button>
            <button disabled={busy || !playlistId} onClick={() => void handleExport("csv")}><Download size={16} />CSV</button>
          </div>
          <div className="action-row">
            <button disabled={busy} onClick={() => void handleTags(false)}><Tags size={16} />Preview</button>
            <button disabled={busy} onClick={() => void handleTags(true)}><Tags size={16} />Write</button>
          </div>
          </section>
        </aside>
      </section>
    </main>
  );
}

function ProcessLog({
  kind,
  scanJob,
  analysisJob
}: {
  kind: "scan" | "analysis";
  scanJob: ScanStats | null;
  analysisJob: AnalysisJobStatus | null;
}) {
  if (kind === "analysis") {
    return <AnalysisProcessLog job={analysisJob} />;
  }
  return <ScanProcessLog job={scanJob} />;
}

function ScanProcessLog({ job }: { job: ScanStats | null }) {
  if (!job) {
    return <div className="process-box">Сканирование не запущено</div>;
  }
  const total = job.total || 0;
  const processed = job.processed || 0;
  const percent = total ? Math.round((processed / total) * 100) : 100;
  const running = ["queued", "running"].includes(job.state || "");
  const etaSeconds = running && job.avg_seconds_per_track ? Math.max(0, (total - processed) * job.avg_seconds_per_track) : null;
  const latestEvents = [...(job.events || [])].reverse().slice(0, 12);
  return (
    <div className="process-box">
      <div className="process-head">
        <strong>{job.state || "idle"}</strong>
        <span>{job.root || "scan"} · {processed}/{total}</span>
      </div>
      <progress max={total || 1} value={processed} />
      <div className="process-grid">
        <span>+{job.added || 0}</span>
        <span>upd {job.updated || 0}</span>
        <span>same {job.unchanged || 0}</span>
        <span>fail {job.failed || 0}</span>
        <span>{job.workers || 1} поток</span>
        <span>{percent}%</span>
      </div>
      {job.avg_seconds_per_track && <span className="analysis-muted">{job.avg_seconds_per_track.toFixed(2)} s/file{etaSeconds ? ` · ETA ${formatEta(etaSeconds)}` : ""}</span>}
      {job.current_path && <span className="analysis-current">Сейчас: {basename(job.current_path)}</span>}
      <div className="process-log">
        <div className="process-log-title">
          <span>Журнал процесса</span>
          <span>{latestEvents.length}/{job.events?.length || 0}</span>
        </div>
        <div className="process-log-list simple">
        {latestEvents.length === 0 ? (
          <span className="process-log-empty">Событий пока нет</span>
        ) : (
          latestEvents.map((event, index) => (
            <div className={`process-log-row ${event.level}`} key={`${event.timestamp}-${index}`}>
              <time>{formatTime(event.timestamp)}</time>
              <strong>{event.level}</strong>
              <span>
              {event.message}{event.path ? ` · ${basename(event.path)}` : ""}
              </span>
            </div>
          ))
        )}
        </div>
      </div>
    </div>
  );
}

function ActivityLog({ events }: { events: ActivityEvent[] }) {
  return (
    <div className="activity-log">
      <div className="activity-log-title">
        <span>Журнал действий</span>
        <span>{events.length}</span>
      </div>
      <div className="activity-log-list">
        {events.map((event) => (
          <div className={`activity-log-row ${event.level}`} key={event.id}>
            <time>{new Date(event.time).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit", second: "2-digit" })}</time>
            <strong>{event.message}</strong>
            {event.detail && <span>{event.detail}</span>}
          </div>
        ))}
      </div>
    </div>
  );
}

function scanSummary(job: ScanStats) {
  return `+${job.added || 0} · обновлено ${job.updated || 0} · без изменений ${job.unchanged || 0} · ошибок ${job.failed || 0}`;
}

function stageIndicatorLabel(scanJob: ScanStats | null, analysisJob: AnalysisJobStatus | null) {
  if (scanJob?.state && ["queued", "running"].includes(scanJob.state)) return "Идет сканирование";
  if (analysisJob && ["queued", "running"].includes(analysisJob.state)) return "Идет анализ";
  if (scanJob?.state === "cancelled" || analysisJob?.state === "cancelled") return "Этап остановлен";
  return "Процесс не запущен";
}

function AnalysisProcessLog({ job }: { job: AnalysisJobStatus | null }) {
  if (!job) {
    return <div className="process-box">Анализ не запущен</div>;
  }
  const percent = job.total ? Math.round((job.processed / job.total) * 100) : 100;
  const running = ["queued", "running"].includes(job.state);
  const etaSeconds = running && job.avg_seconds_per_track ? Math.max(0, (job.total - job.processed) * job.avg_seconds_per_track) : null;
  const latestEvents = [...job.events].reverse().slice(0, 14);
  return (
    <div className="process-box">
      <div className="process-head">
        <strong>{job.state}</strong>
        <span>{job.model_name || job.adapter_name} · {job.device || "device pending"}</span>
      </div>
      <progress max={job.total || 1} value={job.processed} />
      <div className="process-grid">
        <span>{job.processed}/{job.total}</span>
        <span>ok {job.analyzed}</span>
        <span>fail {job.failed}</span>
        <span>{job.workers || 1} поток</span>
        <span>{percent}%</span>
      </div>
      {job.avg_seconds_per_track && <span className="analysis-muted">{job.avg_seconds_per_track.toFixed(2)} s/track{etaSeconds ? ` · ETA ${formatEta(etaSeconds)}` : ""}</span>}
      {job.current_path && <span className="analysis-current">Сейчас: {basename(job.current_path)}</span>}
      {job.errors.length > 0 && <span className="analysis-error">{job.errors[0].path}: {job.errors[0].error}</span>}
      <div className="process-log">
        <div className="process-log-title">
          <span>Журнал процесса</span>
          <span>{latestEvents.length}/{job.events.length}</span>
        </div>
        <div className="process-log-list">
          {latestEvents.length === 0 ? (
            <span className="process-log-empty">Событий пока нет</span>
          ) : (
            latestEvents.map((event, index) => (
              <div className={`process-log-row ${event.level}`} key={`${event.timestamp}-${index}`}>
                <time>{formatTime(event.timestamp)}</time>
                <strong>{event.level}</strong>
                <span>{event.message}{event.path ? ` · ${basename(event.path)}` : ""}</span>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}

function TrackList({
  tracks,
  seedSet,
  playlistSet,
  onSeed,
  onTogglePlaylist,
  onPreview
}: {
  tracks: Track[];
  seedSet: Set<number>;
  playlistSet: Set<number>;
  onSeed: (track: Track) => void;
  onTogglePlaylist: (track: Track) => void;
  onPreview: (track: Track) => void;
}) {
  return (
    <div className="track-list">
      {tracks.map((track) => (
        <div className="track-row" key={track.id}>
          <button className="icon-button" title="Preview" aria-label={`Preview ${displayTrack(track)}`} onClick={() => onPreview(track)}><Play size={15} /></button>
          <div className="track-copy">
            <strong>{displayTrack(track)}</strong>
            <span>{trackInfo(track)}</span>
          </div>
          <button className={`icon-button ${seedSet.has(track.id) ? "active" : ""}`} title="Seed" aria-label={`Seed ${displayTrack(track)}`} onClick={() => onSeed(track)}><Search size={15} /></button>
          <button
            className={`icon-button ${playlistSet.has(track.id) ? "intent-remove active" : "intent-add"}`}
            title={playlistSet.has(track.id) ? "Убрать из сета" : "В сет"}
            aria-label={playlistSet.has(track.id) ? `Убрать ${displayTrack(track)} из сета` : `Добавить ${displayTrack(track)} в сет`}
            onClick={() => onTogglePlaylist(track)}
          >
            {playlistSet.has(track.id) ? <Minus size={15} /> : <Plus size={15} />}
          </button>
        </div>
      ))}
    </div>
  );
}

function ResultRow({
  track,
  score,
  inPlaylist,
  onTogglePlaylist,
  onPreview
}: {
  track: Track;
  score: number;
  inPlaylist: boolean;
  onTogglePlaylist: (track: Track) => void;
  onPreview: (track: Track) => void;
}) {
  return (
    <div className="result-row">
      <button className="icon-button" title="Preview" aria-label={`Preview ${displayTrack(track)}`} onClick={() => onPreview(track)}><Play size={15} /></button>
      <div className="track-copy">
        <strong>{displayTrack(track)}</strong>
        <span>{trackInfo(track)}</span>
      </div>
      <meter min={0} max={1} value={Math.max(0, Math.min(1, score))} />
      <span className="score">{score.toFixed(3)}</span>
      <button
        className={`icon-button ${inPlaylist ? "intent-remove active" : "intent-add"}`}
        title={inPlaylist ? "Убрать из сета" : "В сет"}
        aria-label={inPlaylist ? `Убрать ${displayTrack(track)} из сета` : `Добавить ${displayTrack(track)} в сет`}
        onClick={() => onTogglePlaylist(track)}
      >
        {inPlaylist ? <Minus size={15} /> : <Plus size={15} />}
      </button>
    </div>
  );
}

function displayTrack(track: Track) {
  if (track.artist && track.title) return `${track.artist} - ${track.title}`;
  return track.title || track.path.split(/[\\/]/).pop() || track.path;
}

function trackInfo(track: Track) {
  const parts = [
    track.bpm ? `${track.bpm.toFixed(1)} BPM` : null,
    track.musical_key,
    track.energy != null ? `E ${track.energy.toFixed(2)}` : null,
    track.embedding_model ? "vec" : "no vec"
  ].filter(Boolean);
  return parts.join(" · ");
}

function formatEta(seconds: number) {
  const minutes = Math.floor(seconds / 60);
  const rest = Math.round(seconds % 60);
  if (minutes < 60) return `${minutes}m ${rest}s`;
  const hours = Math.floor(minutes / 60);
  return `${hours}h ${minutes % 60}m`;
}

function basename(path: string) {
  return path.split(/[\\/]/).pop() || path;
}

function formatTime(timestamp: number) {
  return new Date(timestamp * 1000).toLocaleTimeString("ru-RU", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit"
  });
}
