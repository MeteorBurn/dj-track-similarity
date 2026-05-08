import {
  Cpu,
  Download,
  FolderOpen,
  Gauge,
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
import { Fragment, ReactNode, useEffect, useMemo, useState } from "react";
import { AnalysisJobStatus, api, ScanStats, SearchResult, Track } from "./api";

type Notice = { kind: "ok" | "error" | "idle"; text: string };
type ActivityEvent = { id: number; time: number; level: "info" | "ok" | "warn" | "error"; message: string; detail?: string };
type DeviceMode = "auto" | "cpu" | "cuda";
type AnalysisAdapter = "mert" | "clap" | "fake";
type ResetAdapter = "sonara" | "maest" | "mert" | "clap" | "fake";

const defaultNotice: Notice = { kind: "idle", text: "Готово к работе" };

const helpText = {
  musicRoot: "Папка с музыкой. Формат: путь Windows или POSIX, например D:/Music. Тип: строка. Папка должна существовать.",
  analyzeLimit: "Сколько треков анализировать. Тип: целое число 0-100000. 0 = вся библиотека.",
  scanWorkers: "Параллельное чтение метаданных при сканировании. Тип: целое число. Диапазон зависит от CPU, обычно 1-8.",
  refreshTags: "Перечитать только file tags через Mutagen для уже найденных треков. Пути, Sonara, MAEST, MERT и CLAP не трогаются.",
  clearDatabase: "Удалить все записи из SQLite: треки, эмбеддинги, анализы, плейлисты и сет. Аудиофайлы на диске не трогаются.",
  analysisDevice: "Устройство для MERT/CLAP. Значения: AUTO, CPU, CUDA. AUTO выберет CUDA, если PyTorch видит GPU, иначе CPU.",
  sonaraAnalyze: "SONARA считает BPM, key и музыкальные признаки. Нужна для базового описания трека и будущих DJ-фильтров.",
  maestAnalyze: "MAEST определяет жанровые метки. Нужна для жанровой навигации и проверки характера библиотеки.",
  writeMaestGenres: "Перезаписать стандартный Genre/TCON/©gen в аудиофайлах жанрами MAEST. Плееры вроде AIMP будут видеть эти жанры.",
  mertAnalyze: "MERT строит аудио-эмбеддинги. Нужна для поиска похожих треков от выбранных seed-треков.",
  clapAnalyze: "CLAP связывает аудио с текстовым описанием. Нужна для поиска треков по фразе о звучании.",
  analysisBatchSize: "Размер inference batch для MERT/CLAP. Тип: целое число 1-16. CPU: 1-4; CUDA: начни с 4-8.",
  librarySearch: "Фильтр библиотеки. Формат: текст. Ищет по artist, title, album и path.",
  similarity: "Минимальный cosine similarity. Тип: число с точкой, диапазон 0.00-1.00. Для чистой проверки MERT оставь 0.00.",
  textPrompt: "CLAP text search. Формат: короткая фраза через запятые: genre, mood, sound, drums, vocal/no vocals. Тип: строка.",
  lookback: "Сколько последних треков сета добавить в контекст поиска. Тип: целое число 0-12.",
  limit: "Максимум результатов поиска. Тип: целое число 1-500.",
  disabledBpm: "Отключено. BPM-фильтр по метаданным. Тип был бы число, например 128 или 128.5; сейчас не участвует в MERT-only проверке.",
  disabledKey: "Отключено. Key-фильтр по метаданным. Формат был бы Camelot 1A-12B или обычная строка key; сейчас не участвует в MERT-only проверке.",
  disabledEnergy: "Отключено. Energy пока не вычисляется. Будущий формат: число с точкой 0.00-1.00.",
  disabledEpsilon: "Отключено до калибровки. Будущий формат: число с точкой 0.00-1.00, обычно малое значение вроде 0.01-0.05.",
  disabledNoise: "Отключено до калибровки. Будущий формат: число с точкой 0.00-1.00, но безопасный диапазон еще не выбран.",
  playlistName: "Название сохраняемого сета. Формат: текст. Используется как имя плейлиста и файла экспорта.",
  outputDir: "Папка экспорта. Формат: путь Windows или POSIX, например D:/Exports. Если папки нет, она будет создана.",
} as const;

function optimalWorkerLimit() {
  const cores = typeof navigator === "undefined" ? 4 : navigator.hardwareConcurrency || 4;
  return Math.max(1, Math.min(8, Math.floor(cores / 2) || 1));
}

export function App() {
  const [tracks, setTracks] = useState<Track[]>([]);
  const [query, setQuery] = useState("");
  const [musicRoot, setMusicRoot] = useState("");
  const [textQuery, setTextQuery] = useState("");
  const [outputDir, setOutputDir] = useState("");
  const [seeds, setSeeds] = useState<number[]>([]);
  const [results, setResults] = useState<SearchResult[]>([]);
  const [playlist, setPlaylist] = useState<Track[]>([]);
  const [playlistName, setPlaylistName] = useState("seamless-set");
  const [playlistId, setPlaylistId] = useState<number | null>(null);
  const [preview, setPreview] = useState<Track | null>(null);
  const [metadataTrack, setMetadataTrack] = useState<Track | null>(null);
  const [analysisJob, setAnalysisJob] = useState<AnalysisJobStatus | null>(null);
  const [scanJob, setScanJob] = useState<ScanStats | null>(null);
  const [processLogKind, setProcessLogKind] = useState<"scan" | "analysis">("scan");
  const [logTab, setLogTab] = useState<"journal" | "process">("journal");
  const [analysisLimit, setAnalysisLimit] = useState(0);
  const [scanWorkers, setScanWorkers] = useState(1);
  const [analysisBatchSize, setAnalysisBatchSize] = useState(4);
  const [analysisDevice, setAnalysisDevice] = useState<DeviceMode>("auto");
  const [notice, setNotice] = useState<Notice>(defaultNotice);
  const [activityLog, setActivityLog] = useState<ActivityEvent[]>([
    { id: 1, time: Date.now(), level: "info", message: "Интерфейс загружен" }
  ]);
  const [busy, setBusy] = useState(false);
  const [filters, setFilters] = useState({
    bpmTolerance: 4,
    keyCompatibility: false,
    energyEnabled: false,
    energyMin: 0,
    energyMax: 1,
    minSimilarity: 0,
    epsilon: 0,
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
  const maestGenreTrackIds = useMemo(() => tracks.filter((track) => track.genres?.length).map((track) => track.id), [tracks]);
  const scanRunning = Boolean(scanJob?.state && ["queued", "running"].includes(scanJob.state));
  const analysisRunning = Boolean(analysisJob && ["queued", "running"].includes(analysisJob.state));
  const stageRunning = scanRunning || analysisRunning;
  const canStartStage = Boolean(musicRoot || analysisJob?.state === "cancelled");
  const maxScanWorkers = useMemo(() => optimalWorkerLimit(), []);
  const maxAnalysisBatchSize = 16;

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
    void api.latestSonaraJob().then((job) => {
      if (job) {
        setAnalysisJob((current) => (current && ["queued", "running"].includes(current.state) ? current : job));
        if (["queued", "running"].includes(job.state)) setProcessLogKind("analysis");
      }
    }).catch(() => undefined);
    void api.latestGenreJob().then((job) => {
      if (job) {
        setAnalysisJob((current) => (current && ["queued", "running"].includes(current.state) ? current : job));
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
      const request = analysisJobRequest(analysisJob);
      void request.then((job) => {
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
          bpm_tolerance: null,
          key_compatibility: null,
          energy_min: null,
          energy_max: null,
          min_similarity: filters.minSimilarity,
          epsilon: null,
          noise: 0
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
      () => api.scan(musicRoot, scanWorkers),
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

  async function handleAnalyze(adapter: AnalysisAdapter) {
    const limit = analysisLimit > 0 ? analysisLimit : undefined;
    const detail = `${analysisDevice.toUpperCase()} · batch ${analysisBatchSize} · ${limit ? `limit ${limit}` : "вся библиотека"}`;
    appendActivity("info", `${adapter.toUpperCase()} анализ запущен`, detail);
    setProcessLogKind("analysis");
    setAnalysisJob(null);
    await run(
      () => api.analyze(adapter, limit, analysisDevice, analysisBatchSize),
      (job) => {
        setAnalysisJob(job);
        appendActivity("ok", "Analysis job создан", `${job.job_id.slice(0, 8)} · ${job.total} треков · batch ${job.batch_size}`);
        return `${adapter.toUpperCase()} job ${job.job_id.slice(0, 8)}: ${job.total} треков`;
      }
    );
  }

  async function handleRefreshTags() {
    appendActivity("info", "Refresh tags запущен", "Перечитываем Mutagen tags для существующих треков");
    setProcessLogKind("scan");
    setScanJob(null);
    await run(
      () => api.refreshTags(scanWorkers),
      (value) => {
        setScanJob(value);
        const detail = value.job_id ? `job ${value.job_id.slice(0, 8)} · ${value.total || 0} треков` : scanSummary(value);
        appendActivity("ok", "Refresh tags job создан", detail);
        return detail;
      }
    );
  }

  async function handleClearDatabase() {
    const accepted = window.confirm(
      "Удалить все данные из SQLite базы: треки, анализы, эмбеддинги, плейлисты и текущий сет? Аудиофайлы на диске останутся."
    );
    if (!accepted) return;
    appendActivity("warn", "Очистка базы запущена", "Удаляем только данные SQLite, аудиофайлы не трогаем");
    await run(
      () => api.clearDatabase(),
      (value) => {
        setTracks([]);
        setSeeds([]);
        setResults([]);
        setPlaylist([]);
        setPlaylistId(null);
        setPreview(null);
        setMetadataTrack(null);
        setScanJob(null);
        setAnalysisJob(null);
        const detail = `${value.tracks_deleted} треков · ${value.embeddings_deleted} эмбеддингов · ${value.playlists_deleted} плейлистов`;
        appendActivity("ok", "База очищена", detail);
        return detail;
      }
    );
  }

  async function handleSonaraAnalyze() {
    const limit = analysisLimit > 0 ? analysisLimit : undefined;
    const detail = `${limit ? `limit ${limit}` : "вся библиотека"} · SQLite metadata`;
    appendActivity("info", "SONARA lab анализ запущен", detail);
    setProcessLogKind("analysis");
    setAnalysisJob(null);
    await run(
      () => api.analyzeSonara(limit),
      (job) => {
        setAnalysisJob(job);
        appendActivity("ok", "SONARA job создан", `${job.job_id.slice(0, 8)} · ${job.total} треков · SQLite`);
        return `SONARA job ${job.job_id.slice(0, 8)}: ${job.total} треков`;
      }
    );
  }

  async function handleResetAnalysis(adapter: ResetAdapter) {
    const label = adapter.toUpperCase();
    const accepted = window.confirm(`Сбросить результаты ${label}? Аудиофайлы не трогаем, остальные алгоритмы останутся.`);
    if (!accepted) return;
    appendActivity("warn", `${label} reset запущен`, "Точечная очистка результатов анализа");
    await run(
      () => api.resetAnalysis(adapter),
      (result) => {
        void refreshTracks();
        appendActivity("ok", `${label} reset завершен`, `tracks ${result.tracks_updated} · embeddings ${result.embeddings_deleted}`);
        return `${label}: очищено tracks ${result.tracks_updated}, embeddings ${result.embeddings_deleted}`;
      }
    );
  }

  async function handleGenreAnalyze() {
    const limit = analysisLimit > 0 ? analysisLimit : undefined;
    const detail = `${analysisDevice.toUpperCase()} · top 3 genres · ${limit ? `limit ${limit}` : "вся библиотека"}`;
    appendActivity("info", "MAEST анализ жанров запущен", detail);
    setProcessLogKind("analysis");
    setAnalysisJob(null);
    await run(
      () => api.analyzeGenres(limit, analysisDevice, 3),
      (job) => {
        setAnalysisJob(job);
        appendActivity("ok", "MAEST job создан", `${job.job_id.slice(0, 8)} · ${job.total} треков · top 3`);
        return `MAEST job ${job.job_id.slice(0, 8)}: ${job.total} треков`;
      }
    );
  }

  async function handleTextSearch() {
    const prompt = textQuery.trim();
    if (!prompt) {
      setNotice({ kind: "error", text: "Введите текстовый запрос для CLAP" });
      return;
    }
    appendActivity("info", "CLAP text search запущен", prompt);
    await run(
      () =>
        api.textSearch({
          query: prompt,
          limit: filters.limit,
          min_similarity: filters.minSimilarity,
          device: analysisDevice
        }),
      (value) => {
        setResults(value);
        appendActivity("ok", "CLAP text search завершен", `Найдено: ${value.length}`);
        return `Найдено: ${value.length}`;
      }
    );
  }

  async function handleCancelAnalyze() {
    if (!analysisJob) return;
    await run(
      () => cancelAnalysisJob(analysisJob),
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
      if (analysisJob.adapter_name === "sonara") {
        await handleSonaraAnalyze();
        return;
      }
      if (analysisJob.adapter_name === "maest") {
        await handleGenreAnalyze();
        return;
      }
      await handleAnalyze((["mert", "clap", "fake"].includes(analysisJob.adapter_name) ? analysisJob.adapter_name : "mert") as AnalysisAdapter);
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

  function adjustScanWorkers(delta: number) {
    setScanWorkers((current) => Math.min(maxScanWorkers, Math.max(1, current + delta)));
  }

  async function handleGenreTagsApply(trackIds = maestGenreTrackIds) {
    const ids = trackIds.filter((id) => tracks.some((track) => track.id === id && track.genres?.length));
    if (!ids.length) {
      setNotice({ kind: "error", text: "Нет MAEST жанров для записи" });
      return;
    }
    appendActivity("warn", "Запись жанров запущена", `${ids.length} треков · standard Genre`);
    await run(() => api.genreTagApply(ids), (value) => {
      appendActivity("ok", "Жанры записаны", `${value.length} треков · Genre overwritten`);
      return `Жанры записаны: ${value.length}`;
    });
  }

  function adjustAnalysisBatchSize(delta: number) {
    setAnalysisBatchSize((current) => Math.min(maxAnalysisBatchSize, Math.max(1, current + delta)));
  }

  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <h1>DJ Track Similarity</h1>
          <span className="meta">{tracks.length} {trackCountLabel(tracks.length)}</span>
        </div>
        <div className={`notice ${notice.kind}`}>{notice.text}</div>
      </header>

      <section className="workspace">
        <aside className="panel library-panel">
          <div className="panel-title">
            <FolderOpen size={18} />
            <h2>1. База и анализ</h2>
            <div className="panel-title-actions">
              <button className="secondary-mini" disabled={busy || stageRunning || !tracks.length} title={helpText.refreshTags} onClick={() => void handleRefreshTags()}>
                <Tags size={14} />
                RefreshTags
              </button>
              <button className="icon-button stop-button database-clear-button" disabled={busy || stageRunning || !tracks.length} title={helpText.clearDatabase} aria-label="Удалить все данные из базы" onClick={() => void handleClearDatabase()}>
                <Trash2 size={15} />
              </button>
            </div>
          </div>
          <div className="path-row library-path-row">
            <input value={musicRoot} onChange={(event) => setMusicRoot(event.target.value)} placeholder="D:/Music" title={helpText.musicRoot} />
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
          <div className="analysis-section-title">
            <span>Анализ моделей</span>
            <small>Запуск отдельных алгоритмов для текущей базы</small>
          </div>
          <div className="analysis-actions">
            <AnalysisButton label="SONARA" icon={<Gauge size={16} />} disabled={busy || stageRunning} title={helpText.sonaraAnalyze} onRun={() => void handleSonaraAnalyze()} onReset={() => void handleResetAnalysis("sonara")} />
            <AnalysisButton label="MAEST" icon={<Tags size={16} />} disabled={busy || stageRunning} title={helpText.maestAnalyze} onRun={() => void handleGenreAnalyze()} onReset={() => void handleResetAnalysis("maest")} />
            <AnalysisButton label="MERT" icon={<Wand2 size={16} />} disabled={busy || stageRunning} title={helpText.mertAnalyze} onRun={() => void handleAnalyze("mert")} onReset={() => void handleResetAnalysis("mert")} />
            <AnalysisButton label="CLAP" icon={<Search size={16} />} disabled={busy || stageRunning} title={helpText.clapAnalyze} onRun={() => void handleAnalyze("clap")} onReset={() => void handleResetAnalysis("clap")} />
          </div>
          <button className="secondary-mini genre-write-button" disabled={busy || stageRunning || !maestGenreTrackIds.length} title={helpText.writeMaestGenres} onClick={() => void handleGenreTagsApply()}>
            <Save size={14} />
            Сохранить жанры
          </button>
          <label className="analysis-limit" title={helpText.analyzeLimit}>
            Analyze limit
            <input type="number" min={0} max={100000} value={analysisLimit} title={helpText.analyzeLimit} onChange={(event) => setAnalysisLimit(Number(event.target.value))} />
            <small>0 = вся библиотека</small>
          </label>
          <div className="worker-control" title={helpText.scanWorkers}>
            <span>Scan workers</span>
            <div className="stepper">
              <button className="icon-button" disabled={busy || scanWorkers <= 1} onClick={() => adjustScanWorkers(-1)} aria-label="Уменьшить количество потоков сканирования"><Minus size={15} /></button>
              <input type="number" min={1} max={maxScanWorkers} value={scanWorkers} title={helpText.scanWorkers} onChange={(event) => setScanWorkers(Math.min(maxScanWorkers, Math.max(1, Number(event.target.value) || 1)))} />
              <button className="icon-button" disabled={busy || scanWorkers >= maxScanWorkers} onClick={() => adjustScanWorkers(1)} aria-label="Увеличить количество потоков сканирования"><Plus size={15} /></button>
            </div>
            <small>Для чтения метаданных: 1-{maxScanWorkers}</small>
          </div>
          <div className="analysis-device" title={helpText.analysisDevice}>
            <span><Cpu size={15} /> Device</span>
            <div className="segmented">
              {(["auto", "cpu", "cuda"] as DeviceMode[]).map((device) => (
                <button
                  key={device}
                  className={analysisDevice === device ? "active" : ""}
                  disabled={busy || stageRunning}
                  title={helpText.analysisDevice}
                  onClick={() => setAnalysisDevice(device)}
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
              <input type="number" min={1} max={maxAnalysisBatchSize} value={analysisBatchSize} title={helpText.analysisBatchSize} onChange={(event) => setAnalysisBatchSize(Math.min(maxAnalysisBatchSize, Math.max(1, Number(event.target.value) || 1)))} />
              <button className="icon-button" disabled={busy || analysisBatchSize >= maxAnalysisBatchSize} onClick={() => adjustAnalysisBatchSize(1)} aria-label="Увеличить batch size"><Plus size={15} /></button>
            </div>
            <small>CPU: 1-4; CUDA: начни с 4-8 и повышай осторожно.</small>
            <button className="secondary-mini" disabled={busy || stageRunning} onClick={() => void handleAnalyze("fake")}>
              <Gauge size={14} />
              Smoke
            </button>
          </div>
          <TabbedLog
            activeTab={logTab}
            onTabChange={setLogTab}
            processKind={processLogKind}
            scanJob={scanJob}
            analysisJob={analysisJob}
            events={activityLog}
          />
        </aside>

        <section className="panel track-panel">
          <div className="panel-title">
            <ListMusic size={18} />
            <h2>2. Библиотека и прослушивание</h2>
          </div>
          <div className="search-input">
            <Search size={16} />
            <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="artist, title, path" title={helpText.librarySearch} />
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
            onDetails={setMetadataTrack}
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
          <div className="mert-mode-note">
            Seed search использует MERT. Text search использует CLAP и требует отдельного CLAP-анализа библиотеки.
          </div>
          <div className="text-search-box">
            <label title={helpText.textPrompt}>
              Text query
              <input
                value={textQuery}
                onChange={(event) => setTextQuery(event.target.value)}
                placeholder="dark hypnotic techno, rolling bass, no vocals"
                title={helpText.textPrompt}
              />
            </label>
            <button disabled={busy || !textQuery.trim()} onClick={() => void handleTextSearch()}>
              <Search size={16} />
              Text
            </button>
          </div>
          <div className="filters">
            <label className="disabled-filter" title={helpText.disabledBpm}><span>BPM ±</span><input type="number" disabled value={filters.bpmTolerance} min={0} max={32} title={helpText.disabledBpm} onChange={(event) => setFilters({ ...filters, bpmTolerance: Number(event.target.value) })} /></label>
            <label title={helpText.similarity}>Similarity<input type="number" value={filters.minSimilarity} min={0} max={1} step={0.01} title={helpText.similarity} onChange={(event) => setFilters({ ...filters, minSimilarity: Number(event.target.value) })} /></label>
            <label className="disabled-filter" title={helpText.disabledEpsilon}><span>Epsilon</span><input type="number" disabled value={filters.epsilon} min={0} max={1} step={0.01} title={helpText.disabledEpsilon} onChange={(event) => setFilters({ ...filters, epsilon: Number(event.target.value) })} /></label>
            <label className="disabled-filter" title={helpText.disabledNoise}><span>Noise</span><input type="number" disabled value={filters.noise} min={0} max={1} step={0.01} title={helpText.disabledNoise} onChange={(event) => setFilters({ ...filters, noise: Number(event.target.value) })} /></label>
            <label title={helpText.lookback}>Lookback<input type="number" value={filters.lookback} min={0} max={12} title={helpText.lookback} onChange={(event) => setFilters({ ...filters, lookback: Number(event.target.value) })} /></label>
            <label className="disabled-filter" title={helpText.disabledEnergy}><span>Energy min</span><input type="number" disabled value={filters.energyMin} min={0} max={1} step={0.01} title={helpText.disabledEnergy} onChange={(event) => setFilters({ ...filters, energyMin: Number(event.target.value) })} /></label>
            <label className="disabled-filter" title={helpText.disabledEnergy}><span>Energy max</span><input type="number" disabled value={filters.energyMax} min={0} max={1} step={0.01} title={helpText.disabledEnergy} onChange={(event) => setFilters({ ...filters, energyMax: Number(event.target.value) })} /></label>
            <label title={helpText.limit}>Limit<input type="number" value={filters.limit} min={1} max={500} title={helpText.limit} onChange={(event) => setFilters({ ...filters, limit: Number(event.target.value) })} /></label>
            <label className="toggle disabled-filter" title={helpText.disabledKey}><input type="checkbox" disabled checked={filters.keyCompatibility} onChange={(event) => setFilters({ ...filters, keyCompatibility: event.target.checked })} />Key</label>
            <label className="toggle disabled-filter" title={helpText.disabledEnergy}><input type="checkbox" disabled checked={filters.energyEnabled} onChange={(event) => setFilters({ ...filters, energyEnabled: event.target.checked })} />Energy</label>
          </div>
          <button className="primary" disabled={busy || !seeds.length} onClick={() => void handleSearch()}>
            <Search size={17} />
            Seed search
          </button>
          <div className="results-list">
            {results.map(({ track, score }) => (
              <ResultRow
                key={track.id}
                track={track}
                score={score}
                isSeed={seedSet.has(track.id)}
                inPlaylist={playlistSet.has(track.id)}
                onSeed={addSeed}
                onTogglePlaylist={togglePlaylist}
                onPreview={setPreview}
                onDetails={setMetadataTrack}
              />
            ))}
          </div>
          </section>
          <section className="playlist-section">
          <div className="panel-title">
            <ListMusic size={18} />
            <h2>Сет и экспорт</h2>
            <span className="panel-counter">{playlist.length}</span>
          </div>
          <input value={playlistName} onChange={(event) => setPlaylistName(event.target.value)} title={helpText.playlistName} />
          <span className={`save-state ${playlistId ? "saved" : "dirty"}`}>
            {playlistId ? `Сохранен #${playlistId}` : playlist.length ? "Есть несохраненные изменения" : "Сет пуст"}
          </span>
          <div className="playlist-list">
            {playlist.length === 0 ? (
              <div className="empty-state">
                Сет пуст
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
                  <button className="icon-button" title="Теги и жанры" aria-label={`Теги ${displayTrack(track)}`} onClick={() => setMetadataTrack(track)}><Tags size={15} /></button>
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
            <input value={outputDir} onChange={(event) => setOutputDir(event.target.value)} placeholder="D:/Exports" title={helpText.outputDir} />
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
      {metadataTrack && <TrackMetadataDialog track={metadataTrack} busy={busy || stageRunning} onWriteGenres={(track) => void handleGenreTagsApply([track.id])} onClose={() => setMetadataTrack(null)} />}
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

function TabbedLog({
  activeTab,
  onTabChange,
  processKind,
  scanJob,
  analysisJob,
  events
}: {
  activeTab: "journal" | "process";
  onTabChange: (tab: "journal" | "process") => void;
  processKind: "scan" | "analysis";
  scanJob: ScanStats | null;
  analysisJob: AnalysisJobStatus | null;
  events: ActivityEvent[];
}) {
  return (
    <section className="log-panel">
      <div className="log-tabs" role="tablist" aria-label="Журналы процесса">
        <button
          className={activeTab === "journal" ? "active" : ""}
          role="tab"
          aria-selected={activeTab === "journal"}
          onClick={() => onTabChange("journal")}
        >
          Журнал
          <span>{events.length}</span>
        </button>
        <button
          className={activeTab === "process" ? "active" : ""}
          role="tab"
          aria-selected={activeTab === "process"}
          onClick={() => onTabChange("process")}
        >
          Лог
          <span>{processEventCount(processKind, scanJob, analysisJob)}</span>
        </button>
      </div>
      <div className="log-tab-body">
        {activeTab === "journal" ? (
          <ActivityLog events={events} />
        ) : (
          <ProcessLog kind={processKind} scanJob={scanJob} analysisJob={analysisJob} />
        )}
      </div>
    </section>
  );
}

function processEventCount(kind: "scan" | "analysis", scanJob: ScanStats | null, analysisJob: AnalysisJobStatus | null) {
  if (kind === "analysis") return analysisJob?.events.length || 0;
  return scanJob?.events?.length || 0;
}

function analysisJobRequest(job: AnalysisJobStatus) {
  if (job.adapter_name === "sonara") return api.sonaraJob(job.job_id);
  if (job.adapter_name === "maest") return api.genreJob(job.job_id);
  return api.analyzeJob(job.job_id);
}

function cancelAnalysisJob(job: AnalysisJobStatus) {
  if (job.adapter_name === "sonara") return api.cancelSonaraJob(job.job_id);
  if (job.adapter_name === "maest") return api.cancelGenreJob(job.job_id);
  return api.cancelAnalyzeJob(job.job_id);
}

function AnalysisButton({
  label,
  icon,
  disabled,
  title,
  onRun,
  onReset
}: {
  label: string;
  icon: ReactNode;
  disabled: boolean;
  title?: string;
  onRun: () => void;
  onReset: () => void;
}) {
  return (
    <div className="analysis-button-pair">
      <button className="primary" disabled={disabled} title={title} onClick={onRun}>
        {icon}
        {label}
      </button>
      <button className="analysis-reset" disabled={disabled} title={`Reset ${label}`} aria-label={`Reset ${label}`} onClick={onReset}>
        Reset
        <Trash2 size={14} />
      </button>
    </div>
  );
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
      {job.avg_seconds_per_track != null && <span className="analysis-muted">{job.avg_seconds_per_track.toFixed(2)} s/file{etaSeconds ? ` · ETA ${formatEta(etaSeconds)}` : ""}</span>}
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

function analysisRuntimeLabel(job: AnalysisJobStatus) {
  const model = job.model_name || job.adapter_name;
  if (job.adapter_name === "fake") return `${model} · smoke`;
  return `${model} · ${job.device || `${job.device_requested} pending`}`;
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
        <span>{analysisRuntimeLabel(job)}</span>
      </div>
      <progress max={job.total || 1} value={job.processed} />
      <div className="process-grid">
        <span>{job.processed}/{job.total}</span>
        <span>ok {job.analyzed}</span>
        <span>fail {job.failed}</span>
        {job.skipped ? <span>skip {job.skipped}</span> : null}
        <span>batch {job.batch_size || job.workers || 1}</span>
        <span>{percent}%</span>
      </div>
      {job.avg_seconds_per_track != null && <span className="analysis-muted">{job.avg_seconds_per_track.toFixed(2)} s/track{etaSeconds ? ` · ETA ${formatEta(etaSeconds)}` : ""}</span>}
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
  onPreview,
  onDetails
}: {
  tracks: Track[];
  seedSet: Set<number>;
  playlistSet: Set<number>;
  onSeed: (track: Track) => void;
  onTogglePlaylist: (track: Track) => void;
  onPreview: (track: Track) => void;
  onDetails: (track: Track) => void;
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
          <button className="icon-button" title="Теги и жанры" aria-label={`Теги ${displayTrack(track)}`} onClick={() => onDetails(track)}><Tags size={15} /></button>
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
  isSeed,
  inPlaylist,
  onSeed,
  onTogglePlaylist,
  onPreview,
  onDetails
}: {
  track: Track;
  score: number;
  isSeed: boolean;
  inPlaylist: boolean;
  onSeed: (track: Track) => void;
  onTogglePlaylist: (track: Track) => void;
  onPreview: (track: Track) => void;
  onDetails: (track: Track) => void;
}) {
  return (
    <div className="result-row">
      <button className="icon-button" title="Preview" aria-label={`Preview ${displayTrack(track)}`} onClick={() => onPreview(track)}><Play size={15} /></button>
      <div className="track-copy">
        <strong>{displayTrack(track)}</strong>
        <span>{trackInfo(track)}</span>
      </div>
      <button className="icon-button" title="Теги и жанры" aria-label={`Теги ${displayTrack(track)}`} onClick={() => onDetails(track)}><Tags size={15} /></button>
      <meter min={0} max={1} value={Math.max(0, Math.min(1, score))} />
      <span className="score">{score.toFixed(3)}</span>
      <button className={`icon-button ${isSeed ? "active" : ""}`} title="Seed" aria-label={`Seed ${displayTrack(track)}`} onClick={() => onSeed(track)}><Search size={15} /></button>
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
  return analysisStatusLabel(track);
}

function trackCountLabel(count: number) {
  const lastTwo = count % 100;
  const last = count % 10;
  if (lastTwo >= 11 && lastTwo <= 14) return "треков";
  if (last === 1) return "трек";
  if (last >= 2 && last <= 4) return "трека";
  return "треков";
}

function analysisStatusLabel(track: Track) {
  const analyses = new Set(track.analyses || []);
  if (track.genres?.length) analyses.add("maest");
  if (track.embedding_model) analyses.add("mert");
  const labels = [
    analyses.has("sonara") ? "sonara" : null,
    analyses.has("maest") ? "maest" : null,
    analyses.has("mert") ? "mert" : null,
    analyses.has("clap") ? "clap" : null
  ].filter(Boolean);
  return labels.length ? labels.join(" ") : "";
}

const trackTagLabels: Record<string, string> = {
  artist: "Artist",
  album: "Album",
  genre: "Genre",
  year: "Year",
  country: "Country",
  label: "Label",
  catalog_number: "Catalog",
  track_number: "Track no.",
  disc_number: "Disc no.",
  bpm: "BPM tag",
  key: "Key tag",
  comment: "Comment",
  isrc: "ISRC"
};

const trackTagOrder = [
  "artist",
  "album",
  "genre",
  "year",
  "country",
  "label",
  "catalog_number",
  "track_number",
  "disc_number",
  "bpm",
  "key",
  "comment",
  "isrc"
];

function readablePrimaryTrackInfo(track: Track) {
  const metadata = (track.metadata && typeof track.metadata === "object" && !Array.isArray(track.metadata)
    ? track.metadata
    : {}) as Record<string, unknown>;
  const audioFormat = displayAudioFormat(metadata.audio_format, track.path);
  const audioCodec = formatTagValue(metadata.audio_codec);
  const formatAndCodec = formatAudioFormat(audioFormat, audioCodec);
  return [
    ["Title", track.title || String(metadata.title || basename(track.path))],
    ["Audio Length", typeof track.duration === "number" ? formatPlayerDuration(track.duration) : "-"],
    ["Audio Format", formatAndCodec],
    ["File Size", formatFileSizeMb(track.size)],
    ["File Path", track.path]
  ] as const;
}

function readableTrackTags(raw: Track["metadata"]) {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return [];
  const record = raw as Record<string, unknown>;
  return trackTagOrder
    .filter((key) => record[key] != null && record[key] !== "")
    .map((key) => [trackTagLabels[key] || key, record[key]] as const);
}

function TrackMetadataDialog({
  track,
  busy,
  onWriteGenres,
  onClose
}: {
  track: Track;
  busy: boolean;
  onWriteGenres: (track: Track) => void;
  onClose: () => void;
}) {
  const genres = track.genres || [];
  const scores = track.genre_scores || {};
  const sonaraFeatures = readableSonaraFeatures(track.metadata?.sonara_features);
  const primaryEntries = readablePrimaryTrackInfo(track);
  const metadataEntries = readableTrackTags(track.metadata);
  return (
    <div className="modal-backdrop" role="presentation" onClick={onClose}>
      <section className="metadata-dialog" role="dialog" aria-modal="true" aria-label="Теги трека" onClick={(event) => event.stopPropagation()}>
        <div className="dialog-title">
          <div>
            <h2>Теги и жанры</h2>
            <span>{basename(track.path)}</span>
          </div>
          <button className="icon-button" title="Закрыть" aria-label="Закрыть" onClick={onClose}><X size={15} /></button>
        </div>
        <strong className="metadata-track-title">{displayTrack(track)}</strong>
        {primaryEntries.length || metadataEntries.length ? (
          <dl className="metadata-grid tag-grid mutagen-grid">
            {primaryEntries.map(([key, value]) => (
              <Fragment key={key}><dt>{key}</dt><dd>{value}</dd></Fragment>
            ))}
            {metadataEntries.map(([key, value]) => (
              <Fragment key={key}><dt>{key}</dt><dd>{formatTagValue(value)}</dd></Fragment>
            ))}
          </dl>
        ) : (
          <span className="empty-genres">Mutagen не нашел сохраненных тегов</span>
        )}
        <div className="sonara-block">
          <strong>SONARA features</strong>
          {sonaraFeatures.length ? (
            <>
              <dl className="metadata-grid tag-grid">
                {sonaraFeatures.map((feature) => (
                  <Fragment key={feature.key}><dt title={feature.description}>{feature.label}</dt><dd title={feature.description}>{feature.value}</dd></Fragment>
                ))}
              </dl>
            </>
          ) : (
            <span className="empty-genres">SONARA признаки ещё не извлечены</span>
          )}
        </div>
        <div className="genre-block">
          <div className="genre-block-title">
            <strong>MAEST genres</strong>
            <button className="secondary-mini" disabled={busy || !genres.length} title="Перезаписать стандартный Genre тег этого файла жанрами MAEST" onClick={() => onWriteGenres(track)}>
              <Save size={13} />
              Save
            </button>
          </div>
          {genres.length ? (
            <div className="genre-list">
              {genres.map((genre) => (
                <span className="genre-pill" key={genre}>{formatGenreLabel(genre)} <b>{formatConfidence(scores[genre])}</b></span>
              ))}
            </div>
          ) : (
            <span className="empty-genres">Жанры ещё не извлечены</span>
          )}
        </div>
      </section>
    </div>
  );
}

const sonaraFeatureLabels: Record<string, string> = {
  duration_sec: "Duration",
  duration_player: "Length",
  bpm: "BPM",
  camelot_key: "Musical Key",
  key: "Key",
  key_confidence: "Key confidence",
  energy: "Energy",
  danceability: "Danceability",
  valence: "Valence",
  acousticness: "Acousticness",
  loudness_lufs: "Loudness",
  dynamic_range_db: "Dynamic range",
  predominant_chord: "Predominant chord",
  chord_change_rate: "Chord changes",
  dissonance: "Dissonance",
  onset_density: "Onset density",
  beats: "Beats",
  n_beats: "Beat count",
  onset_frames: "Onsets",
  spectral_centroid_mean: "Brightness",
  spectral_bandwidth_mean: "Bandwidth",
  spectral_rolloff_mean: "Rolloff",
  spectral_flatness_mean: "Flatness",
  spectral_contrast_mean: "Contrast",
  zero_crossing_rate: "ZCR",
  mfcc_mean: "MFCC mean",
  chroma_mean: "Chroma mean",
  chord_sequence: "Chord sequence",
  analysis_seconds: "Analysis seconds",
  total_seconds: "Total analysis seconds",
  decode_path: "Decode path",
  requested_feature_count: "Feature count"
};

const tonalFeatureKeys = new Set([
  "key",
  "key_confidence",
  "key_detection",
  "detect_key",
  "predominant_key",
  "predominant_chord",
  "chord_sequence",
  "chord_change_rate",
  "chord_descriptors",
  "chords_from_beats",
  "chords_from_frames",
  "chroma_mean",
  "chroma_stft",
  "hpcp",
  "dissonance",
  "estimate_tuning",
  "pitch_tuning",
  "salience"
]);

const sonaraFeaturePriority: Record<string, number> = {
  duration_player: 0,
  duration_sec: 1,
  bpm: 2,
  camelot_key: 3,
  energy: 4,
  danceability: 5,
  valence: 6,
  acousticness: 7,
  loudness_lufs: 8,
  dynamic_range_db: 9,
  onset_density: 10,
  n_beats: 11,
  beats: 12,
  onset_frames: 13,
  zero_crossing_rate: 14,
  spectral_centroid_mean: 15,
  spectral_bandwidth_mean: 16,
  spectral_rolloff_mean: 17,
  spectral_flatness_mean: 18,
  key: 100,
  key_confidence: 101,
  key_detection: 102,
  detect_key: 103,
  predominant_key: 104,
  predominant_chord: 105,
  chord_sequence: 106,
  chord_change_rate: 107,
  chord_descriptors: 108,
  chords_from_beats: 109,
  chords_from_frames: 110,
  chroma_mean: 111,
  chroma_stft: 112,
  hpcp: 113,
  dissonance: 114,
  estimate_tuning: 115,
  pitch_tuning: 116,
  salience: 117,
  spectral_contrast_mean: 201,
  mfcc_mean: 202,
  decode_path: 203,
  analysis_seconds: 204,
  total_seconds: 205,
  requested_feature_count: 206
};

function readableSonaraFeatures(raw: unknown) {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return [];
  const record = raw as Record<string, unknown>;
  const entries = Object.entries(record);
  const durationSeconds = sonaraFeatureNumber(record.duration_sec);
  if (durationSeconds != null) {
    entries.push([
      "duration_player",
      {
        value: durationSeconds,
        type: "duration",
        description: "Track duration formatted like a music player."
      }
    ]);
  }
  return entries
    .filter(([key]) => key !== "tempo")
    .map(([key, payload]) => {
      const record = payload && typeof payload === "object" && !Array.isArray(payload) ? payload as Record<string, unknown> : {};
      return {
        key,
        label: sonaraFeatureLabels[key] || formatFeatureLabel(key),
        value: formatSonaraValue(record),
        description: typeof record.description === "string" ? record.description : "",
        sortGroup: sonaraFeatureSortGroup(key, record),
        valueGroup: sonaraFeatureValueGroup(record),
        priority: sonaraFeaturePriority[key] ?? 100
      };
    })
    .sort((left, right) => left.sortGroup - right.sortGroup || left.valueGroup - right.valueGroup || left.priority - right.priority || left.label.localeCompare(right.label));
}

function formatFeatureLabel(key: string) {
  return key
    .replace(/_/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/^./, (letter) => letter.toUpperCase());
}

function formatSonaraValue(record: Record<string, unknown>) {
  const value = record.value;
  if (record.type === "unavailable") return "-";
  if (record.type === "duration" && typeof value === "number") return formatPlayerDuration(value);
  if (record.type === "ndarray" || record.storage) {
    const shape = Array.isArray(record.shape) ? record.shape.join("x") : "";
    const summary = record.summary && typeof record.summary === "object" ? record.summary as Record<string, unknown> : null;
    const mean = typeof summary?.mean === "number" ? ` mean ${formatNumber(summary.mean)}` : "";
    return `${shape || record.size || "array"}${mean}`;
  }
  if (typeof value === "number") {
    return formatNumber(value);
  }
  if (Array.isArray(value)) return `${value.length} values`;
  if (value == null) return "-";
  return String(value);
}

function sonaraFeatureValueGroup(record: Record<string, unknown>) {
  if (Array.isArray(record.value)) return 1;
  return record.type === "unavailable" || record.value == null ? 2 : 0;
}

function sonaraFeatureSortGroup(key: string, record: Record<string, unknown>) {
  if (key === "duration_player" || key === "duration_sec" || key === "bpm" || key === "camelot_key") return 0;
  if (tonalFeatureKeys.has(key)) return 2;
  return sonaraFeatureValueGroup(record) === 2 ? 3 : 1;
}

function sonaraFeatureNumber(payload: unknown) {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) return null;
  const value = (payload as Record<string, unknown>).value;
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function formatNumber(value: number) {
  if (Math.abs(value) >= 100) return value.toFixed(1);
  return value.toFixed(3).replace(/0+$/, "").replace(/\.$/, "");
}

function formatTagValue(value: unknown) {
  if (Array.isArray(value)) return value.map((item) => String(item)).join(", ");
  if (value == null) return "-";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function displayAudioFormat(value: unknown, path: string) {
  const stored = formatTagValue(value);
  if (stored && stored !== "-") {
    if (stored.toLowerCase().startsWith("audio/")) return audioFormatFromPath(path) || stored.replace(/^audio\//i, "").toUpperCase();
    return stored;
  }
  return audioFormatFromPath(path) || "-";
}

function audioFormatFromPath(path: string) {
  const extension = path.split(".").pop()?.toLowerCase();
  const formats: Record<string, string> = {
    aif: "AIFF",
    aiff: "AIFF",
    alac: "ALAC",
    flac: "FLAC",
    m4a: "M4A",
    mp3: "MP3",
    ogg: "Ogg",
    opus: "Opus",
    wav: "Wave",
    wave: "Wave"
  };
  return extension ? formats[extension] : undefined;
}

function formatAudioFormat(audioFormat: string, audioCodec: string) {
  if (!audioCodec || audioCodec === "-") return audioFormat || "-";
  if (!audioFormat || audioFormat === "-") return audioCodec;
  const normalizedFormat = normalizeAudioFormatPart(audioFormat);
  const normalizedCodec = normalizeAudioFormatPart(audioCodec);
  if (normalizedFormat && normalizedFormat === normalizedCodec) return audioFormat;
  return `${audioFormat} / ${audioCodec}`;
}

function normalizeAudioFormatPart(value: string) {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, "");
}

function formatFileSizeMb(bytes: number) {
  if (!Number.isFinite(bytes) || bytes <= 0) return "-";
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`;
}

function formatConfidence(value: number | undefined) {
  if (value == null) return "0%";
  return `${Math.round(value * 100)}%`;
}

function formatGenreLabel(label: string) {
  return label.replace(/^Electronic---/i, "");
}

function formatDuration(seconds: number) {
  const minutes = Math.floor(seconds / 60);
  const rest = Math.round(seconds % 60).toString().padStart(2, "0");
  return `${minutes}:${rest}`;
}

function formatPlayerDuration(seconds: number) {
  const rounded = Math.max(0, Math.round(seconds));
  const hours = Math.floor(rounded / 3600);
  const minutes = Math.floor((rounded % 3600) / 60);
  const rest = (rounded % 60).toString().padStart(2, "0");
  if (hours > 0) return `${hours}:${minutes.toString().padStart(2, "0")}:${rest}`;
  return `${minutes}:${rest}`;
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
