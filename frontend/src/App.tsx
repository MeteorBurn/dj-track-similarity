import type { MouseEvent } from "react";
import { useEffect, useMemo, useState } from "react";
import { Moon, ScrollText, Sun } from "lucide-react";
import { AnalysisJobStatus, AnalysisModel, api, GenreTagJobStatus, LibrarySummary, PromotedClassifier, ScanStats, SearchResult, Track } from "./api";
import type { ConfirmationRequest } from "./confirmation";
import { ConfirmationDialog, LogFrameDialog } from "./dialogs";
import { exportDirectoryError } from "./exportView";
import { helpText } from "./helpText";
import { ActivityEvent, analysisJobRequest, cancelAnalysisJob, scanSummary } from "./jobUi";
import { LibraryPanel } from "./LibraryPanel";
import {
  appendVisibleTracksToPlaylist,
  libraryCurrentPageNumber,
  libraryPageOffsetForNumber,
  libraryPageSize,
  orderedLibraryTracks,
  toggleLikedTracksFilter,
  type LibraryPreset,
  type LibrarySortDirection
} from "./libraryView";
import { SearchPlaylistPanel } from "./SearchPlaylistPanel";
import { TrackMetadataDialog } from "./TrackMetadataDialog";
import { TrackPanel } from "./TrackPanel";
import { displayTrack } from "./trackDisplay";
import { applyTheme, resolveInitialTheme, themeStorageKey, type ThemeMode } from "./theme";
import { TooltipLayer, useGlobalTooltip } from "./tooltipLayer";

type Notice = { kind: "ok" | "error" | "idle"; text: string };
type DeviceMode = "auto" | "cpu" | "cuda";
type ResetAdapter = AnalysisModel;

const defaultNotice: Notice = { kind: "idle", text: "Готово к работе" };
const emptySummary: LibrarySummary = { tracks: 0, sonara: 0, maest: 0, mert: 0, clap: 0, liked: 0, classifiers: 0 };
const analysisModelOrder: AnalysisModel[] = ["sonara", "maest", "mert", "clap"];

function optimalWorkerLimit() {
  const cores = typeof navigator === "undefined" ? 4 : navigator.hardwareConcurrency || 4;
  return Math.max(1, Math.min(8, Math.floor(cores / 2) || 1));
}

function activeClassifierMinScores(scores: Record<string, number>) {
  return Object.fromEntries(Object.entries(scores).filter(([, value]) => value > 0));
}

function openDocumentationWindow(event: MouseEvent<HTMLAnchorElement>) {
  const opened = window.open("/docs/", "_blank", "noopener,noreferrer");
  if (opened) event.preventDefault();
}

export function App() {
  const tooltip = useGlobalTooltip();
  const [tracks, setTracks] = useState<Track[]>([]);
  const [libraryTotal, setLibraryTotal] = useState(0);
  const [libraryOffset, setLibraryOffset] = useState(0);
  const [libraryLoading, setLibraryLoading] = useState(false);
  const [librarySummary, setLibrarySummary] = useState<LibrarySummary>(emptySummary);
  const [query, setQuery] = useState("");
  const [libraryPreset, setLibraryPreset] = useState<LibraryPreset>("all");
  const [librarySortDirection, setLibrarySortDirection] = useState<LibrarySortDirection>("forward");
  const [likedOnly, setLikedOnly] = useState(false);
  const [classifiers, setClassifiers] = useState<PromotedClassifier[]>([]);
  const [classifierMinScores, setClassifierMinScores] = useState<Record<string, number>>({});
  const [databasePath, setDatabasePath] = useState<string | null>(null);
  const [musicRoot, setMusicRoot] = useState("");
  const [textQuery, setTextQuery] = useState("");
  const [outputDir, setOutputDir] = useState("");
  const [seeds, setSeeds] = useState<number[]>([]);
  const [results, setResults] = useState<SearchResult[]>([]);
  const [playlist, setPlaylist] = useState<Track[]>([]);
  const [playlistName, setPlaylistName] = useState("seamless-set");
  const [preview, setPreview] = useState<Track | null>(null);
  const [metadataTrack, setMetadataTrack] = useState<Track | null>(null);
  const [seedTrackMap, setSeedTrackMap] = useState<Record<number, Track>>({});
  const [analysisJob, setAnalysisJob] = useState<AnalysisJobStatus | null>(null);
  const [scanJob, setScanJob] = useState<ScanStats | null>(null);
  const [genreTagJob, setGenreTagJob] = useState<GenreTagJobStatus | null>(null);
  const [processLogKind, setProcessLogKind] = useState<"scan" | "analysis" | "genre_tags">("scan");
  const [analysisLimit, setAnalysisLimit] = useState(0);
  const [scanWorkers, setScanWorkers] = useState(4);
  const [analysisTrackBatchSize, setAnalysisTrackBatchSize] = useState(6);
  const [analysisInferenceBatchSize, setAnalysisInferenceBatchSize] = useState(24);
  const [analysisDevice, setAnalysisDevice] = useState<DeviceMode>("auto");
  const [selectedAnalysisModels, setSelectedAnalysisModels] = useState<AnalysisModel[]>(analysisModelOrder);
  const [notice, setNotice] = useState<Notice>(defaultNotice);
  const [logFrameOpen, setLogFrameOpen] = useState(false);
  const [theme, setTheme] = useState<ThemeMode>(() => resolveInitialTheme());
  const [confirmation, setConfirmation] = useState<ConfirmationRequest | null>(null);
  const [activityLog, setActivityLog] = useState<ActivityEvent[]>([
    { id: 1, time: Date.now(), level: "info", message: "Интерфейс загружен" }
  ]);
  const [busy, setBusy] = useState(false);
  const [filters, setFilters] = useState({
    minSimilarity: 0,
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
  const orderedTracks = useMemo(() => orderedLibraryTracks(tracks, librarySortDirection), [tracks, librarySortDirection]);
  const seedTracks = useMemo(() => seeds.map((id) => seedTrackMap[id]).filter(Boolean) as Track[], [seeds, seedTrackMap]);
  const scanRunning = Boolean(scanJob?.state && ["queued", "running"].includes(scanJob.state));
  const analysisRunning = Boolean(analysisJob && ["queued", "running"].includes(analysisJob.state));
  const genreTagRunning = Boolean(genreTagJob && ["queued", "running"].includes(genreTagJob.state));
  const stageRunning = scanRunning || analysisRunning || genreTagRunning;
  const hasTracks = librarySummary.tracks > 0;
  const logHasErrors = useMemo(() => {
    const hasErrorEvent = activityLog.some((event) => event.level === "error")
      || (scanJob?.events || []).some((event) => event.level === "error")
      || (analysisJob?.events || []).some((event) => event.level === "error")
      || (genreTagJob?.events || []).some((event) => event.level === "error");
    return hasErrorEvent || Boolean(analysisJob?.errors.length) || Boolean(genreTagJob?.errors.length);
  }, [activityLog, analysisJob, genreTagJob, scanJob]);
  const canGoBack = libraryOffset > 0 && !libraryLoading;
  const canGoForward = libraryOffset + tracks.length < libraryTotal && !libraryLoading;
  const canStartScan = Boolean(databasePath && musicRoot);
  const maxScanWorkers = useMemo(() => optimalWorkerLimit(), []);
  const maxAnalysisTrackBatchSize = 64;
  const maxAnalysisInferenceBatchSize = 128;

  useEffect(() => {
    void initializeDatabase();
  }, []);

  useEffect(() => {
    applyTheme(theme);
    try {
      localStorage.setItem(themeStorageKey, theme);
    } catch {
      // Theme persistence is optional; keep the UI usable if storage is blocked.
    }
  }, [theme]);

  useEffect(() => {
    if (!databasePath) return;
    const timer = window.setTimeout(() => {
      void refreshLibrary(0);
    }, 250);
    return () => window.clearTimeout(timer);
  }, [query, libraryPreset, likedOnly, classifierMinScores, databasePath]);

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

  useEffect(() => {
    if (!genreTagJob || !["queued", "running"].includes(genreTagJob.state)) return;
    const timer = window.setInterval(() => {
      void api.genreTagJob(genreTagJob.job_id).then((job) => {
        setGenreTagJob(job);
        if (["completed", "cancelled", "failed"].includes(job.state)) {
          void refreshLibrary();
          if (job.state === "completed") {
            appendActivity("ok", "Запись жанров завершена", genreTagJobSummary(job));
          }
          if (job.state === "cancelled") {
            appendActivity("warn", "Запись жанров остановлена", genreTagJobSummary(job));
          }
        }
      }).catch((error) => {
        setNotice({ kind: "error", text: error instanceof Error ? error.message : String(error) });
      });
    }, 1200);
    return () => window.clearInterval(timer);
  }, [genreTagJob?.job_id, genreTagJob?.state]);

  async function initializeDatabase() {
    try {
      const promotedClassifiers = await api.classifiers();
      setClassifiers(promotedClassifiers);
      setClassifierMinScores((current) => {
        const keys = new Set(promotedClassifiers.map((classifier) => classifier.classifier_key));
        return Object.fromEntries(Object.entries(current).filter(([key]) => keys.has(key)));
      });
      const current = await api.currentDatabase();
      setDatabasePath(current.path);
      setMusicRoot(current.music_root || "");
      if (!current.selected) {
        resetDatabaseScopedState();
        setNotice({ kind: "idle", text: "Выберите SQLite базу данных" });
        return;
      }
      await refreshLibrary(0, true);
      await loadLatestJobs(promotedClassifiers);
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      setNotice({ kind: "error", text: message });
      appendActivity("error", "Не удалось прочитать текущую базу", message);
    }
  }

  async function loadLatestJobs(promotedClassifiers = classifiers) {
    await Promise.all([
      api.latestScanJob().then((job) => {
        if (job) {
          setScanJob(job);
          setProcessLogKind("scan");
        }
      }).catch(() => undefined),
      api.latestAnalysisJob().then((job) => {
        if (job) {
          setAnalysisJob(job);
          if (["queued", "running"].includes(job.state)) setProcessLogKind("analysis");
        }
      }).catch(() => undefined),
      ...promotedClassifiers.map((classifier) =>
        api.latestClassifierJob(classifier.classifier_key).then((job) => {
          if (job) {
            setAnalysisJob((current) => (current && ["queued", "running"].includes(current.state) ? current : job));
            if (["queued", "running"].includes(job.state)) setProcessLogKind("analysis");
          }
        }).catch(() => undefined)
      ),
      api.genreTagJobLatest().then((job) => {
        if (job) {
          setGenreTagJob(job);
          if (["queued", "running"].includes(job.state)) setProcessLogKind("genre_tags");
        }
      }).catch(() => undefined)
    ]);
  }

  function resetDatabaseScopedState() {
    setTracks([]);
    setLibraryTotal(0);
    setLibraryOffset(0);
    setLibrarySummary(emptySummary);
    setMusicRoot("");
    setSeeds([]);
    setResults([]);
    setPlaylist([]);
    setPreview(null);
    setMetadataTrack(null);
    setSeedTrackMap({});
    setScanJob(null);
    setAnalysisJob(null);
    setGenreTagJob(null);
  }

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

  function requestConfirmation(request: ConfirmationRequest) {
    setConfirmation(request);
  }

  function confirmPendingAction() {
    const pending = confirmation;
    if (!pending) return;
    setConfirmation(null);
    void pending.onConfirm();
  }

  async function refreshLibrary(nextOffset = libraryOffset, databaseSelected = Boolean(databasePath)) {
    if (!databaseSelected) {
      setTracks([]);
      setLibraryTotal(0);
      setLibraryOffset(0);
      setLibrarySummary(emptySummary);
      return;
    }
    setLibraryLoading(true);
    try {
      const [page, summary] = await Promise.all([
        api.tracks({
          query,
          preset: libraryPreset,
          liked: likedOnly,
          classifierMinScores: activeClassifierMinScores(classifierMinScores),
          limit: libraryPageSize,
          offset: nextOffset
        }),
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
    const currentPage = libraryCurrentPageNumber(libraryTotal, libraryOffset, libraryPageSize);
    const nextOffset = libraryPageOffsetForNumber(currentPage + delta, libraryTotal, libraryPageSize);
    void refreshLibrary(nextOffset);
  }

  function jumpToLibraryPage(pageNumber: number) {
    const nextOffset = libraryPageOffsetForNumber(pageNumber, libraryTotal, libraryPageSize);
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
    setPlaylist((current) => (current.some((item) => item.id === track.id) ? current : [...current, track]));
  }

  function removeFromPlaylist(trackId: number) {
    const removed = playlist.find((track) => track.id === trackId);
    if (removed) {
      appendActivity("warn", "Убран из сета", displayTrack(removed));
    }
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

  function toggleLikedOnly() {
    setLikedOnly((current) => toggleLikedTracksFilter(current));
  }

  function toggleAnalysisModel(model: AnalysisModel) {
    setSelectedAnalysisModels((current) => {
      const next = current.includes(model)
        ? current.filter((item) => item !== model)
        : [...current, model];
      return analysisModelOrder.filter((item) => next.includes(item));
    });
  }

  function toggleLibrarySortDirection() {
    setLibrarySortDirection((current) => (current === "forward" ? "reverse" : "forward"));
  }

  async function addVisibleTracksToPlaylist() {
    if (!databasePath || libraryLoading) return;
    setBusy(true);
    try {
      const filtered = await api.filteredTracks({
        query,
        preset: libraryPreset,
        liked: likedOnly,
        classifierMinScores: activeClassifierMinScores(classifierMinScores)
      });
      const matchingTracks = filtered.items;
      const nextPlaylist = appendVisibleTracksToPlaylist(playlist, matchingTracks);
      const added = nextPlaylist.length - playlist.length;
      if (!added) {
        setNotice({ kind: "idle", text: "Все отфильтрованные треки уже в сете" });
        return;
      }
      setPlaylist(nextPlaylist);
      appendActivity("ok", "Отфильтрованная библиотека добавлена в сет", `${added} новых · всего найдено ${filtered.total}`);
      setNotice({ kind: "ok", text: `Добавлено в сет: ${added}` });
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      setNotice({ kind: "error", text: message });
      appendActivity("error", "Не удалось добавить треки в сет", message);
    } finally {
      setBusy(false);
    }
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

  const pairedClassifierKeys = ["break_energy", "live_instrumentation"];

  async function handleClassifierAnalyze() {
    const available = classifiers.filter((classifier) => pairedClassifierKeys.includes(classifier.classifier_key));
    if (!available.length) {
      setNotice({ kind: "error", text: "Нет promoted classifiers для Break Energy / Live Instrumentation" });
      return;
    }
    const limit = analysisLimit > 0 ? analysisLimit : undefined;
    appendActivity("info", "CLASS analysis запущен", available.map((classifier) => classifier.name).join(" + "));
    setProcessLogKind("analysis");
    setAnalysisJob(null);
    await run(
      () => Promise.all(available.map((classifier) => api.analyzeClassifier(classifier.classifier_key, limit))),
      (jobs) => {
        const job = jobs[jobs.length - 1];
        setAnalysisJob(job);
        appendActivity("ok", "CLASS jobs созданы", jobs.map((item) => `${item.adapter_name} ${item.job_id.slice(0, 8)} · ${item.total}`).join(" · "));
        return `CLASS jobs: ${jobs.length}`;
      }
    );
  }

  async function handleResetClassifiers() {
    const available = classifiers.filter((classifier) => pairedClassifierKeys.includes(classifier.classifier_key));
    if (!available.length) {
      setNotice({ kind: "error", text: "Нет classifier scores для сброса" });
      return;
    }
    appendActivity("warn", "CLASS reset запущен", "Удаляем только classifier scores из SQLite");
    await run(
      () => api.resetClassifiers(available.map((classifier) => classifier.classifier_key)),
      (result) => {
        void refreshLibrary();
        appendActivity("ok", "CLASS reset завершен", `scores ${result.scores_deleted}`);
        return `CLASS: удалено scores ${result.scores_deleted}`;
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

  async function handleChooseDatabase() {
    setBusy(true);
    try {
      const value = await api.chooseDatabase();
      if (!value.selected || !value.path) {
        appendActivity("info", "Выбор базы отменен");
        setNotice({ kind: "idle", text: "Выбор базы отменен" });
        return;
      }
      setDatabasePath(value.path);
      resetDatabaseScopedState();
      setMusicRoot(value.music_root || "");
      await refreshLibrary(0, true);
      await loadLatestJobs();
      appendActivity("ok", "База выбрана", value.path);
      setNotice({ kind: "ok", text: value.path });
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      setNotice({ kind: "error", text: message });
      appendActivity("error", "Не удалось переключить базу", message);
    } finally {
      setBusy(false);
    }
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

  async function handleAnalyzeSelected() {
    if (!selectedAnalysisModels.length) {
      setNotice({ kind: "error", text: "Выберите хотя бы одну модель анализа" });
      return;
    }
    const limit = analysisLimit > 0 ? analysisLimit : undefined;
    const models = [...selectedAnalysisModels];
    const labels = models.map((model) => model.toUpperCase()).join(", ");
    const detail = `${labels} · ${analysisDevice.toUpperCase()} · tracks ${analysisTrackBatchSize} · inference ${analysisInferenceBatchSize} · ${limit ? `limit ${limit}` : "вся библиотека"}`;
    appendActivity("info", "Анализ выбранных моделей запущен", detail);
    setProcessLogKind("analysis");
    setAnalysisJob(null);
    await run(
      () => api.analysisJobStart({
        models,
        limit: limit ?? null,
        device: analysisDevice,
        top_k: 3,
        track_batch_size: analysisTrackBatchSize,
        inference_batch_size: analysisInferenceBatchSize
      }),
      (job) => {
        setAnalysisJob(job);
        appendActivity("ok", "Analysis job создан", `${job.job_id.slice(0, 8)} · ${job.total} треков · tracks ${job.track_batch_size} · inference ${job.inference_batch_size}`);
        return `Analysis job ${job.job_id.slice(0, 8)}: ${job.total} треков`;
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
    appendActivity("warn", "Очистка базы запущена", "Удаляем только данные SQLite, аудиофайлы не трогаем");
    await run(
      () => api.clearDatabase(),
      (value) => {
        setTracks([]);
        setSeeds([]);
        setResults([]);
        setPlaylist([]);
        setPreview(null);
        setMetadataTrack(null);
        setScanJob(null);
        setAnalysisJob(null);
        const detail = `${value.tracks_deleted} треков · ${value.embeddings_deleted} эмбеддингов`;
        appendActivity("ok", "База очищена", detail);
        return detail;
      }
    );
  }

  async function handleResetAnalysis(adapter: ResetAdapter) {
    const label = adapter.toUpperCase();
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

  async function handleCancelGenreTags() {
    if (!genreTagJob) return;
    await run(
      () => api.cancelGenreTagJob(genreTagJob.job_id),
      (job) => {
        setGenreTagJob(job);
        appendActivity("warn", "Genre tag cancel requested", job.job_id.slice(0, 8));
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
      return;
    }
    if (genreTagRunning) {
      await handleCancelGenreTags();
    }
  }

  async function handleExport(format: "m3u" | "csv") {
    if (!playlist.length) {
      setNotice({ kind: "error", text: "Сет пуст" });
      return;
    }
    const pathError = exportDirectoryError(outputDir);
    if (pathError) {
      setNotice({ kind: "error", text: pathError });
      appendActivity("error", "Экспорт не запущен", pathError);
      return;
    }
    await run(() => api.exportPlaylist(playlistName || "seamless-set", playlist.map((track) => track.id), outputDir.trim(), format), (value) => {
      appendActivity("ok", `Экспорт ${format.toUpperCase()}`, value.path);
      return value.path;
    });
  }

  function adjustScanWorkers(delta: number) {
    setScanWorkers((current) => Math.min(maxScanWorkers, Math.max(1, current + delta)));
  }

  async function handleGenreTagsApply() {
    if (!librarySummary.maest) {
      setNotice({ kind: "error", text: "Нет MAEST жанров для записи" });
      return;
    }
    const targetText = `${librarySummary.maest} MAEST треков`;
    appendActivity("warn", "Запись жанров в теги файлов запущена", `${targetText} · standard Genre`);
    setProcessLogKind("genre_tags");
    setGenreTagJob(null);
    await run(() => api.genreTagJobStart(), (job) => {
      setGenreTagJob(job);
      appendActivity("ok", "Genre tag job создан", `${job.job_id.slice(0, 8)} · ${job.total} треков`);
      return `Genre tag job ${job.job_id.slice(0, 8)}: ${job.total} треков`;
    });
  }

  async function handleToggleTrackLiked(track: Track) {
    const nextLiked = !track.liked;
    try {
      const updated = await api.setTrackLiked(track.id, nextLiked);
      setTracks((current) => {
        if (likedOnly && !updated.liked) return current.filter((item) => item.id !== updated.id);
        return current.map((item) => (item.id === updated.id ? { ...item, liked: updated.liked } : item));
      });
      setPlaylist((current) => current.map((item) => (item.id === updated.id ? { ...item, liked: updated.liked } : item)));
      setResults((current) => current.map((item) => (
        item.track.id === updated.id ? { ...item, track: { ...item.track, liked: updated.liked } } : item
      )));
      setSeedTrackMap((current) => (
        current[updated.id] ? { ...current, [updated.id]: { ...current[updated.id], liked: updated.liked } } : current
      ));
      setLibrarySummary((current) => ({
        ...current,
        liked: Math.max(0, current.liked + (updated.liked ? 1 : -1))
      }));
      setLibraryTotal((current) => (likedOnly && !updated.liked ? Math.max(0, current - 1) : current));
      appendActivity(updated.liked ? "ok" : "warn", updated.liked ? "Трек лайкнут" : "Лайк снят", displayTrack(updated));
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      setNotice({ kind: "error", text: message });
      appendActivity("error", "Не удалось изменить лайк", message);
    }
  }

  function adjustAnalysisTrackBatchSize(delta: number) {
    setAnalysisTrackBatchSize((current) => Math.min(maxAnalysisTrackBatchSize, Math.max(1, current + delta)));
  }

  function adjustAnalysisInferenceBatchSize(delta: number) {
    setAnalysisInferenceBatchSize((current) => Math.min(maxAnalysisInferenceBatchSize, Math.max(1, current + delta)));
  }

  function toggleTheme() {
    setTheme((current) => current === "dark" ? "light" : "dark");
  }

  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <h1>
            <a href="/docs/" target="_blank" rel="noreferrer" title="Открыть HTML документацию" onClick={openDocumentationWindow}>
              DJ Track Similarity
            </a>
          </h1>
          <div className="meta" aria-label="Library analysis summary">
            <span className="meta-badge meta-badge-total"><span>tracks</span><strong>{librarySummary.tracks}</strong></span>
            <span className="meta-badge"><span>sonara</span><strong>{librarySummary.sonara}</strong></span>
            <span className="meta-badge"><span>maest</span><strong>{librarySummary.maest}</strong></span>
            <span className="meta-badge"><span>mert</span><strong>{librarySummary.mert}</strong></span>
            <span className="meta-badge"><span>clap</span><strong>{librarySummary.clap}</strong></span>
            <span className="meta-badge"><span>class</span><strong>{librarySummary.classifiers}</strong></span>
          </div>
        </div>
        <div className="topbar-actions">
          <button
            className="icon-button theme-toggle-button"
            title="Переключить тему"
            aria-label="Переключить тему"
            aria-pressed={theme === "dark"}
            onClick={toggleTheme}
            type="button"
          >
            {theme === "dark" ? <Sun size={16} /> : <Moon size={16} />}
          </button>
          <button
            className={`icon-button log-frame-button ${logFrameOpen ? "active" : ""} ${logHasErrors ? "has-errors" : ""}`}
            title="Открыть лог"
            aria-label="Открыть лог"
            aria-pressed={logFrameOpen}
            onClick={() => setLogFrameOpen(true)}
            type="button"
          >
            <ScrollText size={16} />
          </button>
          <div className={`notice ${notice.kind}`}>{notice.text}</div>
        </div>
      </header>

      <section className="workspace">
        <LibraryPanel
          databasePath={databasePath}
          onChooseDatabase={() => void handleChooseDatabase()}
          musicRoot={musicRoot}
          onMusicRootChange={setMusicRoot}
          busy={busy}
          stageRunning={stageRunning}
          canStartScan={canStartScan}
          hasTracks={hasTracks}
          maestGenreTrackCount={librarySummary.maest}
          scanWorkers={scanWorkers}
          maxScanWorkers={maxScanWorkers}
          adjustScanWorkers={adjustScanWorkers}
          onScanWorkersChange={setScanWorkers}
          analysisLimit={analysisLimit}
          onAnalysisLimitChange={setAnalysisLimit}
          analysisDevice={analysisDevice}
          onAnalysisDeviceChange={setAnalysisDevice}
          analysisTrackBatchSize={analysisTrackBatchSize}
          maxAnalysisTrackBatchSize={maxAnalysisTrackBatchSize}
          adjustAnalysisTrackBatchSize={adjustAnalysisTrackBatchSize}
          onAnalysisTrackBatchSizeChange={setAnalysisTrackBatchSize}
          analysisInferenceBatchSize={analysisInferenceBatchSize}
          maxAnalysisInferenceBatchSize={maxAnalysisInferenceBatchSize}
          adjustAnalysisInferenceBatchSize={adjustAnalysisInferenceBatchSize}
          onAnalysisInferenceBatchSizeChange={setAnalysisInferenceBatchSize}
          scanJob={scanJob}
          analysisJob={analysisJob}
          helpText={helpText}
          onStopActiveStage={() => void handleStopActiveStage()}
          onChooseFolder={() => void handleChooseFolder()}
          onScan={() => void handleScan()}
          onRefreshTags={() => void handleRefreshTags()}
          onWriteMaestGenres={() => void handleGenreTagsApply()}
          onClearDatabase={() => requestConfirmation({
            title: "Очистить базу?",
            message: "Удалить все данные из SQLite базы: треки, анализы, эмбеддинги и текущий сет? Аудиофайлы на диске останутся.",
            onConfirm: () => handleClearDatabase()
          })}
          selectedAnalysisModels={selectedAnalysisModels}
          onToggleAnalysisModel={toggleAnalysisModel}
          onAnalyzeSelected={() => void handleAnalyzeSelected()}
          onResetAnalysis={(adapter) => requestConfirmation({
            title: `Сбросить ${adapter.toUpperCase()}?`,
            message: `Сбросить результаты ${adapter.toUpperCase()}? Аудиофайлы не трогаем, остальные алгоритмы останутся.`,
            onConfirm: () => handleResetAnalysis(adapter)
          })}
        />

        <TrackPanel
          query={query}
          onQueryChange={setQuery}
          libraryPreset={libraryPreset}
          onToggleLibraryPreset={toggleLibraryPreset}
          likedOnly={likedOnly}
          likedTrackCount={librarySummary.liked}
          onToggleLikedOnly={toggleLikedOnly}
          librarySortDirection={librarySortDirection}
          onToggleLibrarySortDirection={toggleLibrarySortDirection}
          preview={preview}
          tracks={orderedTracks}
          total={libraryTotal}
          offset={libraryOffset}
          loading={libraryLoading}
          canGoBack={canGoBack}
          canGoForward={canGoForward}
          onPreviousPage={() => changeLibraryPage(-1)}
          onNextPage={() => changeLibraryPage(1)}
          onPageJump={jumpToLibraryPage}
          busy={busy || stageRunning || !databasePath}
          seedSet={seedSet}
          playlistSet={playlistSet}
          librarySearchHelp={helpText.librarySearch}
          onAddVisibleTracks={() => void addVisibleTracksToPlaylist()}
          onSeed={addSeed}
          onToggleLiked={(track) => void handleToggleTrackLiked(track)}
          onTogglePlaylist={togglePlaylist}
          onPreview={setPreview}
          onDetails={(track) => void handleTrackDetails(track)}
        />

        <SearchPlaylistPanel
          seedTracks={seedTracks}
          textQuery={textQuery}
          onTextQueryChange={setTextQuery}
          busy={busy || !databasePath}
          filters={filters}
          setFilters={setFilters}
          seeds={seeds}
          results={results}
          seedSet={seedSet}
          playlistSet={playlistSet}
          playlist={playlist}
          playlistName={playlistName}
          onPlaylistNameChange={setPlaylistName}
          outputDir={outputDir}
          onOutputDirChange={setOutputDir}
          onChooseOutputFolder={() => void handleChooseOutputFolder()}
          helpText={helpText}
          classifiers={classifiers}
          classifierMinScores={classifierMinScores}
          onClassifierMinScoreChange={(classifier, value) =>
            setClassifierMinScores((current) => ({ ...current, [classifier]: value }))
          }
          classifierJob={classifiers.some((classifier) => classifier.classifier_key === analysisJob?.adapter_name) ? analysisJob : null}
          removeSeed={removeSeed}
          handleTextSearch={() => void handleTextSearch()}
          handleSonaraSearch={() => void handleSonaraSearch()}
          handleMertSearch={() => void handleMertSearch()}
          handleClassifierAnalyze={() => void handleClassifierAnalyze()}
          handleResetClassifiers={() => requestConfirmation({
            title: "Сбросить CLASS?",
            message: "Удалить сохраненные данные Break Energy и Live Instrumentation? Аудиофайлы не трогаем.",
            onConfirm: () => handleResetClassifiers()
          })}
          addSeed={addSeed}
          togglePlaylist={togglePlaylist}
          setPreview={setPreview}
          setMetadataTrack={(track) => void handleTrackDetails(track)}
          removeFromPlaylist={removeFromPlaylist}
          handleExport={(format) => void handleExport(format)}
        />
      </section>
      {metadataTrack && <TrackMetadataDialog track={metadataTrack} onClose={() => setMetadataTrack(null)} />}
      {confirmation && (
        <ConfirmationDialog
          request={confirmation}
          onConfirm={confirmPendingAction}
          onCancel={() => setConfirmation(null)}
        />
      )}
      {logFrameOpen && (
        <LogFrameDialog
          processLogKind={processLogKind}
          scanJob={scanJob}
          analysisJob={analysisJob}
          genreTagJob={genreTagJob}
          activityLog={activityLog}
          onClose={() => setLogFrameOpen(false)}
        />
      )}
      <TooltipLayer tooltip={tooltip} />
    </main>
  );
}

function genreTagJobSummary(job: GenreTagJobStatus) {
  return `записано ${job.applied} · пропущено ${job.skipped} · ошибок ${job.failed} · всего ${job.total}`;
}
