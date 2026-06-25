import type { MouseEvent } from "react";
import { useEffect, useMemo, useState } from "react";
import { CopyX, FlaskConical, Moon, Power, RefreshCcw, ScrollText, Square, Sun } from "lucide-react";
import { AnalysisJobStatus, AnalysisModel, api, AudioDedupJobPayload, AudioDedupJobStatus, GenreTagJobStatus, PromotedClassifier, RhythmLabLaunchResult, ScanStats, SetBuilderGeneratePayload, Track } from "./api";
import { analysisSelectionOrder, isAudioAnalysisModel, type AnalysisSelection } from "./analysisSelection";
import { AudioDedupDialog } from "./AudioDedupDialog";
import { clapPromptPresets, defaultClapPromptPresetKey, promptQueriesFromText } from "./clapPrompt";
import { classifierScoringBlockedReason } from "./classifierCompatibility";
import type { ConfirmationRequest } from "./confirmation";
import { ConfirmationDialog, LogFrameDialog } from "./dialogs";
import { exportDirectoryError } from "./exportView";
import { helpText } from "./helpText";
import { analysisJobRequest, cancelAnalysisJob, scanSummary, stageIndicatorLabel } from "./jobUi";
import { LibraryPanel } from "./LibraryPanel";
import { appendVisibleTracksToPlaylist } from "./libraryView";
import { SearchPlaylistPanel } from "./SearchPlaylistPanel";
import { TrackMetadataDialog } from "./TrackMetadataDialog";
import { TrackPanel } from "./TrackPanel";
import { displayTrack } from "./trackDisplay";
import { applyTheme, resolveInitialTheme, themeStorageKey, type ThemeMode } from "./theme";
import { TooltipLayer, useGlobalTooltip } from "./tooltipLayer";
import { useActivityLog } from "./useActivityLog";
import { useLibraryState } from "./useLibraryState";
import { useSearchPlaylist } from "./useSearchPlaylist";

type Notice = { kind: "ok" | "error" | "idle"; text: string };
type DeviceMode = "auto" | "cpu" | "cuda";
type ResetAdapter = AnalysisModel;

const defaultNotice: Notice = { kind: "idle", text: "Готово к работе" };
const analysisModelOrder = analysisSelectionOrder;

function optimalWorkerLimit() {
  const cores = typeof navigator === "undefined" ? 4 : navigator.hardwareConcurrency || 4;
  return Math.max(1, Math.min(8, Math.floor(cores / 2) || 1));
}

function openDocumentationWindow(event: MouseEvent<HTMLAnchorElement>) {
  const opened = window.open("/docs/", "_blank", "noopener,noreferrer");
  if (opened) event.preventDefault();
}

function openRhythmLabWindow(result: RhythmLabLaunchResult, pendingWindow: Window | null) {
  if (pendingWindow) {
    pendingWindow.location.href = result.url;
    return pendingWindow;
  }
  return window.open(result.url, "_blank", "noopener,noreferrer");
}

export function App() {
  const tooltip = useGlobalTooltip();
  const [databasePath, setDatabasePath] = useState<string | null>(null);
  const { activityLog, appendActivity } = useActivityLog();
  const {
    libraryTotal,
    libraryOffset,
    libraryLoading,
    librarySummary,
    query,
    setQuery,
    searchMode,
    setSearchMode,
    libraryPreset,
    librarySortDirection,
    likedOnly,
    classifierMinScores,
    setClassifierMinScores,
    orderedTracks,
    hasTracks,
    canGoBack,
    canGoForward,
    refreshLibrary,
    resetLibraryState,
    changeLibraryPage,
    jumpToLibraryPage,
    toggleLibraryPreset,
    toggleLikedOnly,
    toggleLibrarySortDirection,
    filteredTracks,
    updateTrackLiked
  } = useLibraryState({ databaseSelected: Boolean(databasePath) });
  const {
    textQuery,
    setTextQuery,
    outputDir,
    setOutputDir,
    seeds,
    setSeeds,
    results,
    setResults,
    playlist,
    setPlaylist,
    playlistName,
    setPlaylistName,
    preview,
    playingTrackId,
    togglePreview,
    markPreviewPlaying,
    markPreviewPaused,
    metadataTrack,
    setMetadataTrack,
    setSeedTrackMap,
    seedSet,
    playlistSet,
    seedTracks,
    addSeed,
    removeSeed,
    removeFromPlaylist,
    togglePlaylist,
    resetSearchPlaylistState
  } = useSearchPlaylist({ onActivity: appendActivity });
  const [clapPresetKey, setClapPresetKey] = useState(defaultClapPromptPresetKey);
  const [clapAvoidQuery, setClapAvoidQuery] = useState("");
  const [classifiers, setClassifiers] = useState<PromotedClassifier[]>([]);
  const [musicRoot, setMusicRoot] = useState("");
  const [analysisJob, setAnalysisJob] = useState<AnalysisJobStatus | null>(null);
  const [audioDedupJob, setAudioDedupJob] = useState<AudioDedupJobStatus | null>(null);
  const [scanJob, setScanJob] = useState<ScanStats | null>(null);
  const [genreTagJob, setGenreTagJob] = useState<GenreTagJobStatus | null>(null);
  const [processLogKind, setProcessLogKind] = useState<"scan" | "analysis" | "genre_tags" | "audio_dedup">("scan");
  const [analysisLimit, setAnalysisLimit] = useState(0);
  const [scanWorkers, setScanWorkers] = useState(4);
  const [analysisTrackBatchSize, setAnalysisTrackBatchSize] = useState(4);
  const [analysisInferenceBatchSize, setAnalysisInferenceBatchSize] = useState(24);
  const [analysisDevice, setAnalysisDevice] = useState<DeviceMode>("auto");
  const [selectedAnalysisModels, setSelectedAnalysisModels] = useState<AnalysisSelection[]>(analysisModelOrder);
  const [notice, setNotice] = useState<Notice>(defaultNotice);
  const [logFrameOpen, setLogFrameOpen] = useState(false);
  const [audioDedupOpen, setAudioDedupOpen] = useState(false);
  const [theme, setTheme] = useState<ThemeMode>(() => resolveInitialTheme());
  const [confirmation, setConfirmation] = useState<ConfirmationRequest | null>(null);
  const [busy, setBusy] = useState(false);
  const [filters, setFilters] = useState({
    minSimilarity: 0,
    limit: 10,
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

  const scanRunning = Boolean(scanJob?.state && ["queued", "running"].includes(scanJob.state));
  const analysisRunning = Boolean(analysisJob && ["queued", "running"].includes(analysisJob.state));
  const genreTagRunning = Boolean(genreTagJob && ["queued", "running"].includes(genreTagJob.state));
  const audioDedupRunning = Boolean(audioDedupJob && ["queued", "running"].includes(audioDedupJob.state));
  const stageRunning = scanRunning || analysisRunning || genreTagRunning || audioDedupRunning;
  const logHasErrors = useMemo(() => {
    const hasErrorEvent = activityLog.some((event) => event.level === "error")
      || (scanJob?.events || []).some((event) => event.level === "error")
      || (analysisJob?.events || []).some((event) => event.level === "error")
      || (audioDedupJob?.events || []).some((event) => event.level === "error")
      || (genreTagJob?.events || []).some((event) => event.level === "error");
    return hasErrorEvent || Boolean(analysisJob?.errors.length) || Boolean(audioDedupJob?.errors.length) || Boolean(genreTagJob?.errors.length);
  }, [activityLog, analysisJob, audioDedupJob, genreTagJob, scanJob]);
  const canStartScan = Boolean(databasePath && musicRoot);
  const analysisModelCounts: Record<AnalysisSelection, number> = {
    sonara: librarySummary.sonara,
    maest: librarySummary.maest,
    mert: librarySummary.mert,
    clap: librarySummary.clap,
    classifiers: librarySummary.classifiers
  };
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
  }, [query, searchMode, libraryPreset, likedOnly, classifierMinScores, databasePath]);

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

  useEffect(() => {
    if (!audioDedupJob || !["queued", "running"].includes(audioDedupJob.state)) return;
    const timer = window.setInterval(() => {
      void api.audioDedupJob(audioDedupJob.job_id).then((job) => {
        setAudioDedupJob(job);
        if (["completed", "cancelled", "failed"].includes(job.state)) {
          if (job.apply) void refreshLibrary();
          if (job.state === "completed") {
            appendActivity("ok", "Audio Dedup завершен", `groups ${job.groups} · safe ${job.safe_candidates}`);
            setNotice({ kind: "ok", text: job.xlsx_path ? "Audio Dedup: XLSX готов" : "Audio Dedup завершен" });
          }
          if (job.state === "cancelled") {
            appendActivity("warn", "Audio Dedup остановлен", job.current_step || job.root);
          }
        }
      }).catch((error) => {
        setNotice({ kind: "error", text: error instanceof Error ? error.message : String(error) });
      });
    }, 1200);
    return () => window.clearInterval(timer);
  }, [audioDedupJob?.job_id, audioDedupJob?.state]);

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
      }).catch(() => undefined),
      api.latestAudioDedupJob().then((job) => {
        if (job) {
          setAudioDedupJob(job);
          if (["queued", "running"].includes(job.state)) setProcessLogKind("audio_dedup");
        }
      }).catch(() => undefined)
    ]);
  }

  function resetDatabaseScopedState() {
    resetLibraryState();
    setMusicRoot("");
    resetSearchPlaylistState();
    setScanJob(null);
    setAnalysisJob(null);
    setAudioDedupJob(null);
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

  function requestConfirmation(request: ConfirmationRequest) {
    setConfirmation(request);
  }

  function confirmPendingAction() {
    const pending = confirmation;
    if (!pending) return;
    setConfirmation(null);
    void pending.onConfirm();
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

  function toggleAnalysisModel(model: AnalysisSelection) {
    setSelectedAnalysisModels((current) => {
      const next = current.includes(model)
        ? current.filter((item) => item !== model)
        : [...current, model];
      return analysisModelOrder.filter((item) => next.includes(item));
    });
  }

  async function addVisibleTracksToPlaylist() {
    if (!databasePath || libraryLoading) return;
    setBusy(true);
    try {
      const filtered = await filteredTracks();
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
    appendActivity("info", "SONARA search запущен", `custom mixer · ${seeds.length} seed`);
    await run(
      () =>
        api.sonaraSearch({
          seed_track_ids: seeds,
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

  async function handleResetClassifiers() {
    const available = classifiers;
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

  async function handleAnalyzeClassifier(classifier: PromotedClassifier) {
    await run(
      async () => {
        const promotedClassifiers = await api.classifiers();
        setClassifiers(promotedClassifiers);
        const currentClassifier = promotedClassifiers.find((candidate) => candidate.classifier_key === classifier.classifier_key);
        if (!currentClassifier) {
          throw new Error(`Cannot rescore ${classifier.name}: Classifier profile is no longer available.`);
        }
        const blockedReason = classifierScoringBlockedReason(currentClassifier);
        if (blockedReason) {
          throw new Error(`Cannot rescore ${classifier.name}: ${blockedReason}`);
        }

        appendActivity("info", "CLASSIFIER пересчет запущен", `${currentClassifier.name} · reset scores + analyze`);
        setProcessLogKind("analysis");
        setAnalysisJob(null);
        await api.resetClassifiers([currentClassifier.classifier_key]);
        return api.analyzeClassifier(currentClassifier.classifier_key);
      },
      (job) => {
        setAnalysisJob(job);
        appendActivity("ok", "Classifier job создан", `${classifier.name} · ${job.job_id.slice(0, 8)} · ${job.total} треков`);
        return `${classifier.name}: ${job.total} треков к пересчету`;
      }
    );
  }

  async function handleMertSearch() {
    if (!seeds.length) {
      setNotice({ kind: "error", text: "Выберите seed-треки" });
      return;
    }
    appendActivity("info", "MERT search запущен", `${seeds.length} seed`);
    await run(
      () =>
        api.search({
          seed_track_ids: seeds,
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

  async function handleChooseAudioDedupFolder() {
    try {
      const value = await api.chooseFolder();
      if (!value.path) {
        appendActivity("info", "Выбор папки Audio Dedup отменен");
        return null;
      }
      appendActivity("ok", "Папка Audio Dedup выбрана", value.path);
      return value.path;
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      setNotice({ kind: "error", text: message });
      appendActivity("error", "Не удалось выбрать папку Audio Dedup", message);
      return null;
    }
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
    const requestedAudioModels = selectedAnalysisModels.filter(isAudioAnalysisModel);
    const includeClassifiers = selectedAnalysisModels.includes("classifiers");
    if (!requestedAudioModels.length && !includeClassifiers) {
      setNotice({ kind: "error", text: "Выберите хотя бы одну модель анализа" });
      return;
    }
    if (!requestedAudioModels.length && includeClassifiers && !classifiers.length) {
      setNotice({ kind: "error", text: "Нет promoted classifiers для расчета" });
      return;
    }
    const limit = analysisLimit > 0 ? analysisLimit : undefined;
    const models = [...requestedAudioModels];
    const labels = models.map((model) => model.toUpperCase()).join(", ");
    const classifierKeys = includeClassifiers && classifiers.length > 0 ? classifiers.map((classifier) => classifier.classifier_key) : [];
    const classifierTail = classifierKeys.length ? " · CLASSIFIERS в этом же job" : "";
    const detail = `${labels}${classifierTail} · ${analysisDevice.toUpperCase()} · tracks ${analysisTrackBatchSize} · inference ${analysisInferenceBatchSize} · ${limit ? `limit ${limit}` : "вся библиотека"}`;
    appendActivity("info", "Анализ выбранных моделей запущен", detail);
    setProcessLogKind("analysis");
    setAnalysisJob(null);
    await run(
      () => api.analysisJobStart({
        models,
        classifier_keys: classifierKeys,
        limit: limit ?? null,
        device: analysisDevice,
        top_k: 3,
        track_batch_size: analysisTrackBatchSize,
        inference_batch_size: analysisInferenceBatchSize
      }),
      (job) => {
        setAnalysisJob(job);
        if (includeClassifiers && !classifiers.length) {
          appendActivity("warn", "CLASSIFIERS не запущены", "Нет promoted classifier models");
        }
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
        resetLibraryState();
        resetSearchPlaylistState();
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
    const manualQueries = promptQueriesFromText(prompt, clapAvoidQuery);
    const positiveQueries = manualQueries.positiveQueries;
    const negativeQueries = manualQueries.negativeQueries;
    appendActivity("info", "CLAP search запущен", negativeQueries.length ? `${prompt} · avoid ${negativeQueries[0]}` : prompt);
    await run(
      () =>
        api.textSearch({
          query: prompt,
          positive_queries: positiveQueries,
          negative_queries: negativeQueries,
          adaptive_contrast: true,
          preset: clapPresetKey,
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

  async function handleSetBuilderGenerate(payload: SetBuilderGeneratePayload) {
    if (payload.seed_mode === "manual" && !payload.seed_track_ids.length) {
      setNotice({ kind: "error", text: "Выберите seed-треки для SET" });
      return;
    }
    appendActivity("info", "SET builder запущен", `${payload.mode} · ${payload.seed_mode}`);
    await run(
      () => api.setBuilderGenerate(payload),
      (value) => {
        setResults(value.items);
        setSeeds(value.seed_track_ids);
        const anchorTracks = value.items
          .filter((item) => value.seed_track_ids.includes(item.track.id))
          .map((item) => item.track);
        setSeedTrackMap((current) => {
          const next = { ...current };
          for (const track of anchorTracks) {
            next[track.id] = track;
          }
          return next;
        });
        appendActivity("ok", "SET builder завершен", `${value.items.length} треков · eligible ${value.coverage.eligible_tracks}`);
        return `SET: ${value.items.length} треков`;
      }
    );
  }

  function handleAddGeneratedSetToPlaylist() {
    if (!results.length) {
      setNotice({ kind: "error", text: "Нет SET preview для добавления" });
      return;
    }
    const nextPlaylist = appendVisibleTracksToPlaylist(playlist, results.map((item) => item.track));
    const added = nextPlaylist.length - playlist.length;
    if (!added) {
      setNotice({ kind: "idle", text: "Все треки preview уже в сете" });
      return;
    }
    setPlaylist(nextPlaylist);
    appendActivity("ok", "SET preview добавлен в сет", `${added} новых`);
    setNotice({ kind: "ok", text: `Добавлено в сет: ${added}` });
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

  async function handleAudioDedupStart(payload: AudioDedupJobPayload) {
    appendActivity(payload.apply ? "warn" : "info", "Audio Dedup запущен", `${payload.preset || "safe"} · ${payload.root}`);
    setProcessLogKind("audio_dedup");
    setAudioDedupJob(null);
    await run(
      () => api.audioDedupJobStart(payload),
      (job) => {
        setAudioDedupJob(job);
        appendActivity("ok", "Audio Dedup job создан", `${job.job_id.slice(0, 8)} · ${job.root}`);
        return `Audio Dedup job ${job.job_id.slice(0, 8)}`;
      }
    );
  }

  async function handleCancelAudioDedup() {
    if (!audioDedupJob) return;
    await run(
      () => api.cancelAudioDedupJob(audioDedupJob.job_id),
      (job) => {
        setAudioDedupJob(job);
        appendActivity("warn", "Audio Dedup cancel requested", job.job_id.slice(0, 8));
        return `Cancel requested: ${job.job_id.slice(0, 8)}`;
      }
    );
  }

  function handleOpenAudioDedupXlsx() {
    if (!audioDedupJob?.job_id || !audioDedupJob.xlsx_path) return;
    const opened = window.open(api.audioDedupXlsxUrl(audioDedupJob.job_id), "_blank", "noopener,noreferrer");
    if (!opened) {
      setNotice({ kind: "error", text: "Браузер заблокировал открытие XLSX" });
    }
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
      return;
    }
    if (audioDedupRunning) {
      await handleCancelAudioDedup();
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
      updateTrackLiked(updated);
      setPlaylist((current) => current.map((item) => (item.id === updated.id ? { ...item, liked: updated.liked } : item)));
      setResults((current) => current.map((item) => (
        item.track.id === updated.id ? { ...item, track: { ...item.track, liked: updated.liked } } : item
      )));
      setSeedTrackMap((current) => (
        current[updated.id] ? { ...current, [updated.id]: { ...current[updated.id], liked: updated.liked } } : current
      ));
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

  async function handleLaunchRhythmLab() {
    const pendingWindow = window.open("about:blank", "_blank");
    if (pendingWindow) pendingWindow.opener = null;
    try {
      const result = await api.launchRhythmLab();
      const opened = openRhythmLabWindow(result, pendingWindow);
      const status = result.already_running ? "Rhythm Lab уже запущен" : "Rhythm Lab запущен";
      setNotice({ kind: "ok", text: opened ? status : `${status}: ${result.url}` });
      appendActivity("ok", status, result.source_db ? `source ${result.source_db}` : result.url);
    } catch (error) {
      pendingWindow?.close();
      const message = error instanceof Error ? error.message : String(error);
      setNotice({ kind: "error", text: message });
      appendActivity("error", "Не удалось запустить Rhythm Lab", message);
    }
  }

  async function handleStopRhythmLab() {
    try {
      const result = await api.stopRhythmLab();
      const status = result.stopped ? "Rhythm Lab остановлен" : result.running ? "Rhythm Lab запущен не из этой кнопки" : "Rhythm Lab не запущен";
      setNotice({ kind: result.running && !result.stopped ? "error" : "ok", text: status });
      appendActivity(result.running && !result.stopped ? "warn" : "ok", status, result.url);
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      setNotice({ kind: "error", text: message });
      appendActivity("error", "Не удалось остановить Rhythm Lab", message);
    }
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
          <div className="library-summary" aria-label="Library analysis summary">
            <span className="library-summary-badge library-summary-total-badge"><span>tracks</span><strong>{librarySummary.tracks}</strong></span>
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
          <button
            className="icon-button rhythm-lab-launch-button"
            title="Запустить Rhythm Lab"
            aria-label="Запустить Rhythm Lab"
            onClick={() => void handleLaunchRhythmLab()}
            type="button"
          >
            <FlaskConical size={16} />
          </button>
          <button
            className="icon-button audio-dedup-launch-button"
            title="Открыть Audio Dedup"
            aria-label="Открыть Audio Dedup"
            onClick={() => setAudioDedupOpen(true)}
            type="button"
          >
            <CopyX size={16} />
          </button>
          <button
            className="icon-button rhythm-lab-stop-button"
            title="Остановить Rhythm Lab"
            aria-label="Остановить Rhythm Lab"
            onClick={() => void handleStopRhythmLab()}
            type="button"
          >
            <Power size={16} />
          </button>
          <button
            className="icon-button stop-button stop-active-stage-button"
            title="Остановить текущий scan или анализ"
            aria-label="Остановить текущий scan или анализ"
            disabled={busy || !stageRunning}
            onClick={() => void handleStopActiveStage()}
            type="button"
          >
            <Square size={15} />
          </button>
          <span className={`process-indicator ${stageRunning ? "running" : ""}`} title={stageIndicatorLabel(scanJob, analysisJob, genreTagJob, audioDedupJob)} aria-label={stageIndicatorLabel(scanJob, analysisJob, genreTagJob, audioDedupJob)}>
            <RefreshCcw size={17} />
          </span>
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
          helpText={helpText}
          onChooseFolder={() => void handleChooseFolder()}
          onScan={() => void handleScan()}
          onRefreshTags={() => void handleRefreshTags()}
          onWriteMaestGenres={() => void handleGenreTagsApply()}
          onClearDatabase={() => requestConfirmation({
            title: "Очистить базу?",
            message: "Удалить все данные из SQLite базы: треки, анализы, эмбеддинги и текущий сет? Аудиофайлы на диске останутся.",
            onConfirm: () => handleClearDatabase()
          })}
          analysisCounts={analysisModelCounts}
          selectedAnalysisModels={selectedAnalysisModels}
          onToggleAnalysisModel={toggleAnalysisModel}
          onAnalyzeSelected={() => void handleAnalyzeSelected()}
          onResetAnalysis={(adapter) => requestConfirmation({
            title: `Сбросить ${adapter.toUpperCase()}?`,
            message: `Сбросить результаты ${adapter.toUpperCase()}? Аудиофайлы не трогаем, остальные алгоритмы останутся.`,
            onConfirm: () => handleResetAnalysis(adapter)
          })}
          onResetClassifiers={() => requestConfirmation({
            title: "Сбросить CLASSIFIERS?",
            message: "Удалить сохраненные promoted classifier scores? Аудиофайлы не трогаем.",
            onConfirm: () => handleResetClassifiers()
          })}
        />

        <TrackPanel
          query={query}
          onQueryChange={setQuery}
          searchMode={searchMode}
          onSearchModeChange={setSearchMode}
          libraryPreset={libraryPreset}
          onToggleLibraryPreset={toggleLibraryPreset}
          likedOnly={likedOnly}
          likedTrackCount={librarySummary.liked}
          onToggleLikedOnly={toggleLikedOnly}
          librarySortDirection={librarySortDirection}
          onToggleLibrarySortDirection={toggleLibrarySortDirection}
          preview={preview}
          playingTrackId={playingTrackId}
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
          onPreview={togglePreview}
          onPreviewPlaying={markPreviewPlaying}
          onPreviewPaused={markPreviewPaused}
          onDetails={(track) => void handleTrackDetails(track)}
        />

        <SearchPlaylistPanel
          seedTracks={seedTracks}
          textQuery={textQuery}
          onTextQueryChange={setTextQuery}
          clapAvoidQuery={clapAvoidQuery}
          onClapAvoidQueryChange={setClapAvoidQuery}
          clapPresetKey={clapPresetKey}
          onClapPresetChange={setClapPresetKey}
          clapPromptPresets={clapPromptPresets}
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
          clapEmbeddingCount={librarySummary.clap}
          classifiers={classifiers}
          classifierMinScores={classifierMinScores}
          onClassifierMinScoreChange={(classifier, value) =>
            setClassifierMinScores((current) => ({ ...current, [classifier]: value }))
          }
          onAnalyzeClassifier={handleAnalyzeClassifier}
          classifierJob={classifiers.some((classifier) => classifier.classifier_key === analysisJob?.adapter_name) ? analysisJob : null}
          removeSeed={removeSeed}
          handleTextSearch={() => void handleTextSearch()}
          handleSonaraSearch={() => void handleSonaraSearch()}
          handleMertSearch={() => void handleMertSearch()}
          handleSetBuilderGenerate={(payload) => void handleSetBuilderGenerate(payload)}
          addGeneratedSetToPlaylist={handleAddGeneratedSetToPlaylist}
          addSeed={addSeed}
          togglePlaylist={togglePlaylist}
          playingTrackId={playingTrackId}
          setPreview={togglePreview}
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
          audioDedupJob={audioDedupJob}
          genreTagJob={genreTagJob}
          activityLog={activityLog}
          onClose={() => setLogFrameOpen(false)}
        />
      )}
      {audioDedupOpen && (
        <AudioDedupDialog
          databasePath={databasePath}
          defaultRoot={musicRoot}
          job={audioDedupJob}
          onChooseFolder={handleChooseAudioDedupFolder}
          onStart={handleAudioDedupStart}
          onCancelJob={handleCancelAudioDedup}
          onOpenXlsx={handleOpenAudioDedupXlsx}
          onClose={() => setAudioDedupOpen(false)}
        />
      )}
      <TooltipLayer tooltip={tooltip} />
    </main>
  );
}

function genreTagJobSummary(job: GenreTagJobStatus) {
  return `записано ${job.applied} · пропущено ${job.skipped} · ошибок ${job.failed} · всего ${job.total}`;
}
