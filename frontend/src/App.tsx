import { useSearchRequests } from "./useSearchRequests";
import { useTextSearch } from "./useTextSearch";
import { useJobState } from "./useJobState";
import type { MouseEvent } from "react";
import { useEffect, useMemo, useRef, useState } from "react";
import { AudioLines, Moon, Power, RefreshCcw, ScrollText, Square, Sun } from "lucide-react";
import { PlayerDock } from "./PlayerDock";
import {
  AnalysisModel,
  api,
  DatabaseValidationJobStatus,
  PromotedClassifier,
  RhythmLabLaunchResult,
  RhythmLabStatus,
  ScanRequest,
  Track,
  TrackDetail,
} from "./api";
import {
  analysisSelectionOrder,
  analysisStartBlockedByMissingSonara,
  defaultStageSelections,
  describeAnalysisStart,
  type AnalysisSelection,
  type StageSelection
} from "./analysisSelection";
import {
  textPromptAxes,
  textPromptPresets
} from "./textPromptPresets";
import { classifierIsAvailable, classifierScoringBlockedReason } from "./classifierCompatibility";
import { ConfirmationDialog, LogFrameDialog } from "./dialogs";
import { AudioDedupDialog } from "./AudioDedupDialog";
import { exportDirectoryError } from "./exportView";
import { helpText } from "./helpText";
import { cancelAnalysisJob, scanSummary, stageIndicatorLabel } from "./jobUi";
import type { ProcessLogKind } from "./jobUi";
import { LibraryPanel } from "./LibraryPanel";
import { MLAnalysisSettingsDialog } from "./MLAnalysisSettingsDialog";
import { writePreviewPosition } from "./previewPosition";
import { ScanImportDialog } from "./ScanImportDialog";
import { SonaraAnalysisSettingsDialog } from "./SonaraAnalysisSettingsDialog";
import {
  appendVisibleTracksToPlaylist,
  nextLibraryPlaybackTrack,
  resolvePanelCollapsed,
  storePanelCollapsed
} from "./libraryView";
import type { CollapsiblePanel } from "./libraryView";
import { SearchPlaylistPanel, type SearchFiltersState } from "./SearchPlaylistPanel";
import { shutdownApplication } from "./shutdownApplication";
import {
  loadSonaraAnalysisSettings,
  saveSonaraAnalysisSettings,
  type SonaraAnalysisSettings,
} from "./sonaraAnalysisSettings";
import {
  loadMLAnalysisSettings,
  saveMLAnalysisSettings,
  type MLAnalysisSettings,
  withMLStagingFolder,
} from "./mlAnalysisSettings";
import {
  boundScanDuration,
  loadScanImportSettings,
  saveScanImportSettings,
  scanExtensionsFor,
  type ScanImportSettings,
} from "./scanImportSettings";
import {
  createRequestTokenGuard,
  type PrimarySearchTab,
  type SeedEmbeddingFamily,
} from "./searchSurfaceState";
import { TrackMetadataDialog } from "./TrackMetadataDialog";
import { TrackPanel } from "./TrackPanel";
import { displayTrack, sameTrackIdentity } from "./trackDisplay";
import { applyTheme, resolveInitialTheme, themeStorageKey, type ThemeMode } from "./theme";
import { TooltipLayer, useGlobalTooltip } from "./tooltipLayer";
import { useActivityLog } from "./useActivityLog";
import { useConfirmation } from "./useConfirmation";
import { useLibraryState } from "./useLibraryState";
import { useSearchPlaylist } from "./useSearchPlaylist";
import type { PreviewTarget } from "./useSearchPlaylist";

type Notice = { kind: "ok" | "error" | "idle"; text: string };
type DeviceMode = "auto" | "cpu" | "cuda";
type ResetAdapter = AnalysisModel;

const defaultNotice: Notice = { kind: "idle", text: "Готово к работе" };
const analysisModelOrder = analysisSelectionOrder;
const defaultScanWorkers = 8;
const maxScanWorkers = 16;

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
  const [databaseCatalogUuid, setDatabaseCatalogUuid] = useState<string | null>(null);
  const databaseCatalogUuidRef = useRef(databaseCatalogUuid);
  databaseCatalogUuidRef.current = databaseCatalogUuid;
  const suppressNextLibraryRefresh = useRef(false);
  const startupInitializationStarted = useRef(false);
  const { activityLog, appendActivity } = useActivityLog();
  const {
    libraryTotal,
    libraryOffset,
    libraryLoading,
    libraryError,
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
    adoptDatabaseScope,
    refreshLibrary,
    refreshLibrarySummary,
    resetLibraryState,
    changeLibraryPage,
    jumpToLibraryPage,
    toggleLibraryPreset,
    toggleLikedOnly,
    toggleLibrarySortDirection,
    updateTrackLiked
  } = useLibraryState({
    databaseSelected: Boolean(databasePath),
    databaseKey: databaseCatalogUuid
  });
  const {
    outputDir,
    setOutputDir,
    seeds,
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
    setSeedTracks,
    seedSet,
    playlistSet,
    seedTracks,
    addSeed,
    removeSeed,
    removeFromPlaylist,
    togglePlaylist,
    resetSearchPlaylistState
  } = useSearchPlaylist({ onActivity: appendActivity });
  const [seedEmbeddingFamily, setSeedEmbeddingFamily] = useState<SeedEmbeddingFamily>("mert");
  const [classifiers, setClassifiers] = useState<PromotedClassifier[]>([]);
  const [scanImportOpen, setScanImportOpen] = useState(false);
  const [sonaraSettingsDialogOpen, setSonaraSettingsDialogOpen] = useState(false);
  const [mlSettingsDialogOpen, setMlSettingsDialogOpen] = useState(false);
  const [scanImportStartToast, setScanImportStartToast] = useState(false);
  const [rhythmLabStatus, setRhythmLabStatus] = useState<RhythmLabStatus | null>(null);
  const [processLogKind, setProcessLogKind] = useState<ProcessLogKind>("scan");
  const [analysisLimit, setAnalysisLimit] = useState(0);
  const [analysisTrackBatchSize, setAnalysisTrackBatchSize] = useState(8);
  const [analysisInferenceBatchSize, setAnalysisInferenceBatchSize] = useState(16);
  const [sonaraSettings, setSonaraSettings] = useState<SonaraAnalysisSettings>(
    () => loadSonaraAnalysisSettings(),
  );
  const [mlSettings, setMlSettings] = useState<MLAnalysisSettings>(
    () => loadMLAnalysisSettings(),
  );
  const [analysisDevice, setAnalysisDevice] = useState<DeviceMode>("auto");
  const [selectedStages, setSelectedStages] = useState<StageSelection[]>(defaultStageSelections);
  const [initialLibraryLoaded, setInitialLibraryLoaded] = useState(false);
  const [scanImportSettings, setScanImportSettings] = useState<ScanImportSettings>(
    () => loadScanImportSettings(),
  );
  const [notice, setNotice] = useState<Notice>(defaultNotice);
  const [logFrameOpen, setLogFrameOpen] = useState(false);
  const [audioDedupOpen, setAudioDedupOpen] = useState(false);
  const [theme, setTheme] = useState<ThemeMode>(() => resolveInitialTheme());
  // The workspace is three equal columns, and only the search panel needs all
  // of its width all of the time: setup is done once, and the library is a
  // place to find a track rather than to watch. Either can fold to a rail, and
  // folding both leaves the search panel nearly the whole row.
  const [setupCollapsed, setSetupCollapsed] = useState(() => resolvePanelCollapsed("setup"));
  const [libraryCollapsed, setLibraryCollapsed] = useState(() => resolvePanelCollapsed("library"));
  const { confirmation, requestConfirmation, confirmPendingAction, cancelConfirmation } = useConfirmation();
  // One optimization prompt per finished validation, however many polls observe it.
  const optimizationPromptedForJob = useRef<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [serverShutdownAccepted, setServerShutdownAccepted] = useState(false);
  const [libraryPlaybackShuffle, setLibraryPlaybackShuffle] = useState(false);
  const [filters, setFilters] = useState<SearchFiltersState>({
    limit: 20,
    sonaraMode: "custom",
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
      loudness: 0,
      vocalness: 0,
      aggression: 0
    }
  });

  const {
    selectedPresetKeys,
    textFeedbackContext,
    executions, feedbackPending, feedbackReady,
    textFeedbackVerdicts,
    textCompareModels,
    setTextCompareModels,
    textModelLoadingLabel,
    textComparison,
    textQuery,
    promptNegativeWeight,
    textNegativeQuery,
    textUseNegativePrompt,
    setTextUseNegativePrompt,
    textEmbeddingFamily,
    clearPromptPresets,
    togglePromptPreset,
    changeTextEmbeddingFamily,
    handleTextSearch,
    cancelTextSearch,
    handleTextResultFeedback,
  } = useTextSearch({
    embeddingCounts: { clap: librarySummary.clap, mulan: librarySummary.mulan },
    databasePath,
    databaseCatalogUuid,
    filters,
    analysisDevice,
    setNotice,
    appendActivity,
  });
  const searchRequests = useSearchRequests({
    databasePath,
    databaseCatalogUuid,
    seedTracks,
    seeds,
    filters,
    textUseNegativePrompt,
    selectedPresetKeys,
    textCompareModels,
    analysisDevice,
    textEmbeddingFamily,
    seedEmbeddingFamily,
    setResults,
    addSeed,
    setNotice,
    appendActivity,
  });
  const {
    genericSearchPending,
    randomSonaraTrackPending,
    randomEmbeddingTrackPending,
    genericSearchResultState,
    genericSearchInputKey,
    cancelGenericSearchRequest,
    handleSonaraSearch,
    handleAddRandomSonaraTrack,
    handleAddRandomEmbeddingTrack,
    handleEmbeddingSearch,
  } = searchRequests;
  const {
    analysisJob,
    setAnalysisJob,
    analysisPipelineJob,
    setAnalysisPipelineJob,
    scanJob,
    setScanJob,
    genreTagJob,
    setGenreTagJob,
    databaseValidationJob,
    setDatabaseValidationJob,
    databaseOptimizationJob,
    setDatabaseOptimizationJob,
    scanRunning,
    analysisRunning,
    genreTagRunning,
    databaseValidationRunning,
    databaseOptimizationRunning,
    loadLatestJobs,
  } = useJobState({
    classifiers,
    setProcessLogKind,
    refreshLibrary,
    refreshLibrarySummary,
    refreshClassifierProfilesInBackground,
    setNotice,
    appendActivity,
    promptDatabaseOptimization,
  });

  const previewAudioRef = useRef<HTMLAudioElement | null>(null);
  const trackDetailRequestGuard = useRef(createRequestTokenGuard());
  const trackDetailAbortController = useRef<AbortController | null>(null);

  const stageRunning = scanImportStartToast || scanRunning || analysisRunning || genreTagRunning || databaseValidationRunning || databaseOptimizationRunning;
  const rhythmLabRunning = Boolean(rhythmLabStatus?.running);
  const logHasErrors = useMemo(() => {
    const hasErrorEvent = activityLog.some((event) => event.level === "error")
      || (scanJob?.events || []).some((event) => event.level === "error")
      || (analysisJob?.events || []).some((event) => event.level === "error")
      || (genreTagJob?.events || []).some((event) => event.level === "error");
    return hasErrorEvent || Boolean(analysisJob?.errors.length) || Boolean(genreTagJob?.errors.length) || Boolean(databaseValidationJob?.errors) || Boolean(databaseOptimizationJob?.error);
  }, [activityLog, analysisJob, databaseOptimizationJob, databaseValidationJob, genreTagJob, scanJob]);
  // The library reports the one BPM range it analyses SONARA with. Once an
  // analysis job has claimed it, the range is fixed until that analysis is
  // reset or the library is cleared.
  const sonaraBpmRangeLocked = librarySummary.sonara_bpm_min != null
    && librarySummary.sonara_bpm_max != null;
  const sonaraBpmRange = sonaraBpmRangeLocked
    ? { bpmMin: librarySummary.sonara_bpm_min as number, bpmMax: librarySummary.sonara_bpm_max as number }
    : { bpmMin: sonaraSettings.bpmMin, bpmMax: sonaraSettings.bpmMax };
  const analysisModelCounts: Record<AnalysisSelection, number> = {
    sonara: librarySummary.sonara,
    maest: librarySummary.maest_analysis,
    mert: librarySummary.mert,
    muq: librarySummary.muq,
    mulan: librarySummary.mulan,
    clap: librarySummary.clap
  };
  const maxAnalysisTrackBatchSize = 64;
  const maxAnalysisInferenceBatchSize = 128;

  useEffect(() => {
    if (startupInitializationStarted.current) return;
    startupInitializationStarted.current = true;
    void initializeDatabase();
    void refreshRhythmLabStatus();
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
    saveSonaraAnalysisSettings(sonaraSettings);
  }, [sonaraSettings]);

  useEffect(() => {
    saveMLAnalysisSettings(mlSettings);
  }, [mlSettings]);

  useEffect(() => {
    saveScanImportSettings(scanImportSettings);
  }, [scanImportSettings]);

  // Keeps the stage checkbox valid: SONARA/ML are only reachable once tracks
  // exist, and ML only once SONARA has results — mirrors the per-checkbox
  // disabled rules in LibraryPanel. Gated on the first real summary fetch so
  // the tracks: 0 startup default doesn't force DATABASE on every reload of
  // an already-analyzed library.
  useEffect(() => {
    if (!initialLibraryLoaded) return;
    if (!hasTracks) {
      setSelectedStages(["database"]);
    } else if (librarySummary.sonara < 1) {
      setSelectedStages(["sonara"]);
    }
  }, [initialLibraryLoaded, hasTracks, librarySummary.sonara]);

  useEffect(() => {
    cancelTrackDetailRequest();
  }, [databaseCatalogUuid]);

  useEffect(() => () => {
    trackDetailAbortController.current?.abort();
  }, []);

  useEffect(() => {
    writePreviewPosition({
      trackId: preview?.track_id ?? null,
      currentTime: 0,
      duration: 0,
    });
  }, [preview?.track_id]);

  useEffect(() => {
    const audio = previewAudioRef.current;
    if (!audio || !preview) return;
    if (playingTrackId === preview.track_id) {
      void audio.play().catch(() => undefined);
    } else {
      audio.pause();
    }
  }, [preview, playingTrackId]);

  useEffect(() => {
    if (!databasePath) return;
    if (suppressNextLibraryRefresh.current) {
      suppressNextLibraryRefresh.current = false;
      return;
    }
    const timer = window.setTimeout(() => {
      void refreshLibrary(0);
    }, 250);
    return () => window.clearTimeout(timer);
  }, [
    query,
    searchMode,
    libraryPreset,
    likedOnly,
    classifierMinScores,
    databasePath,
    databaseCatalogUuid
  ]);

  async function initializeDatabase() {
    try {
      const current = await api.currentDatabase();
      if (current.path !== databasePath) suppressNextLibraryRefresh.current = true;
      if (current.selected) adoptDatabaseScope(current.catalog_uuid);
      setDatabasePath(current.path);
      setDatabaseCatalogUuid(current.catalog_uuid);
      if (!current.selected) {
        resetDatabaseScopedState();
        setNotice({ kind: "idle", text: "Выберите SQLite базу данных" });
        return;
      }
      const promotedClassifiersRequest = api.classifiers();
      await refreshLibrary(0, {
        selected: true,
        databaseKey: current.catalog_uuid,
        refreshSummary: true
      });
      const promotedClassifiers = await promotedClassifiersRequest;
      adoptClassifierProfiles(promotedClassifiers);
      await loadLatestJobs(promotedClassifiers);
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      setNotice({ kind: "error", text: message });
      appendActivity("error", "Не удалось прочитать текущую базу", message);
    } finally {
      // librarySummary starts at tracks: 0 before this resolves, so the stage
      // auto-correction effect must not treat that startup default as a real
      // empty library until the first real fetch has settled.
      setInitialLibraryLoaded(true);
    }
  }

  async function refreshRhythmLabStatus() {
    try {
      setRhythmLabStatus(await api.rhythmLabStatus());
    } catch {
      setRhythmLabStatus(null);
    }
  }

  function adoptClassifierProfiles(promotedClassifiers: PromotedClassifier[]) {
    setClassifiers(promotedClassifiers);
    setClassifierMinScores((current) => {
      const availableKeys = new Set(
        promotedClassifiers
          .filter(
            (classifier) =>
              classifierIsAvailable(classifier)
              && Number(classifier.scored_tracks || 0) > 0,
          )
          .map((classifier) => classifier.classifier_key)
      );
      return Object.fromEntries(
        Object.entries(current).filter(([key]) => availableKeys.has(key))
      );
    });
  }

  async function refreshClassifierProfiles() {
    const promotedClassifiers = await api.classifiers();
    adoptClassifierProfiles(promotedClassifiers);
    return promotedClassifiers;
  }

  function refreshClassifierProfilesInBackground() {
    void refreshClassifierProfiles().catch((error) => {
      const message = error instanceof Error ? error.message : String(error);
      appendActivity("warn", "Не удалось обновить CLASS profiles", message);
    });
  }

  function resetDatabaseScopedState() {
    databaseCatalogUuidRef.current = null;
    cancelGenericSearchRequest();
    cancelTextSearch();
    cancelTrackDetailRequest();
    resetLibraryState();
    setDatabaseCatalogUuid(null);
    resetSearchPlaylistState();
    setScanJob(null);
    setAnalysisJob(null);
    setAnalysisPipelineJob(null);
    setGenreTagJob(null);
    setClassifiers([]);
  }

  async function run<T>(
    action: () => Promise<T>,
    ok: (value: T) => string | void,
    options: { refreshLibrary?: boolean; refreshSummary?: boolean } = {}
  ) {
    setBusy(true);
    try {
      const value = await action();
      if (options.refreshLibrary) {
        await refreshLibrary(0, { refreshSummary: options.refreshSummary });
      } else if (options.refreshSummary) {
        await refreshLibrarySummary();
      }
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

  function handlePrimarySearchTabChange(tab: PrimarySearchTab) {
    cancelGenericSearchRequest();
    cancelTextSearch();
    if (tab === "class" && databasePath) {
      refreshClassifierProfilesInBackground();
    }
  }

  function cancelTrackDetailRequest() {
    trackDetailRequestGuard.current.invalidate();
    trackDetailAbortController.current?.abort();
    trackDetailAbortController.current = null;
    setMetadataTrack(null);
  }

  function updatePreviewPosition(trackId: number) {
    const audio = previewAudioRef.current;
    if (!audio) return;
    const duration = Number.isFinite(audio.duration) ? Math.max(0, audio.duration) : 0;
    writePreviewPosition({
      trackId,
      currentTime: Math.min(Math.max(0, audio.currentTime), duration || 0),
      duration,
    });
  }

  function seekPreview(track: PreviewTarget, seconds: number) {
    const audio = previewAudioRef.current;
    if (!audio || preview?.track_id !== track.track_id) return;
    const duration = Number.isFinite(audio.duration) ? Math.max(0, audio.duration) : 0;
    audio.currentTime = Math.min(Math.max(0, seconds), duration);
    updatePreviewPosition(track.track_id);
  }

  function handleLibraryPreviewEnded(track: PreviewTarget) {
    updatePreviewPosition(track.track_id);
    const nextTrack = nextLibraryPlaybackTrack(
      orderedTracks,
      track.track_id,
      libraryPlaybackShuffle
    );
    if (nextTrack) {
      togglePreview(nextTrack);
      return;
    }
    markPreviewPaused(track.track_id);
  }

  async function handleTrackDetails(track: Track) {
    trackDetailAbortController.current?.abort();
    const controller = new AbortController();
    const token = trackDetailRequestGuard.current.begin();
    trackDetailAbortController.current = controller;
    setMetadataTrack(null);
    try {
      const fullTrack = await api.track(track.track_id, {
        signal: controller.signal,
      });
      if (!trackDetailRequestGuard.current.isCurrent(token)) return;
      if (
        databaseCatalogUuidRef.current !== track.catalog_uuid
        || !sameTrackIdentity(track, fullTrack)
      ) {
        throw new Error(
          "Track details changed while loading; refresh the current catalog and try again."
        );
      }
      setMetadataTrack(fullTrack);
    } catch (error) {
      if (
        !trackDetailRequestGuard.current.isCurrent(token)
        || isAbortError(error)
      ) {
        return;
      }
      const message = error instanceof Error ? error.message : String(error);
      setNotice({ kind: "error", text: message });
      appendActivity("error", "Не удалось загрузить теги трека", message);
    } finally {
      if (
        trackDetailRequestGuard.current.isCurrent(token)
        && trackDetailAbortController.current === controller
      ) {
        trackDetailAbortController.current = null;
      }
    }
  }

  function toggleStage(stage: StageSelection) {
    setSelectedStages((current) => {
      if (current.length === 1 && current.includes(stage)) return current;
      if (stage === "database" || stage === "sonara") {
        return [stage];
      }
      const mlSelections = current.filter(
        (item): item is AnalysisModel => item !== "database" && item !== "sonara",
      );
      const next = mlSelections.includes(stage)
        ? mlSelections.filter((item) => item !== stage)
        : [...mlSelections, stage];
      return next.length
        ? analysisModelOrder.filter((item) => next.includes(item))
        : current;
    });
  }

  function addVisibleTracksToPlaylist() {
    const nextPlaylist = appendVisibleTracksToPlaylist(playlist, orderedTracks);
    const added = nextPlaylist.length - playlist.length;
    if (!added) {
      setNotice({ kind: "idle", text: "Все треки страницы уже в сете" });
      return;
    }
    setPlaylist(nextPlaylist);
    appendActivity("ok", "Текущая страница добавлена в сет", `${added} новых · на странице ${orderedTracks.length}`);
    setNotice({ kind: "ok", text: `Добавлено в сет: ${added}` });
  }

  function addPromptCandidatesToPlaylist(tracks: Track[], modelLabel: string) {
    if (
      busy || genericSearchPending
      || genericSearchResultState?.origin !== "text"
      || genericSearchResultState.requestKey !== genericSearchInputKey
    ) return;
    const nextPlaylist = appendVisibleTracksToPlaylist(playlist, tracks);
    const added = nextPlaylist.length - playlist.length;
    if (!added) {
      setNotice({ kind: "idle", text: "Все показанные кандидаты уже в сете" });
      return;
    }
    setPlaylist(nextPlaylist);
    appendActivity("ok", "Кандидаты PROMPT добавлены в сет", `${modelLabel} · ${added} новых · показано ${tracks.length}`);
    setNotice({ kind: "ok", text: `Добавлено в сет: ${added}` });
  }

  async function handleAnalyzeClassifier(classifier: PromotedClassifier) {
    if (librarySummary.sonara < 1) {
      const message = "Сначала выполните SONARA-анализ хотя бы одного трека";
      setNotice({ kind: "error", text: message });
      appendActivity("error", "CLASSIFIER недоступен", message);
      return;
    }
    await run(
      async () => {
        const promotedClassifiers = await api.classifiers();
        adoptClassifierProfiles(promotedClassifiers);
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
        await api.resetClassifier(currentClassifier.classifier_key);
        return api.analyzeClassifier(currentClassifier.classifier_key);
      },
      (job) => {
        setAnalysisJob(job);
        appendActivity("ok", "Classifier job создан", `${classifier.name} · ${job.job_id.slice(0, 8)} · ${job.total} треков`);
        return `${classifier.name}: ${job.total} треков к пересчету`;
      },
      { refreshLibrary: true, refreshSummary: true }
    );
  }

  async function handleResetClassifier(classifier: PromotedClassifier) {
    appendActivity("warn", "CLASSIFIER очистка запущена", classifier.name);
    await run(
      () => api.resetClassifier(classifier.classifier_key),
      (result) => {
        setClassifiers((current) => current.map((candidate) => candidate.classifier_key === classifier.classifier_key ? { ...candidate, scored_tracks: 0 } : candidate));
        setClassifierMinScores((current) => {
          const next = { ...current };
          delete next[classifier.classifier_key];
          return next;
        });
        const detail = `${classifier.name} · удалено ${result.classifier_rows_deleted} score`;
        appendActivity("ok", "CLASSIFIER данные удалены", detail);
        return detail;
      },
      { refreshLibrary: true, refreshSummary: true }
    );
  }

  async function handleStartScan(request: ScanRequest) {
    appendActivity(
      "info",
      "Подготовка сканирования начата",
      request.root,
    );
    setProcessLogKind("scan");
    setScanJob(null);
    setScanImportOpen(false);
    setScanImportStartToast(true);
    setNotice({ kind: "idle", text: "Сканирование директории" });
    setBusy(true);
    try {
      const value = await api.scan(request);
      setScanJob(value);
      const detail = value.job_id ? `job ${value.job_id.slice(0, 8)} · ${value.total || 0} файлов` : scanSummary(value);
      appendActivity("ok", "Scan job создан", detail);
      setNotice(
        ["queued", "running"].includes(value.state || "")
          ? { kind: "ok", text: "Загрузка треков в базу" }
          : { kind: "ok", text: detail },
      );
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      setNotice({ kind: "error", text: message });
      appendActivity("error", "Ошибка загрузки треков", message);
    } finally {
      setScanImportStartToast(false);
      setBusy(false);
    }
  }

  // The single "Старт" entry point: runs whichever stage is checked in the
  // library panel. DATABASE and SONARA/ML are mutually exclusive selections
  // (toggleStage), so exactly one branch below ever applies.
  async function handleStageStart() {
    if (selectedStages.includes("database")) {
      await handleStartScan({
        root: scanImportSettings.root,
        workers: scanImportSettings.workers,
        limit: analysisLimit > 0 ? analysisLimit : undefined,
        extensions: scanExtensionsFor(scanImportSettings.selectedFormats),
        min_duration_seconds: boundScanDuration(scanImportSettings.minDurationSeconds),
        max_duration_seconds: boundScanDuration(scanImportSettings.maxDurationSeconds),
      });
      return;
    }
    await handleAnalyzeSelected();
  }

  async function handleChooseScanFolder(): Promise<string | null> {
    setBusy(true);
    try {
      const value = await api.chooseFolder();
      if (!value.path) {
        appendActivity("info", "Выбор папки отменен");
        return null;
      }
      appendActivity("ok", "Папка выбрана", value.path);
      return value.path;
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      setNotice({ kind: "error", text: message });
      appendActivity("error", "Не удалось выбрать папку", message);
      return null;
    } finally {
      setBusy(false);
    }
  }

  async function handleChooseStagingFolder() {
    await run(
      () => api.chooseFolder(),
      (value) => {
        if (!value.path) {
          appendActivity("info", "Выбор папки staging отменен");
          return "Выбор папки staging отменен";
        }
        setSonaraSettings((current) => ({
          ...current,
          staged: { ...current.staged, folder: value.path || "" },
        }));
        appendActivity("ok", "Папка staging выбрана", value.path);
        return value.path;
      }
    );
  }

  async function handleChooseMLStagingFolder() {
    await run(
      () => api.chooseFolder(),
      (value) => {
        const folder = value.path;
        if (!folder) {
          appendActivity("info", "Выбор ML staging-папки отменен");
          return "Выбор ML staging-папки отменен";
        }
        setMlSettings((current) => withMLStagingFolder(current, folder));
        appendActivity("ok", "ML staging-папка выбрана", folder);
        return `ML staging-папка: ${folder}`;
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
      if (value.path !== databasePath) suppressNextLibraryRefresh.current = true;
      resetDatabaseScopedState();
      adoptDatabaseScope(value.catalog_uuid);
      setDatabasePath(value.path);
      setDatabaseCatalogUuid(value.catalog_uuid);
      const promotedClassifiersRequest = api.classifiers();
      await refreshLibrary(0, {
        selected: true,
        databaseKey: value.catalog_uuid,
        refreshSummary: true
      });
      const promotedClassifiers = await promotedClassifiersRequest;
      adoptClassifierProfiles(promotedClassifiers);
      await loadLatestJobs(promotedClassifiers);
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
    // DATABASE is handled by handleStageStart before this ever runs; the
    // mutual-exclusion in toggleStage guarantees it is absent here.
    const stageModels = selectedStages.filter((stage): stage is AnalysisSelection => stage !== "database");
    const mlModels = stageModels.filter((model) => model !== "sonara");
    const includeSonara = stageModels.includes("sonara");
    const stages: Array<"sonara" | "ml"> = [];
    if (includeSonara) stages.push("sonara");
    if (mlModels.length) stages.push("ml");
    if (!stages.length) {
      setNotice({ kind: "error", text: "Выберите хотя бы одну стадию анализа" });
      return;
    }
    if (
      includeSonara
      && sonaraSettings.mode === "staged"
      && !sonaraSettings.staged.folder.trim()
    ) {
      const message = "Выберите папку staging перед запуском Staged Mode";
      setNotice({ kind: "error", text: message });
      appendActivity("error", "SONARA Staged Mode недоступен", message);
      return;
    }
    if (
      analysisStartBlockedByMissingSonara(
        stageModels,
        librarySummary.sonara
      )
    ) {
      const message = "Сначала выполните SONARA-анализ хотя бы одного трека";
      setNotice({ kind: "error", text: message });
      appendActivity("error", "ML недоступны", message);
      return;
    }
    const limit = analysisLimit > 0 ? analysisLimit : undefined;
    const settings: string[] = [];
    if (includeSonara) {
      settings.push(
        sonaraSettings.mode === "staged"
          ? `SONARA · Staged · ${sonaraSettings.staged.folder} · Processes ${sonaraSettings.staged.processes} · Threads ${sonaraSettings.staged.threads} · BatchSize ${sonaraSettings.staged.batchSize} · StageSize ${sonaraSettings.staged.stageSize}`
          : `SONARA · Direct · BatchSize ${sonaraSettings.directBatchSize}`
      );
    }
    if (mlModels.length) {
      settings.push(
        `ML · ${mlModels.map((model) => model.toUpperCase()).join(", ")} · Device ${analysisDevice.toUpperCase()} · `
        + `Track batch ${analysisTrackBatchSize} · Inference batch ${analysisInferenceBatchSize}`
      );
    }
    settings.push(`Analyze limit ${limit ?? "all"}`);
    setProcessLogKind("analysis");
    setAnalysisJob(null);
    setAnalysisPipelineJob(null);
    await run(
      async () => {
        return api.analysisPipelineStart({
          stages,
          limit: limit === 0 ? undefined : limit,
          sonara: {
            mode: sonaraSettings.mode,
            direct_batch_size: sonaraSettings.directBatchSize,
            bpm_min: sonaraBpmRange.bpmMin,
            bpm_max: sonaraBpmRange.bpmMax,
            staged: {
              folder: sonaraSettings.staged.folder,
              processes: sonaraSettings.staged.processes,
              threads: sonaraSettings.staged.threads,
              batch_size: sonaraSettings.staged.batchSize,
              stage_size: sonaraSettings.staged.stageSize,
            },
          },
          ml: {
            mode: mlSettings.mode,
            staged: {
              folder: mlSettings.staged.folder,
              copy_workers: mlSettings.staged.workers,
              decode_workers: mlSettings.staged.workers,
              stage_size: mlSettings.staged.stageSize,
              inference_batch_size: analysisInferenceBatchSize,
              preflight_copy_enabled: true,
              preflight_copy_count: 64,
            },
            models: mlModels,
            device: analysisDevice,
            top_k: 3,
            track_batch_size: analysisTrackBatchSize,
            inference_batch_size: analysisInferenceBatchSize
          }
        });
      },
      (job) => {
        setAnalysisPipelineJob(job);
        appendActivity("ok", "Анализ поставлен в очередь", settings.join(" | "));
        return describeAnalysisStart(job.order, mlModels, limit);
      }
    );
  }

  async function handleRefreshTags() {
    appendActivity("info", "Refresh tags запущен", "Перечитываем Mutagen tags для существующих треков");
    setProcessLogKind("scan");
    setScanJob(null);
    await run(
      () => api.refreshTags(defaultScanWorkers),
      (value) => {
        setScanJob(value);
        const detail = value.job_id ? `job ${value.job_id.slice(0, 8)} · ${value.total || 0} треков` : scanSummary(value);
        appendActivity("ok", "Refresh tags job создан", detail);
        return detail;
      }
    );
  }

  async function handleValidateDatabase() {
    await run(
      () => api.startDatabaseValidation(),
      (job) => {
        setDatabaseValidationJob(job);
        setProcessLogKind("database_validation");
        setNotice({ kind: "ok", text: "Проверка БД запущена" });
      },
    );
  }

  async function handleOptimizeDatabase() {
    await run(
      () => api.startDatabaseOptimization(),
      (job) => {
        setDatabaseOptimizationJob(job);
        setProcessLogKind("database_optimization");
        return "Оптимизация БД запущена";
      },
    );
  }

  function promptDatabaseOptimization(job: DatabaseValidationJobStatus) {
    // Only a clean validation earns the prompt: VACUUM must not run over a
    // library whose rows just failed their contracts.
    if (job.state !== "completed" || job.errors > 0) return;
    if (optimizationPromptedForJob.current === job.job_id) return;
    optimizationPromptedForJob.current = job.job_id;
    requestConfirmation({
      title: "Оптимизировать базу данных?",
      message:
        `Проверка завершена без ошибок: ${job.checked} проверок, предупреждений ${job.warnings}. ` +
        "Будет создана проверенная резервная копия рядом с базой, затем выполнены VACUUM и ANALYZE. " +
        "На большой базе это занимает несколько минут; запись в базу на это время приостанавливается.",
      onConfirm: () => handleOptimizeDatabase(),
    });
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
        const detail = `${value.tracks_deleted} треков · ${value.feature_rows_deleted} features · ${value.embedding_rows_deleted} embeddings · ${value.classifier_rows_deleted} classifiers`;
        appendActivity("ok", "База очищена", detail);
        return detail;
      }
    );
  }

  async function handleDeleteTrack(track: TrackDetail) {
    await run(
      async () => {
        const result = await api.deleteTrack(track);
        cancelTrackDetailRequest();
        resetSearchPlaylistState();
        appendActivity("ok", "Трек удалён из базы", displayTrack(track));
        return result;
      },
      () => displayTrack(track),
      { refreshLibrary: true, refreshSummary: true },
    );
  }

  async function handleResetAnalysis(adapter: ResetAdapter) {
    const label = adapter.toUpperCase();
    appendActivity("warn", `${label} reset запущен`, "Точечная очистка результатов анализа");
    await run(
      () => api.resetAnalysis(adapter),
      (result) => {
        appendActivity("ok", `${label} reset завершен`, `features ${result.feature_rows_deleted} · embeddings ${result.embedding_rows_deleted} · classifiers ${result.classifier_rows_deleted}`);
        return `${label}: features ${result.feature_rows_deleted}, embeddings ${result.embedding_rows_deleted}, classifiers ${result.classifier_rows_deleted}`;
      },
      { refreshLibrary: true, refreshSummary: true }
    );
  }

  function togglePanel(panel: CollapsiblePanel) {
    const setter = panel === "setup" ? setSetupCollapsed : setLibraryCollapsed;
    setter((collapsed) => {
      storePanelCollapsed(panel, !collapsed);
      return !collapsed;
    });
  }

  async function handleCancelAnalyze() {
    if (analysisPipelineJob && ["queued", "running"].includes(analysisPipelineJob.state)) {
      await run(
        () => api.cancelAnalysisPipeline(analysisPipelineJob.job_id),
        (job) => {
          setAnalysisPipelineJob(job);
          appendActivity("warn", "Pipeline cancel requested", job.job_id.slice(0, 8));
          return `Cancel requested: ${job.job_id.slice(0, 8)}`;
        }
      );
      return;
    }
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

  async function handleCancelDatabaseValidation() {
    if (!databaseValidationJob) return;
    await run(
      () => api.cancelDatabaseValidation(databaseValidationJob.job_id),
      (job) => {
        setDatabaseValidationJob(job);
        appendActivity("warn", "Database validation cancel requested", job.job_id.slice(0, 8));
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
      return;
    }
    if (databaseValidationRunning) {
      await handleCancelDatabaseValidation();
      return;
    }
  }

  async function handleShutdownServer() {
    setBusy(true);
    appendActivity("warn", "Остановка сервера запрошена");
    try {
      await shutdownApplication({
        requestShutdown: api.shutdownServer,
        onAcknowledged: () => setServerShutdownAccepted(true),
        closeWindow: () => window.close(),
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      setNotice({ kind: "error", text: message });
      appendActivity("error", "Ошибка", message);
    } finally {
      setBusy(false);
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
    await run(() => api.exportPlaylist(playlistName || "seamless-set", playlist.map((track) => track.track_id), outputDir.trim(), format), (value) => {
      appendActivity("ok", `Экспорт ${format.toUpperCase()}`, value.path);
      return value.path;
    });
  }

  async function handleSavePlaylistToRhythmLabCollection() {
    if (!playlist.length) {
      setNotice({ kind: "error", text: "Сет пуст" });
      return;
    }
    const defaultName = playlistName.trim() || `Collection ${new Date().toISOString().slice(0, 10)}`;
    const name = window.prompt("Rhythm Lab collection name", defaultName)?.trim();
    if (!name) return;
    await run(
      () => api.saveRhythmLabCollection(name, playlist, "append"),
      (value) => {
        appendActivity("ok", "Rhythm Lab collection", `${value.name} · ${value.track_count} tracks`);
        return `Collection saved: ${value.name}`;
      }
    );
  }

  async function handleGenreTagsApply() {
    if (!librarySummary.maest_analysis) {
      setNotice({ kind: "error", text: "Нет MAEST жанров для записи" });
      return;
    }
    const targetText = `${librarySummary.maest_analysis} MAEST треков`;
    appendActivity("warn", "Запись жанров в теги файлов запущена", `${targetText} · standard Genre`);
    setProcessLogKind("genre_tags");
    setGenreTagJob(null);
    await run(() => api.genreTagJobStart(), (job) => {
      setGenreTagJob(job);
      appendActivity("ok", "Genre tag job создан", `${job.job_id.slice(0, 8)} · ${job.total} треков`);
      return `Genre tag job ${job.job_id.slice(0, 8)}: ${job.total} треков`;
    });
  }

  async function handleToggleTrackLiked(track: Track): Promise<Track | null> {
    if (databaseCatalogUuidRef.current !== track.catalog_uuid) return null;
    const nextLiked = !track.liked;
    try {
      const updated = await api.setTrackLiked(track, nextLiked);
      if (
        databaseCatalogUuidRef.current !== track.catalog_uuid
        || !sameTrackIdentity(track, updated)
      ) return null;
      updateTrackLiked(updated);
      setPlaylist((current) => current.map((item) => (sameTrackIdentity(item, updated) ? updated : item)));
      setResults((current) => current.map((item) => (
        sameTrackIdentity(item.track, updated) ? { ...item, track: updated } : item
      )));
      setSeedTracks((current) => current.map((item) => (sameTrackIdentity(item, updated) ? updated : item)));
      appendActivity(updated.liked ? "ok" : "warn", updated.liked ? "Трек лайкнут" : "Лайк снят", displayTrack(updated));
      return updated;
    } catch (error) {
      if (databaseCatalogUuidRef.current !== track.catalog_uuid) return null;
      const message = error instanceof Error ? error.message : String(error);
      setNotice({ kind: "error", text: message });
      appendActivity("error", "Не удалось изменить лайк", message);
      return null;
    }
  }

  function toggleTheme() {
    setTheme((current) => current === "dark" ? "light" : "dark");
  }

  async function handleLaunchRhythmLab() {
    const pendingWindow = window.open("about:blank", "_blank");
    if (pendingWindow) pendingWindow.opener = null;
    setBusy(true);
    try {
      const result = await api.launchRhythmLab();
      setRhythmLabStatus({
        running: true,
        managed: result.managed,
        url: result.url,
        source: result.source
      });
      const opened = openRhythmLabWindow(result, pendingWindow);
      const status = result.already_running ? "Rhythm Lab уже запущен" : "Rhythm Lab запущен";
      setNotice({ kind: "ok", text: opened ? status : `${status}: ${result.url}` });
      appendActivity("ok", status, result.source ? `source ${result.source.database_path}` : result.url);
    } catch (error) {
      pendingWindow?.close();
      const message = error instanceof Error ? error.message : String(error);
      setNotice({ kind: "error", text: message });
      appendActivity("error", "Не удалось запустить Rhythm Lab", message);
    } finally {
      setBusy(false);
    }
  }

  if (serverShutdownAccepted) {
    return (
      <main className="app-shell shutdown-complete-screen">
        <section className="shutdown-complete-card" role="status">
          <Power size={30} />
          <h1>Остановка сервера запрошена</h1>
          <p>Перед повторным запуском дождитесь завершения работы сервера в консоли. Если вкладка не закрылась автоматически, её можно закрыть вручную.</p>
        </section>
      </main>
    );
  }

  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <h1>
            <a href="/docs/" target="_blank" rel="noreferrer" title="Открыть HTML документацию" onClick={openDocumentationWindow}>
              <AudioLines className="brand-wave" size={34} aria-hidden="true" />
              DJ Track Similarity
            </a>
          </h1>
        </div>
        <nav className="workbench-nav" aria-label="Рабочая область">
          <button type="button" aria-pressed={!setupCollapsed && !libraryCollapsed} onClick={() => { setSetupCollapsed(false); setLibraryCollapsed(false); }}>DISCOVER</button>
          <button type="button" aria-pressed={!setupCollapsed && libraryCollapsed} onClick={() => { setSetupCollapsed(false); setLibraryCollapsed(true); }}>ANALYZE</button>
          <button type="button" aria-pressed={setupCollapsed && !libraryCollapsed} onClick={() => { setSetupCollapsed(true); setLibraryCollapsed(false); }}>LIBRARY</button>
          <button type="button" aria-pressed={setupCollapsed && libraryCollapsed} onClick={() => { setSetupCollapsed(true); setLibraryCollapsed(true); }}>SEARCH</button>
        </nav>
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
            className="icon-button server-shutdown-button"
            title="Остановить все серверы и закрыть вкладку"
            aria-label="Остановить все серверы и закрыть вкладку"
            disabled={busy}
            onClick={() => void handleShutdownServer()}
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
          <span className={`process-indicator ${stageRunning ? "running" : ""}`} title={stageIndicatorLabel(scanJob, analysisJob, genreTagJob, databaseOptimizationJob)} aria-label={stageIndicatorLabel(scanJob, analysisJob, genreTagJob, databaseOptimizationJob)}>
            <RefreshCcw size={17} />
          </span>
          <div className={`notice ${notice.kind}`}>{notice.text}</div>
        </div>
      </header>

      <section
        className={`workspace ${setupCollapsed ? "setup-collapsed" : ""} ${libraryCollapsed ? "library-collapsed" : ""}`}
      >
        <LibraryPanel
          collapsed={setupCollapsed}
          onToggleCollapsed={() => togglePanel("setup")}
          databasePath={databasePath}
          onChooseDatabase={() => void handleChooseDatabase()}
          busy={busy}
          stageRunning={stageRunning}
          hasTracks={hasTracks}
          libraryTrackCount={librarySummary.tracks}
          maestGenreTrackCount={librarySummary.maest_analysis}
          analysisLimit={analysisLimit}
          onAnalysisLimitChange={setAnalysisLimit}
          helpText={helpText}
          onOpenScanDialog={() => setScanImportOpen(true)}
          onOpenSonaraSettingsDialog={() => setSonaraSettingsDialogOpen(true)}
          onOpenMLSettingsDialog={() => setMlSettingsDialogOpen(true)}
          onRefreshTags={() => void handleRefreshTags()}
          onWriteMaestGenres={() => void handleGenreTagsApply()}
          onClearDatabase={() => requestConfirmation({
            title: "Очистить базу?",
            message: "Удалить все данные из SQLite базы: треки, анализы, эмбеддинги и текущий сет? Аудиофайлы на диске останутся.",
            onConfirm: () => handleClearDatabase()
          })}
          onValidateDatabase={() => void handleValidateDatabase()}
          onOpenAudioDedup={() => setAudioDedupOpen(true)}
          rhythmLabRunning={rhythmLabRunning}
          onLaunchRhythmLab={() => void handleLaunchRhythmLab()}
          analysisCounts={analysisModelCounts}
          selectedStages={selectedStages}
          onToggleStage={toggleStage}
          scanRootSelected={Boolean(scanImportSettings.root.trim())}
          onStart={() => void handleStageStart()}
          onResetAnalysis={(adapter) => requestConfirmation({
            title: `Сбросить ${adapter.toUpperCase()}?`,
            message: `Сбросить результаты ${adapter.toUpperCase()}? Аудиофайлы не трогаем, остальные алгоритмы останутся.`,
            onConfirm: () => handleResetAnalysis(adapter)
          })}
        />

        <TrackPanel
          collapsed={libraryCollapsed}
          onToggleCollapsed={() => togglePanel("library")}
          databaseSelected={Boolean(databasePath && databaseCatalogUuid)}
          query={query}
          onQueryChange={setQuery}
          searchMode={searchMode}
          onSearchModeChange={setSearchMode}
          libraryPreset={libraryPreset}
          onToggleLibraryPreset={toggleLibraryPreset}
          likedOnly={likedOnly}
          likedTrackCount={librarySummary.liked}
          onToggleLikedOnly={toggleLikedOnly}
          libraryPlaybackShuffle={libraryPlaybackShuffle}
          onToggleLibraryPlaybackShuffle={() => setLibraryPlaybackShuffle((current) => !current)}
          librarySortDirection={librarySortDirection}
          onToggleLibrarySortDirection={toggleLibrarySortDirection}
          loadError={libraryError}
          playingTrackId={playingTrackId}
          previewTrackId={preview?.track_id ?? null}
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
          onSeekPreview={seekPreview}
          onDetails={(track) => void handleTrackDetails(track)}
        />

        <SearchPlaylistPanel
          seedTracks={seedTracks}
          onActivity={appendActivity}
          textQuery={textQuery}
          textNegativeQuery={textNegativeQuery}
          textUseNegativePrompt={textUseNegativePrompt}
          onTextUseNegativePromptChange={setTextUseNegativePrompt}
          textEmbeddingFamily={textEmbeddingFamily}
          onTextEmbeddingFamilyChange={changeTextEmbeddingFamily}
          seedEmbeddingFamily={seedEmbeddingFamily}
          onSeedEmbeddingFamilyChange={setSeedEmbeddingFamily}
          textCompareModels={textCompareModels}
          textModelLoadingLabel={textModelLoadingLabel}
          onTextCompareModelsChange={setTextCompareModels}
          selectedPresetKeys={selectedPresetKeys}
          onTogglePreset={togglePromptPreset}
          onClearPresets={clearPromptPresets}
          promptAxes={textPromptAxes}
          promptPresets={textPromptPresets}
          promptNegativeWeight={promptNegativeWeight}
          textExecution={textFeedbackContext}
          databaseIdentity={databaseCatalogUuid}
          busy={busy || genericSearchPending || randomSonaraTrackPending || randomEmbeddingTrackPending || !databasePath}
          filters={filters}
          setFilters={setFilters}
          seeds={seeds}
          results={results}
          genericSearchInputKey={genericSearchInputKey}
          genericSearchResultKey={genericSearchResultState?.requestKey || ""}
          genericSearchResultOrigin={genericSearchResultState?.origin || null}
          textFeedback={
            genericSearchResultState?.origin === "text" && textFeedbackContext?.feedback_capability === "ready" && feedbackReady[textFeedbackContext.run_id]
              ? {
                  verdicts: textFeedbackVerdicts[textEmbeddingFamily] ?? {},
                  pending: Object.fromEntries(Object.entries(feedbackPending).filter(([key]) => key.startsWith(`${textFeedbackContext.run_id}:`)).map(([key, value]) => [key.slice(textFeedbackContext.run_id.length + 1), value])),
                  onVerdict: (track: Track, verdict: 1 | -1) =>
                    handleTextResultFeedback(track, verdict, textEmbeddingFamily)
                }
              : null
          }
          textComparison={
            genericSearchResultState?.origin === "text" && textComparison
              ? textComparison.map((column) => ({
                  ...column,
                  verdicts: textFeedbackVerdicts[column.family] ?? {},
                  pending: Object.fromEntries(Object.entries(feedbackPending).filter(([key]) => key.startsWith(`${column.execution?.run_id}:`)).map(([key, value]) => [key.slice((column.execution?.run_id.length ?? 0) + 1), value])),
                  onVerdict: executions[column.family]?.feedback_capability === "ready" && !!feedbackReady[column.execution?.run_id ?? ""]
                    ? (track: Track, verdict: 1 | -1) =>
                        handleTextResultFeedback(track, verdict, column.family)
                    : undefined
                }))
              : null
          }
          onPrimarySearchTabChange={handlePrimarySearchTabChange}
          seedSet={seedSet}
          playlistSet={playlistSet}
          playlist={playlist}
          playlistName={playlistName}
          onPlaylistNameChange={setPlaylistName}
          outputDir={outputDir}
          onOutputDirChange={setOutputDir}
          onChooseOutputFolder={() => void handleChooseOutputFolder()}
          helpText={helpText}
          embeddingCounts={{
            mert: librarySummary.mert,
            maest: librarySummary.maest_embedding,
            muq: librarySummary.muq,
            mulan: librarySummary.mulan,
            clap: librarySummary.clap
          }}
          classifiers={classifiers}
          classifierMinScores={classifierMinScores}
          onClassifierMinScoreChange={(classifier, value) =>
            setClassifierMinScores((current) => ({ ...current, [classifier]: value }))
          }
          onAnalyzeClassifier={handleAnalyzeClassifier}
          onResetClassifier={(classifier) => requestConfirmation({
            title: `Удалить результаты ${classifier.name}?`,
            message: "Будут удалены только рассчитанные score этого классификатора. Аудиофайлы и результаты других классификаторов останутся.",
            onConfirm: () => handleResetClassifier(classifier)
          })}
          classifierJob={classifiers.some((classifier) => classifier.classifier_key === analysisJob?.adapter_name) ? analysisJob : null}
          removeSeed={removeSeed}
          handleTextSearch={() => void handleTextSearch(searchRequests)}
          handleSonaraSearch={() => void handleSonaraSearch()}
          handleAddRandomSonaraTrack={() => void handleAddRandomSonaraTrack()}
          handleAddRandomEmbeddingTrack={() => void handleAddRandomEmbeddingTrack()}
          handleEmbeddingSearch={handleEmbeddingSearch}
          addSeed={addSeed}
          toggleLiked={handleToggleTrackLiked}
          togglePlaylist={togglePlaylist}
          onAddPromptCandidates={addPromptCandidatesToPlaylist}
          playingTrackId={playingTrackId}
          previewTrackId={preview?.track_id ?? null}
          setPreview={togglePreview}
          onSeekPreview={seekPreview}
          setMetadataTrack={(track) => void handleTrackDetails(track)}
          removeFromPlaylist={removeFromPlaylist}
          handleSaveToCollection={() => void handleSavePlaylistToRhythmLabCollection()}
          handleExport={(format) => void handleExport(format)}
        />
      </section>
      <PlayerDock preview={preview} playing={preview != null && playingTrackId === preview.track_id} audioRef={previewAudioRef} onToggle={togglePreview} onSeek={seekPreview} />
      {preview ? (
        <audio
          ref={previewAudioRef}
          hidden
          src={`/media/${preview.track_id}`}
          onPlay={() => {
            if (playingTrackId === preview.track_id) markPreviewPlaying(preview.track_id);
          }}
          onPause={() => markPreviewPaused(preview.track_id)}
          onEnded={() => {
            handleLibraryPreviewEnded(preview);
          }}
          onDurationChange={() => updatePreviewPosition(preview.track_id)}
          onTimeUpdate={() => updatePreviewPosition(preview.track_id)}
        />
      ) : null}
      {metadataTrack && (
        <TrackMetadataDialog
          track={metadataTrack}
          sonaraBpmRange={sonaraBpmRangeLocked ? sonaraBpmRange : null}
          onClose={() => setMetadataTrack(null)}
          onDelete={(track) => requestConfirmation({
            title: "Удалить трек из базы?",
            message: `Будут удалены трек и все связанные данные SQLite. Аудиофайл ${displayTrack(track)} на диске останется.`,
            onConfirm: () => handleDeleteTrack(track),
          })}
          onPreview={togglePreview}
          playingTrackId={playingTrackId}
        />
      )}
      {scanImportOpen && (
        <ScanImportDialog
          settings={scanImportSettings}
          onSettingsChange={setScanImportSettings}
          busy={busy}
          stageRunning={stageRunning}
          maxWorkers={maxScanWorkers}
          onChooseFolder={handleChooseScanFolder}
          onClose={() => setScanImportOpen(false)}
        />
      )}
      {sonaraSettingsDialogOpen && (
        <SonaraAnalysisSettingsDialog
          busy={busy}
          stageRunning={stageRunning}
          sonaraSettings={sonaraSettings}
          onSonaraSettingsChange={setSonaraSettings}
          sonaraBpmRange={sonaraBpmRange}
          sonaraBpmRangeLocked={sonaraBpmRangeLocked}
          onSonaraBpmRangeChange={(range) => setSonaraSettings((current) => ({ ...current, ...range }))}
          onChooseSonaraStagingFolder={() => void handleChooseStagingFolder()}
          onClose={() => setSonaraSettingsDialogOpen(false)}
        />
      )}
      {mlSettingsDialogOpen && (
        <MLAnalysisSettingsDialog
          busy={busy}
          stageRunning={stageRunning}
          hasTracks={hasTracks}
          mlSettings={mlSettings}
          onMLSettingsChange={setMlSettings}
          onChooseMLStagingFolder={() => void handleChooseMLStagingFolder()}
          analysisDevice={analysisDevice}
          onAnalysisDeviceChange={setAnalysisDevice}
          analysisTrackBatchSize={analysisTrackBatchSize}
          maxAnalysisTrackBatchSize={maxAnalysisTrackBatchSize}
          onAnalysisTrackBatchSizeChange={setAnalysisTrackBatchSize}
          analysisInferenceBatchSize={analysisInferenceBatchSize}
          maxAnalysisInferenceBatchSize={maxAnalysisInferenceBatchSize}
          onAnalysisInferenceBatchSizeChange={setAnalysisInferenceBatchSize}
          onClose={() => setMlSettingsDialogOpen(false)}
        />
      )}
      {scanImportStartToast && (
        <div className="scan-import-start-toast" role="status" aria-live="polite">Подготавливаем список треков…</div>
      )}
      {confirmation && (
          <ConfirmationDialog
            request={confirmation}
            onConfirm={confirmPendingAction}
            onCancel={cancelConfirmation}
          />
      )}
      {logFrameOpen && (
        <LogFrameDialog
          processLogKind={processLogKind}
          scanJob={scanJob}
          analysisJob={analysisJob}
          genreTagJob={genreTagJob}
          databaseValidationJob={databaseValidationJob}
          databaseOptimizationJob={databaseOptimizationJob}
          activityLog={activityLog}
          onClose={() => setLogFrameOpen(false)}
        />
      )}
      <AudioDedupDialog
        open={audioDedupOpen}
        playingTrackId={playingTrackId}
        onPreview={(file) => togglePreview({ track_id: file.track_id })}
        onClose={() => setAudioDedupOpen(false)}
        onDeleted={(message) => {
          setNotice({ kind: "ok", text: message });
          appendActivity("info", message);
          void refreshLibrary(0, { refreshSummary: true });
        }}
      />
      <TooltipLayer tooltip={tooltip} />
    </main>
  );
}

function isAbortError(error: unknown) {
  return error instanceof Error && error.name === "AbortError";
}
