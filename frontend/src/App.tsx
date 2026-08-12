import type { MouseEvent } from "react";
import { useEffect, useMemo, useRef, useState } from "react";
import { FlaskConical, Moon, Power, RefreshCcw, ScrollText, Square, Sun } from "lucide-react";
import {
  AnalysisJobStatus,
  AnalysisModel,
  AnalysisPipelineStatus,
  api,
  EmbeddingSource,
  GenreTagJobStatus,
  PromotedClassifier,
  RhythmLabLaunchResult,
  RhythmLabStatus,
  ScanStats,
  Track,
} from "./api";
import {
  analysisSelectionOrder,
  analysisStartBlockedByMissingSonara,
  defaultAnalysisSelections,
  type AnalysisSelection
} from "./analysisSelection";
import { clapPromptPresets, defaultClapPromptPresetKey, promptQueriesFromText } from "./clapPrompt";
import { classifierIsAvailable, classifierScoringBlockedReason } from "./classifierCompatibility";
import { ConfirmationDialog, LogFrameDialog } from "./dialogs";
import { exportDirectoryError } from "./exportView";
import { helpText } from "./helpText";
import { analysisJobRequest, cancelAnalysisJob, scanSummary, stageIndicatorLabel } from "./jobUi";
import { LibraryPanel } from "./LibraryPanel";
import { appendVisibleTracksToPlaylist } from "./libraryView";
import { SearchPlaylistPanel, type SearchFiltersState } from "./SearchPlaylistPanel";
import {
  createRequestTokenGuard,
  type GenericSearchTab,
  type PrimarySearchTab,
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

type Notice = { kind: "ok" | "error" | "idle"; text: string };
type DeviceMode = "auto" | "cpu" | "cuda";
type ResetAdapter = AnalysisModel;
type GenericSearchResultState = {
  origin: GenericSearchTab;
  requestKey: string;
};
type GuardedRequestTicket = {
  token: number;
  requestKey: string;
  controller: AbortController;
};

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
    filteredTracks,
    updateTrackLiked
  } = useLibraryState({
    databaseSelected: Boolean(databasePath),
    databaseKey: databaseCatalogUuid
  });
  const {
    textQuery,
    setTextQuery,
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
  const [clapNegativeQuery, setClapNegativeQuery] = useState("");
  const [clapUseNegativePrompt, setClapUseNegativePrompt] = useState(true);
  const [classifiers, setClassifiers] = useState<PromotedClassifier[]>([]);
  const [musicRoot, setMusicRoot] = useState("");
  const [analysisJob, setAnalysisJob] = useState<AnalysisJobStatus | null>(null);
  const [analysisPipelineJob, setAnalysisPipelineJob] = useState<AnalysisPipelineStatus | null>(null);
  const [scanJob, setScanJob] = useState<ScanStats | null>(null);
  const [genreTagJob, setGenreTagJob] = useState<GenreTagJobStatus | null>(null);
  const [rhythmLabStatus, setRhythmLabStatus] = useState<RhythmLabStatus | null>(null);
  const [processLogKind, setProcessLogKind] = useState<"scan" | "analysis" | "genre_tags">("scan");
  const [analysisLimit, setAnalysisLimit] = useState(0);
  const [scanWorkers, setScanWorkers] = useState(8);
  const [analysisTrackBatchSize, setAnalysisTrackBatchSize] = useState(8);
  const [analysisInferenceBatchSize, setAnalysisInferenceBatchSize] = useState(16);
  const [sonaraBatchSize, setSonaraBatchSize] = useState(8);
  const [analysisDevice, setAnalysisDevice] = useState<DeviceMode>("auto");
  const [selectedAnalysisModels, setSelectedAnalysisModels] = useState<AnalysisSelection[]>(defaultAnalysisSelections);
  const [notice, setNotice] = useState<Notice>(defaultNotice);
  const [logFrameOpen, setLogFrameOpen] = useState(false);
  const [theme, setTheme] = useState<ThemeMode>(() => resolveInitialTheme());
  const { confirmation, requestConfirmation, confirmPendingAction, cancelConfirmation } = useConfirmation();
  const [busy, setBusy] = useState(false);
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
  const genericSearchRequestGuard = useRef(createRequestTokenGuard());
  const genericSearchAbortController = useRef<AbortController | null>(null);
  const [genericSearchPending, setGenericSearchPending] = useState(false);
  const [randomSonaraTrackPending, setRandomSonaraTrackPending] = useState(false);
  const [genericSearchResultState, setGenericSearchResultState] = useState<GenericSearchResultState | null>(null);
  const [previewPosition, setPreviewPosition] = useState({
    trackId: null as number | null,
    currentTime: 0,
    duration: 0,
  });
  const previewAudioRef = useRef<HTMLAudioElement | null>(null);
  const genericSearchInputKey = useMemo(
    () => JSON.stringify({
      database_path: databasePath,
      catalog_uuid: databaseCatalogUuid,
      seed_identities: seedTracks.map((track) => ({
        track_id: track.track_id,
        track_uuid: track.track_uuid,
      })),
      filters,
      text_query: textQuery,
      clap_negative_query: clapNegativeQuery,
      clap_use_negative_prompt: clapUseNegativePrompt,
      clap_preset_key: clapPresetKey,
      clap_device: analysisDevice,
    }),
    [
      analysisDevice,
      clapNegativeQuery,
      clapPresetKey,
      clapUseNegativePrompt,
      databaseCatalogUuid,
      databasePath,
      filters,
      seedTracks,
      textQuery,
    ]
  );
  const genericSearchInputKeyRef = useRef(genericSearchInputKey);
  const trackDetailRequestGuard = useRef(createRequestTokenGuard());
  const trackDetailAbortController = useRef<AbortController | null>(null);

  const scanRunning = Boolean(scanJob?.state && ["queued", "running"].includes(scanJob.state));
  const analysisRunning = Boolean(
    (analysisJob && ["queued", "running"].includes(analysisJob.state))
    || (analysisPipelineJob && ["queued", "running"].includes(analysisPipelineJob.state))
  );
  const genreTagRunning = Boolean(genreTagJob && ["queued", "running"].includes(genreTagJob.state));
  const stageRunning = scanRunning || analysisRunning || genreTagRunning;
  const rhythmLabRunning = Boolean(rhythmLabStatus?.running);
  const logHasErrors = useMemo(() => {
    const hasErrorEvent = activityLog.some((event) => event.level === "error")
      || (scanJob?.events || []).some((event) => event.level === "error")
      || (analysisJob?.events || []).some((event) => event.level === "error")
      || (genreTagJob?.events || []).some((event) => event.level === "error");
    return hasErrorEvent || Boolean(analysisJob?.errors.length) || Boolean(genreTagJob?.errors.length);
  }, [activityLog, analysisJob, genreTagJob, scanJob]);
  const canStartScan = Boolean(databasePath && musicRoot);
  const analysisModelCounts: Record<AnalysisSelection, number> = {
    sonara: librarySummary.sonara,
    maest: librarySummary.maest_analysis,
    mert: librarySummary.mert,
    muq: librarySummary.muq,
    clap: librarySummary.clap
  };
  const maxScanWorkers = useMemo(() => optimalWorkerLimit(), []);
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
    genericSearchInputKeyRef.current = genericSearchInputKey;
    cancelGenericSearchRequest();
    setGenericSearchResultState(null);
    setResults([]);
  }, [genericSearchInputKey]);

  useEffect(() => {
    cancelTrackDetailRequest();
  }, [databaseCatalogUuid]);

  useEffect(() => () => {
    genericSearchAbortController.current?.abort();
    trackDetailAbortController.current?.abort();
  }, []);

  useEffect(() => {
    setPreviewPosition({
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

  useEffect(() => {
    if (!scanJob?.job_id || !["queued", "running"].includes(scanJob.state || "")) return;
    const timer = window.setInterval(() => {
      void api.scanJob(scanJob.job_id!).then((job) => {
        setScanJob(job);
        if (["completed", "cancelled", "failed"].includes(job.state || "")) {
          void refreshLibrary(0, { refreshSummary: true });
          refreshClassifierProfilesInBackground();
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
          void refreshLibrary(0, { refreshSummary: true });
          refreshClassifierProfilesInBackground();
        }
      }).catch((error) => {
        setNotice({ kind: "error", text: error instanceof Error ? error.message : String(error) });
      });
    }, 1500);
    return () => window.clearInterval(timer);
  }, [analysisJob?.job_id, analysisJob?.state]);

  useEffect(() => {
    if (!analysisPipelineJob || !["queued", "running"].includes(analysisPipelineJob.state)) return;
    const timer = window.setInterval(() => {
      void api.analysisPipeline(analysisPipelineJob.job_id).then((job) => {
        setAnalysisPipelineJob(job);
        const currentStage = job.current_stage;
        const childJobId = currentStage ? job.stages[currentStage]?.child_job_id : null;
        if (childJobId) {
          void api.analysisJob(childJobId).then(setAnalysisJob).catch((error) => {
            setNotice({ kind: "error", text: error instanceof Error ? error.message : String(error) });
          });
        }
        if (["completed", "cancelled", "failed"].includes(job.state)) {
          void refreshLibrary(0, { refreshSummary: true });
          refreshClassifierProfilesInBackground();
        }
      }).catch((error) => {
        setNotice({ kind: "error", text: error instanceof Error ? error.message : String(error) });
      });
    }, 1500);
    return () => window.clearInterval(timer);
  }, [analysisPipelineJob?.job_id, analysisPipelineJob?.state]);

  useEffect(() => {
    if (!genreTagJob || !["queued", "running"].includes(genreTagJob.state)) return;
    const timer = window.setInterval(() => {
      void api.genreTagJob(genreTagJob.job_id).then((job) => {
        setGenreTagJob(job);
        if (["completed", "cancelled", "failed"].includes(job.state)) {
          void refreshLibrary(0, { refreshSummary: true });
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
      api.latestAnalysisPipeline().then((job) => {
        if (job) setAnalysisPipelineJob(job);
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
    cancelGenericSearchRequest();
    cancelTrackDetailRequest();
    resetLibraryState();
    setDatabaseCatalogUuid(null);
    setMusicRoot("");
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

  function beginGenericSearchRequest(): GuardedRequestTicket {
    genericSearchAbortController.current?.abort();
    const controller = new AbortController();
    const ticket = {
      token: genericSearchRequestGuard.current.begin(),
      requestKey: genericSearchInputKeyRef.current,
      controller,
    };
    genericSearchAbortController.current = controller;
    setGenericSearchPending(true);
    setGenericSearchResultState(null);
    setResults([]);
    return ticket;
  }

  function genericSearchRequestIsCurrent(ticket: GuardedRequestTicket) {
    return (
      genericSearchRequestGuard.current.isCurrent(ticket.token)
      && genericSearchInputKeyRef.current === ticket.requestKey
    );
  }

  function commitGenericSearchResults(
    ticket: GuardedRequestTicket,
    origin: GenericSearchTab,
    value: Awaited<ReturnType<typeof api.search>>
  ) {
    if (!genericSearchRequestIsCurrent(ticket)) return false;
    setResults(value);
    setGenericSearchResultState({
      origin,
      requestKey: ticket.requestKey,
    });
    return true;
  }

  function finishGenericSearchRequest(ticket: GuardedRequestTicket) {
    if (!genericSearchRequestIsCurrent(ticket)) return;
    if (genericSearchAbortController.current === ticket.controller) {
      genericSearchAbortController.current = null;
    }
    setGenericSearchPending(false);
  }

  function cancelGenericSearchRequest() {
    genericSearchRequestGuard.current.invalidate();
    genericSearchAbortController.current?.abort();
    genericSearchAbortController.current = null;
    setGenericSearchPending(false);
  }

  function handlePrimarySearchTabChange(tab: PrimarySearchTab) {
    cancelGenericSearchRequest();
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
    setPreviewPosition({
      trackId,
      currentTime: Math.min(Math.max(0, audio.currentTime), duration || 0),
      duration,
    });
  }

  function seekPreview(track: Track, seconds: number) {
    const audio = previewAudioRef.current;
    if (!audio || preview?.track_id !== track.track_id) return;
    const duration = Number.isFinite(audio.duration) ? Math.max(0, audio.duration) : 0;
    audio.currentTime = Math.min(Math.max(0, seconds), duration);
    updatePreviewPosition(track.track_id);
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

  function toggleAnalysisModel(model: AnalysisSelection) {
    setSelectedAnalysisModels((current) => {
      if (current.length === 1 && current.includes(model)) return current;
      if (model === "sonara") {
        return [model];
      }
      const mlSelections = current.filter((item) => item !== "sonara");
      const next: AnalysisSelection[] = mlSelections.includes(model)
        ? mlSelections.filter((item) => item !== model)
        : [...mlSelections, model];
      return next.length
        ? analysisModelOrder.filter((item) => next.includes(item))
        : current;
    });
  }

  async function addVisibleTracksToPlaylist() {
    if (!databasePath || libraryLoading) return;
    setBusy(true);
    try {
      const filtered = await filteredTracks();
      const nextPlaylist = appendVisibleTracksToPlaylist(playlist, filtered);
      const added = nextPlaylist.length - playlist.length;
      if (!added) {
        setNotice({ kind: "idle", text: "Все отфильтрованные треки уже в сете" });
        return;
      }
      setPlaylist(nextPlaylist);
      appendActivity("ok", "Отфильтрованная библиотека добавлена в сет", `${added} новых · всего найдено ${filtered.length}`);
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
    const customMode = filters.sonaraMode === "custom";
    const ticket = beginGenericSearchRequest();
    appendActivity("info", "SONARA search запущен", `${filters.sonaraMode} · ${seeds.length} seed`);
    try {
      const value = await api.sonaraSearch({
        seed_track_ids: seeds,
        limit: filters.limit,
        mode: filters.sonaraMode,
        mixer_weights: customMode ? filters.sonaraMixer : null,
        modifiers: customMode ? filters.sonaraModifiers : null,
      }, {
        signal: ticket.controller.signal,
      });
      if (commitGenericSearchResults(ticket, "sonara", value)) {
        appendActivity("ok", "SONARA search завершен", `Найдено: ${value.length}`);
        setNotice({ kind: "ok", text: `Найдено: ${value.length}` });
      }
    } catch (error) {
      if (!genericSearchRequestIsCurrent(ticket) || isAbortError(error)) return;
      const message = error instanceof Error ? error.message : String(error);
      setNotice({ kind: "error", text: message });
      appendActivity("error", "SONARA search недоступен", message);
    } finally {
      finishGenericSearchRequest(ticket);
    }
  }

  async function handleAddRandomSonaraTrack() {
    if (randomSonaraTrackPending) return;
    setRandomSonaraTrackPending(true);
    appendActivity("info", "Добавление случайного SONARA seed", `Исключено текущих seed: ${seeds.length}`);
    try {
      const track = await api.randomSonaraTrack({
        exclude_track_ids: seeds,
      });
      addSeed(track);
      const selected = displayTrack(track);
      appendActivity("ok", "Добавлен случайный SONARA seed", selected);
      setNotice({ kind: "ok", text: `Добавлен seed: ${selected}` });
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      setNotice({ kind: "error", text: message });
      appendActivity("error", "Не удалось добавить случайный SONARA seed", message);
    } finally {
      setRandomSonaraTrackPending(false);
    }
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

  async function handleEmbeddingSearch(analysisFamily: EmbeddingSource) {
    if (!seeds.length) {
      const error = new Error("Выберите от 1 до 5 уникальных seed-треков");
      setNotice({ kind: "error", text: error.message });
      throw error;
    }
    if (analysisFamily !== "mert" && analysisFamily !== "muq") {
      throw new Error(`Unsupported embedding search tab: ${analysisFamily}`);
    }
    const label = analysisFamily.toUpperCase();
    const ticket = beginGenericSearchRequest();
    appendActivity("info", `${label} search запущен`, `${seeds.length} seed`);
    try {
      const value = await api.search({
        analysis_family: analysisFamily,
        seed_track_ids: seeds,
        limit: filters.limit,
        epsilon: null,
        noise: 0,
      }, {
        signal: ticket.controller.signal,
      });
      if (commitGenericSearchResults(ticket, analysisFamily, value)) {
        appendActivity("ok", `${label} search завершен`, `Найдено: ${value.length}`);
        setNotice({ kind: "ok", text: `Найдено: ${value.length}` });
      }
    } catch (error) {
      if (!genericSearchRequestIsCurrent(ticket) || isAbortError(error)) return;
      const message = error instanceof Error ? error.message : String(error);
      setNotice({ kind: "error", text: message });
      appendActivity("error", `${label} search недоступен`, message);
      throw error;
    } finally {
      finishGenericSearchRequest(ticket);
    }
  }

  async function handleScan() {
    const limit = analysisLimit > 0 ? analysisLimit : undefined;
    appendActivity(
      "info",
      "Сканирование запущено",
      `${musicRoot} · limit ${limit ?? "all"}`,
    );
    setProcessLogKind("scan");
    setScanJob(null);
    await run(
      () => api.scan(musicRoot, scanWorkers, limit),
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
    const mlModels = selectedAnalysisModels.filter((model) => model !== "sonara");
    const includeSonara = selectedAnalysisModels.includes("sonara");
    const stages: Array<"sonara" | "ml"> = [];
    if (includeSonara) stages.push("sonara");
    if (mlModels.length) stages.push("ml");
    if (!stages.length) {
      setNotice({ kind: "error", text: "Выберите хотя бы одну стадию анализа" });
      return;
    }
    if (
      analysisStartBlockedByMissingSonara(
        selectedAnalysisModels,
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
      settings.push(`SONARA · Core · SONARA batch ${sonaraBatchSize}`);
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
          limit: limit ?? null,
          sonara: { batch_size: sonaraBatchSize },
          ml: {
            models: mlModels, device: analysisDevice, top_k: 3,
            track_batch_size: analysisTrackBatchSize, inference_batch_size: analysisInferenceBatchSize
          }
        });
      },
      (job) => {
        setAnalysisPipelineJob(job);
        appendActivity("ok", "Анализ поставлен в очередь", settings.join(" | "));
        return `Анализ: ${job.order.join(" → ")}`;
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
        const detail = `${value.tracks_deleted} треков · ${value.feature_rows_deleted} features · ${value.embedding_rows_deleted} embeddings · ${value.classifier_rows_deleted} classifiers`;
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
        appendActivity("ok", `${label} reset завершен`, `features ${result.feature_rows_deleted} · embeddings ${result.embedding_rows_deleted} · classifiers ${result.classifier_rows_deleted}`);
        return `${label}: features ${result.feature_rows_deleted}, embeddings ${result.embedding_rows_deleted}, classifiers ${result.classifier_rows_deleted}`;
      },
      { refreshLibrary: true, refreshSummary: true }
    );
  }

  async function handleTextSearch() {
    const prompt = textQuery.trim();
    if (!prompt) {
      setNotice({ kind: "error", text: "Введите текстовый запрос для CLAP" });
      return;
    }
    const manualQueries = promptQueriesFromText(prompt, clapNegativeQuery, clapUseNegativePrompt);
    const positiveQueries = manualQueries.positiveQueries;
    const negativeQueries = manualQueries.negativeQueries;
    const ticket = beginGenericSearchRequest();
    appendActivity("info", "CLAP search запущен", negativeQueries.length ? `${prompt} · negative ${negativeQueries[0]}` : prompt);
    try {
      const value = await api.textSearch({
        query: prompt,
        positive_queries: positiveQueries,
        negative_queries: negativeQueries,
        adaptive_contrast: true,
        preset: clapPresetKey,
        limit: filters.limit,
        device: analysisDevice
      }, {
        signal: ticket.controller.signal,
      });
      if (commitGenericSearchResults(ticket, "clap", value)) {
        appendActivity("ok", "CLAP search завершен", `Найдено: ${value.length}`);
        setNotice({ kind: "ok", text: `Найдено: ${value.length}` });
      }
    } catch (error) {
      if (!genericSearchRequestIsCurrent(ticket) || isAbortError(error)) return;
      const message = error instanceof Error ? error.message : String(error);
      setNotice({ kind: "error", text: message });
      appendActivity("error", "CLAP search недоступен", message);
    } finally {
      finishGenericSearchRequest(ticket);
    }
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
  }

  async function handleShutdownServer() {
    setBusy(true);
    appendActivity("warn", "Остановка сервера запрошена");
    try {
      await api.shutdownServer();
      setNotice({ kind: "idle", text: "Сервер останавливается" });
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

  function adjustScanWorkers(delta: number) {
    setScanWorkers((current) => Math.min(maxScanWorkers, Math.max(1, current + delta)));
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
    const nextLiked = !track.liked;
    try {
      const updated = await api.setTrackLiked(track, nextLiked);
      updateTrackLiked(updated);
      setPlaylist((current) => current.map((item) => (item.track_id === updated.track_id ? updated : item)));
      setResults((current) => current.map((item) => (
        item.track.track_id === updated.track_id ? { ...item, track: updated } : item
      )));
      setSeedTrackMap((current) => (
        current[updated.track_id] ? { ...current, [updated.track_id]: updated } : current
      ));
      appendActivity(updated.liked ? "ok" : "warn", updated.liked ? "Трек лайкнут" : "Лайк снят", displayTrack(updated));
      return updated;
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      setNotice({ kind: "error", text: message });
      appendActivity("error", "Не удалось изменить лайк", message);
      return null;
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

  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <h1>
            <a href="/docs/" target="_blank" rel="noreferrer" title="Открыть HTML документацию" onClick={openDocumentationWindow}>
              DJ Track Similarity
            </a>
          </h1>
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
            className={`icon-button rhythm-lab-launch-button ${rhythmLabRunning ? "active" : ""}`}
            title={rhythmLabRunning ? "Открыть Rhythm Lab" : "Запустить Rhythm Lab"}
            aria-label={rhythmLabRunning ? "Открыть Rhythm Lab" : "Запустить Rhythm Lab"}
            aria-pressed={rhythmLabRunning}
            disabled={busy}
            onClick={() => void handleLaunchRhythmLab()}
            type="button"
          >
            <FlaskConical size={16} />
          </button>
          <button
            className="icon-button server-shutdown-button"
            title="Остановить текущий сервер"
            aria-label="Остановить текущий сервер"
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
          <span className={`process-indicator ${stageRunning ? "running" : ""}`} title={stageIndicatorLabel(scanJob, analysisJob, genreTagJob)} aria-label={stageIndicatorLabel(scanJob, analysisJob, genreTagJob)}>
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
          maestGenreTrackCount={librarySummary.maest_analysis}
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
          sonaraBatchSize={sonaraBatchSize}
          onSonaraBatchSizeChange={setSonaraBatchSize}
          analysisJob={analysisJob}
          pipelineJob={analysisPipelineJob}
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
        />

        <TrackPanel
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
          librarySortDirection={librarySortDirection}
          onToggleLibrarySortDirection={toggleLibrarySortDirection}
          loadError={libraryError}
          playingTrackId={playingTrackId}
          previewTrackId={preview?.track_id ?? null}
          previewCurrentTime={previewPosition.trackId === preview?.track_id ? previewPosition.currentTime : 0}
          previewDuration={previewPosition.trackId === preview?.track_id ? previewPosition.duration : 0}
          tracks={orderedTracks}
          libraryTotalTracks={librarySummary.tracks}
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
          textQuery={textQuery}
          onTextQueryChange={setTextQuery}
          clapNegativeQuery={clapNegativeQuery}
          onClapNegativeQueryChange={setClapNegativeQuery}
          clapUseNegativePrompt={clapUseNegativePrompt}
          onClapUseNegativePromptChange={setClapUseNegativePrompt}
          clapPresetKey={clapPresetKey}
          onClapPresetChange={setClapPresetKey}
          clapPromptPresets={clapPromptPresets}
          databaseIdentity={databaseCatalogUuid}
          busy={busy || genericSearchPending || randomSonaraTrackPending || !databasePath}
          filters={filters}
          setFilters={setFilters}
          seeds={seeds}
          results={results}
          genericSearchInputKey={genericSearchInputKey}
          genericSearchResultKey={genericSearchResultState?.requestKey || ""}
          genericSearchResultOrigin={genericSearchResultState?.origin || null}
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
            clap: librarySummary.clap
          }}
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
          handleAddRandomSonaraTrack={() => void handleAddRandomSonaraTrack()}
          handleEmbeddingSearch={handleEmbeddingSearch}
          addSeed={addSeed}
          toggleLiked={handleToggleTrackLiked}
          togglePlaylist={togglePlaylist}
          playingTrackId={playingTrackId}
          previewTrackId={preview?.track_id ?? null}
          previewCurrentTime={previewPosition.trackId === preview?.track_id ? previewPosition.currentTime : 0}
          previewDuration={previewPosition.trackId === preview?.track_id ? previewPosition.duration : 0}
          setPreview={togglePreview}
          onSeekPreview={seekPreview}
          setMetadataTrack={(track) => void handleTrackDetails(track)}
          removeFromPlaylist={removeFromPlaylist}
          handleSaveToCollection={() => void handleSavePlaylistToRhythmLabCollection()}
          handleExport={(format) => void handleExport(format)}
        />
      </section>
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
            updatePreviewPosition(preview.track_id);
            markPreviewPaused(preview.track_id);
          }}
          onDurationChange={() => updatePreviewPosition(preview.track_id)}
          onTimeUpdate={() => updatePreviewPosition(preview.track_id)}
        />
      ) : null}
      {metadataTrack && (
        <TrackMetadataDialog
          track={metadataTrack}
          onClose={() => setMetadataTrack(null)}
          onPreview={togglePreview}
          playingTrackId={playingTrackId}
        />
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

function isAbortError(error: unknown) {
  return error instanceof Error && error.name === "AbortError";
}
