import { useEffect, useMemo, useState } from "react";
import { AnalysisJobStatus, api, LibrarySummary, ScanStats, SearchResult, Track } from "./api";
import { exportDirectoryError } from "./exportView";
import { ActivityEvent, analysisJobRequest, cancelAnalysisJob, scanSummary } from "./jobUi";
import { LibraryPanel } from "./LibraryPanel";
import { appendVisibleTracksToPlaylist, LibraryPreset } from "./libraryView";
import { SearchPlaylistPanel } from "./SearchPlaylistPanel";
import { TrackMetadataDialog } from "./TrackMetadataDialog";
import { TrackPanel } from "./TrackPanel";
import { basename, displayTrack, trackCountLabel, trackHasAnalysis } from "./trackDisplay";

type Notice = { kind: "ok" | "error" | "idle"; text: string };
type DeviceMode = "auto" | "cpu" | "cuda";
type AnalysisAdapter = "mert" | "clap" | "fake";
type ResetAdapter = "sonara" | "maest" | "mert" | "clap" | "fake";

const defaultNotice: Notice = { kind: "idle", text: "Готово к работе" };
const libraryPageSize = 200;
const emptySummary: LibrarySummary = { tracks: 0, sonara: 0, maest: 0, mert: 0, clap: 0 };

const helpText = {
  musicRoot: "Папка с музыкой. Формат: путь Windows или POSIX, например D:/Music. Тип: строка. Папка должна существовать.",
  analyzeLimit: "Сколько треков анализировать. Тип: целое число 0-100000. 0 = вся библиотека.",
  scanWorkers: "Параллельное чтение метаданных при сканировании. Тип: целое число. Диапазон зависит от CPU, обычно 1-8.",
  refreshTags: "Перечитать только file tags через Mutagen для уже найденных треков. Пути, Sonara, MAEST, MERT и CLAP не трогаются.",
  clearDatabase: "Удалить все записи из SQLite: треки, эмбеддинги, анализы, плейлисты и сет. Аудиофайлы на диске не трогаются.",
  analysisDevice: "Устройство для MERT/CLAP. Значения: AUTO, CPU, CUDA. AUTO выберет CUDA, если PyTorch видит GPU, иначе CPU.",
  sonaraAnalyze: "SONARA считает BPM, key и музыкальные признаки. Нужна для базового описания трека и будущих DJ-фильтров. Параллельность берется из Embedding batch size.",
  maestAnalyze: "MAEST определяет жанровые метки. Нужна для жанровой навигации и проверки характера библиотеки. Batch берется из Embedding batch size.",
  writeMaestGenres: "Перезаписать стандартный Genre/TCON/©gen в аудиофайлах жанрами MAEST. Плееры вроде AIMP будут видеть эти жанры.",
  mertAnalyze: "MERT строит аудио-эмбеддинги. Нужна для поиска похожих треков от выбранных seed-треков.",
  clapAnalyze: "CLAP строит music-focused аудио-эмбеддинги для поиска по текстовому описанию звучания.",
  analysisBatchSize: "Для SONARA это число параллельных track workers. Для MAEST/MERT/CLAP это inference batch. Тип: целое число 1-16.",
  librarySearch: "Фильтр библиотеки. Формат: текст. Ищет по artist, title, album, path, MAEST genres и syncopated rhythm.",
  similarity: "Минимальный similarity. Тип: число с точкой, диапазон 0.00-1.00.",
  sonaraMixerTimbre: "Вес тембра и спектральной фактуры: MFCC, centroid, bandwidth, rolloff, flatness, contrast. Повышай для похожего материала звука.",
  sonaraMixerRhythm: "Вес ритмической текстуры: onset density, zero crossing, danceability, chord movement. Повышай для кликов, ломанности и микро-грува.",
  sonaraMixerDynamics: "Вес динамики: energy, RMS, LUFS, dynamic range. Повышай для похожего давления, дыхания и громкости.",
  sonaraMixerHarmonic: "Вес гармонического цвета: chroma, dissonance, chord change, key confidence. Повышай для похожего аккордового ощущения.",
  sonaraMixerTempo: "Вес BPM compatibility с half/double-tempo логикой. Повышай для более удобных DJ-переходов, снижай для свободного поиска.",
  sonaraModifierEnergy: "Направление energy относительно seed/lookback: ниже = спокойнее, выше = активнее. 0 не тянет выдачу.",
  sonaraModifierValence: "Направление valence относительно seed/lookback: ниже = темнее/меланхоличнее, выше = светлее. Это не preset, а числовой bias.",
  sonaraModifierAcousticness: "Направление acousticness: ниже = электроннее, выше = органичнее/живее по Sonara.",
  sonaraModifierBrightness: "Направление spectral centroid: ниже = мягче/темнее по спектру, выше = ярче.",
  sonaraModifierRhythmDensity: "Направление onset density: ниже = меньше событий, выше = плотнее клики/перкуссия.",
  sonaraModifierDynamicRange: "Направление dynamic range: ниже = ровнее/плотнее, выше = больше дыхания и перепадов.",
  sonaraModifierLoudness: "Направление LUFS: ниже = тише/дальше, выше = громче/ближе.",
  textPrompt: "CLAP search. Лучше писать на английском одно связное описание звучания: genre/scene, rhythm/drums, bass, texture, instruments, mood/space, vocals/no vocals. Не полагайся только на абстрактное настроение без слышимых признаков.",
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
  const [libraryTotal, setLibraryTotal] = useState(0);
  const [libraryOffset, setLibraryOffset] = useState(0);
  const [libraryLoading, setLibraryLoading] = useState(false);
  const [librarySummary, setLibrarySummary] = useState<LibrarySummary>(emptySummary);
  const [query, setQuery] = useState("");
  const [libraryPreset, setLibraryPreset] = useState<LibraryPreset>("all");
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
  const [seedTrackMap, setSeedTrackMap] = useState<Record<number, Track>>({});
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
    limit: 5,
    sonaraMixer: {
      timbre: 1,
      rhythm: 1,
      dynamics: 0.8,
      harmonic: 0.8,
      tempo: 0.35
    },
    sonaraModifiers: {
      energy: 0,
      valence: 0,
      acousticness: 0,
      brightness: 0,
      rhythm_density: 0,
      dynamic_range: 0,
      loudness: 0
    }
  });

  const seedSet = useMemo(() => new Set(seeds), [seeds]);
  const playlistSet = useMemo(() => new Set(playlist.map((track) => track.id)), [playlist]);
  const seedTracks = useMemo(() => seeds.map((id) => seedTrackMap[id]).filter(Boolean) as Track[], [seeds, seedTrackMap]);
  const visibleMaestGenreTrackIds = useMemo(() => tracks.filter((track) => track.genres?.length).map((track) => track.id), [tracks]);
  const scanRunning = Boolean(scanJob?.state && ["queued", "running"].includes(scanJob.state));
  const analysisRunning = Boolean(analysisJob && ["queued", "running"].includes(analysisJob.state));
  const stageRunning = scanRunning || analysisRunning;
  const hasTracks = librarySummary.tracks > 0;
  const canGoBack = libraryOffset > 0 && !libraryLoading;
  const canGoForward = libraryOffset + tracks.length < libraryTotal && !libraryLoading;
  const canStartScan = Boolean(musicRoot);
  const maxScanWorkers = useMemo(() => optimalWorkerLimit(), []);
  const maxAnalysisBatchSize = 16;

  useEffect(() => {
    void refreshLibrary(0);
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
    const timer = window.setTimeout(() => {
      void refreshLibrary(0);
    }, 250);
    return () => window.clearTimeout(timer);
  }, [query, libraryPreset]);

  useEffect(() => {
    if (!scanJob?.job_id || !["queued", "running"].includes(scanJob.state || "")) return;
    const timer = window.setInterval(() => {
      void api.scanJob(scanJob.job_id!).then((job) => {
        setScanJob(job);
        if (["completed", "cancelled", "failed"].includes(job.state || "")) {
          void refreshLibrary();
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
          void refreshLibrary();
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
      await refreshLibrary();
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

  function appendActivities(events: Array<{ level: ActivityEvent["level"]; message: string; detail?: string }>) {
    const now = Date.now();
    setActivityLog((current) => [
      ...events.map((event, index) => ({ id: now + index + Math.random(), time: now, ...event })),
      ...current
    ].slice(0, 80));
  }

  async function refreshLibrary(nextOffset = libraryOffset) {
    setLibraryLoading(true);
    try {
      const [page, summary] = await Promise.all([
        api.tracks({ query, preset: libraryPreset, limit: libraryPageSize, offset: nextOffset }),
        api.librarySummary()
      ]);
      setTracks(page.items);
      setLibraryTotal(page.total);
      setLibraryOffset(page.offset);
      setLibrarySummary(summary);
    } finally {
      setLibraryLoading(false);
    }
  }

  function changeLibraryPage(delta: number) {
    const nextOffset = Math.max(0, libraryOffset + delta * libraryPageSize);
    void refreshLibrary(nextOffset);
  }

  async function handleTrackDetails(track: Track) {
    setMetadataTrack(track);
    try {
      const fullTrack = await api.track(track.id);
      setMetadataTrack(fullTrack);
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      setNotice({ kind: "error", text: message });
      appendActivity("error", "Не удалось загрузить теги трека", message);
    }
  }

  function addSeed(track: Track) {
    setSeedTrackMap((current) => ({ ...current, [track.id]: track }));
    setSeeds((current) => (current.includes(track.id) ? current : [...current, track.id]));
  }

  function removeSeed(trackId: number) {
    setSeedTrackMap((current) => {
      const next = { ...current };
      delete next[trackId];
      return next;
    });
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

  function toggleLibraryPreset(preset: LibraryPreset) {
    setLibraryPreset((current) => (current === preset ? "all" : preset));
  }

  function addVisibleTracksToPlaylist() {
    const nextPlaylist = appendVisibleTracksToPlaylist(playlist, tracks);
    const added = nextPlaylist.length - playlist.length;
    if (!added) {
      setNotice({ kind: "idle", text: "Все видимые треки уже в сете" });
      return;
    }
    setPlaylistId(null);
    setPlaylist(nextPlaylist);
    appendActivity("ok", "Текущая страница добавлена в сет", `${added} новых · на странице ${tracks.length}`);
    setNotice({ kind: "ok", text: `Добавлено в сет: ${added}` });
  }

  async function handleSonaraSearch() {
    if (!seeds.length) {
      setNotice({ kind: "error", text: "Выберите seed-треки" });
      return;
    }
    const lookbackTrackIds = filters.lookback > 0 ? playlist.slice(-filters.lookback).map((track) => track.id) : [];
    appendActivity("info", "SONARA search запущен", `custom mixer · ${seeds.length} seed · lookback ${lookbackTrackIds.length}`);
    await run(
      () =>
        api.sonaraSearch({
          seed_track_ids: seeds,
          lookback_track_ids: lookbackTrackIds,
          limit: filters.limit,
          mode: "custom",
          mixer_weights: filters.sonaraMixer,
          modifiers: filters.sonaraModifiers,
          min_similarity: filters.minSimilarity
        }),
      (value) => {
        setResults(value);
        appendActivity("ok", "SONARA search завершен", `Найдено: ${value.length}`);
        return `Найдено: ${value.length}`;
      }
    );
  }

  async function handleMertSearch() {
    if (!seeds.length) {
      setNotice({ kind: "error", text: "Выберите seed-треки" });
      return;
    }
    const lookbackTrackIds = filters.lookback > 0 ? playlist.slice(-filters.lookback).map((track) => track.id) : [];
    appendActivity("info", "MERT search запущен", `${seeds.length} seed · lookback ${lookbackTrackIds.length}`);
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
        appendActivity("ok", "MERT search завершен", `Найдено: ${value.length}`);
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

  async function handleChooseOutputFolder() {
    await run(
      () => api.chooseFolder(),
      (value) => {
        if (!value.path) {
          appendActivity("info", "Выбор папки экспорта отменен");
          return "Выбор папки экспорта отменен";
        }
        setOutputDir(value.path);
        appendActivity("ok", "Папка экспорта выбрана", value.path);
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
    const detail = `batch ${analysisBatchSize} · ${limit ? `limit ${limit}` : "вся библиотека"} · SQLite metadata`;
    appendActivity("info", "SONARA lab анализ запущен", detail);
    setProcessLogKind("analysis");
    setAnalysisJob(null);
    await run(
      () => api.analyzeSonara(limit, analysisBatchSize),
      (job) => {
        setAnalysisJob(job);
        appendActivity("ok", "SONARA job создан", `${job.job_id.slice(0, 8)} · ${job.total} треков · batch ${job.batch_size}`);
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
        void refreshLibrary();
        appendActivity("ok", `${label} reset завершен`, `tracks ${result.tracks_updated} · embeddings ${result.embeddings_deleted}`);
        return `${label}: очищено tracks ${result.tracks_updated}, embeddings ${result.embeddings_deleted}`;
      }
    );
  }

  async function handleGenreAnalyze() {
    const limit = analysisLimit > 0 ? analysisLimit : undefined;
    const detail = `${analysisDevice.toUpperCase()} · batch ${analysisBatchSize} · top 3 genres · ${limit ? `limit ${limit}` : "вся библиотека"}`;
    appendActivity("info", "MAEST анализ жанров запущен", detail);
    setProcessLogKind("analysis");
    setAnalysisJob(null);
    await run(
      () => api.analyzeGenres(limit, analysisDevice, 3, analysisBatchSize),
      (job) => {
        setAnalysisJob(job);
        appendActivity("ok", "MAEST job создан", `${job.job_id.slice(0, 8)} · ${job.total} треков · batch ${job.batch_size} · top 3`);
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
    appendActivity("info", "CLAP search запущен", prompt);
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
        appendActivity("ok", "CLAP search завершен", `Найдено: ${value.length}`);
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
    const pathError = exportDirectoryError(outputDir);
    if (pathError) {
      setNotice({ kind: "error", text: pathError });
      appendActivity("error", "Экспорт не запущен", pathError);
      return;
    }
    await run(() => api.exportPlaylist(playlistId, outputDir.trim(), format), (value) => {
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

  async function handleGenreTagsApply(trackIds = visibleMaestGenreTrackIds) {
    const ids = trackIds.filter((id) => tracks.some((track) => track.id === id && track.genres?.length));
    if (!ids.length) {
      setNotice({ kind: "error", text: "Нет MAEST жанров для записи" });
      return;
    }
    appendActivity("warn", "Запись жанров в теги файлов запущена", `${ids.length} треков · standard Genre`);
    await run(() => api.genreTagApply(ids), (value) => {
      appendActivities([
        {
          level: "ok" as const,
          message: "Жанры записаны в теги файлов",
          detail: `${value.length} треков · Genre overwritten`
        },
        ...value.map((preview) => ({
          level: "ok" as const,
          message: "Жанры записаны в файл",
          detail: genreWriteLogDetail(preview.path, preview.tags)
        }))
      ]);
      return `Жанры записаны в теги файлов: ${value.length}`;
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
          <span className="meta">
            {librarySummary.tracks} {trackCountLabel(librarySummary.tracks)}
            {" | sonara "}{librarySummary.sonara}
            {" | maest "}{librarySummary.maest}
            {" | mert "}{librarySummary.mert}
            {" | clap "}{librarySummary.clap}
          </span>
        </div>
        <div className={`notice ${notice.kind}`}>{notice.text}</div>
      </header>

      <section className="workspace">
        <LibraryPanel
          musicRoot={musicRoot}
          onMusicRootChange={setMusicRoot}
          busy={busy}
          stageRunning={stageRunning}
          canStartScan={canStartScan}
          hasTracks={hasTracks}
          scanWorkers={scanWorkers}
          maxScanWorkers={maxScanWorkers}
          adjustScanWorkers={adjustScanWorkers}
          onScanWorkersChange={setScanWorkers}
          analysisLimit={analysisLimit}
          onAnalysisLimitChange={setAnalysisLimit}
          analysisDevice={analysisDevice}
          onAnalysisDeviceChange={setAnalysisDevice}
          analysisBatchSize={analysisBatchSize}
          maxAnalysisBatchSize={maxAnalysisBatchSize}
          adjustAnalysisBatchSize={adjustAnalysisBatchSize}
          onAnalysisBatchSizeChange={setAnalysisBatchSize}
          maestGenreTrackCount={visibleMaestGenreTrackIds.length}
          logTab={logTab}
          onLogTabChange={setLogTab}
          processLogKind={processLogKind}
          scanJob={scanJob}
          analysisJob={analysisJob}
          activityLog={activityLog}
          helpText={helpText}
          onStopActiveStage={() => void handleStopActiveStage()}
          onChooseFolder={() => void handleChooseFolder()}
          onScan={() => void handleScan()}
          onRefreshTags={() => void handleRefreshTags()}
          onClearDatabase={() => void handleClearDatabase()}
          onSonaraAnalyze={() => void handleSonaraAnalyze()}
          onGenreAnalyze={() => void handleGenreAnalyze()}
          onAnalyze={(adapter) => void handleAnalyze(adapter)}
          onResetAnalysis={(adapter) => void handleResetAnalysis(adapter)}
          onWriteMaestGenres={() => void handleGenreTagsApply()}
        />

        <TrackPanel
          query={query}
          onQueryChange={setQuery}
          libraryPreset={libraryPreset}
          onToggleLibraryPreset={toggleLibraryPreset}
          preview={preview}
          tracks={tracks}
          total={libraryTotal}
          offset={libraryOffset}
          pageSize={libraryPageSize}
          loading={libraryLoading}
          canGoBack={canGoBack}
          canGoForward={canGoForward}
          onPreviousPage={() => changeLibraryPage(-1)}
          onNextPage={() => changeLibraryPage(1)}
          seedSet={seedSet}
          playlistSet={playlistSet}
          librarySearchHelp={helpText.librarySearch}
          onAddVisibleTracks={addVisibleTracksToPlaylist}
          onSeed={addSeed}
          onTogglePlaylist={togglePlaylist}
          onPreview={setPreview}
          onDetails={(track) => void handleTrackDetails(track)}
        />

        <SearchPlaylistPanel
          seedTracks={seedTracks}
          textQuery={textQuery}
          onTextQueryChange={setTextQuery}
          busy={busy}
          filters={filters}
          setFilters={setFilters}
          seeds={seeds}
          results={results}
          seedSet={seedSet}
          playlistSet={playlistSet}
          playlist={playlist}
          playlistName={playlistName}
          onPlaylistNameChange={setPlaylistName}
          playlistId={playlistId}
          outputDir={outputDir}
          onOutputDirChange={setOutputDir}
          onChooseOutputFolder={() => void handleChooseOutputFolder()}
          helpText={helpText}
          removeSeed={removeSeed}
          handleTextSearch={() => void handleTextSearch()}
          handleSonaraSearch={() => void handleSonaraSearch()}
          handleMertSearch={() => void handleMertSearch()}
          addSeed={addSeed}
          togglePlaylist={togglePlaylist}
          setPreview={setPreview}
          setMetadataTrack={(track) => void handleTrackDetails(track)}
          removeFromPlaylist={removeFromPlaylist}
          handleCreatePlaylist={() => void handleCreatePlaylist()}
          handleExport={(format) => void handleExport(format)}
          handleTags={(apply) => void handleTags(apply)}
        />
      </section>
      {metadataTrack && <TrackMetadataDialog track={metadataTrack} busy={busy || stageRunning} onWriteGenres={(track) => void handleGenreTagsApply([track.id])} onClose={() => setMetadataTrack(null)} />}
    </main>
  );
}

function genreWriteLogDetail(path: string, tags: Record<string, string>) {
  const tagEntries = Object.entries(tags);
  const tagText = tagEntries.length ? tagEntries.map(([key, value]) => `${key}: ${value}`).join(" · ") : "Genre tag skipped";
  return `${basename(path)} · ${tagText}`;
}
