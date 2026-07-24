import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type Dispatch,
  type SetStateAction
} from "react";
import { api, type LibrarySummary, type Track } from "./api";
import {
  createLibraryLoadCoordinator,
  firstLibraryChunk,
  isPagedLibraryLoadSize,
  libraryChunkPlan,
  libraryLoadTarget,
  libraryPageSizeForLoadSize,
  libraryRequestKey,
  libraryTrackIdentityKey,
  libraryTracksBelongToCatalog,
  mergeLibraryTracks,
  type LibraryLoadProgress,
  type LibraryLoadSize
} from "./libraryLoading";
import {
  libraryCurrentPageNumber,
  libraryPageOffsetForNumber,
  orderedLibraryTracks,
  toggleLikedTracksFilter,
  type LibraryPreset,
  type LibrarySearchMode,
  type LibrarySortDirection
} from "./libraryView";

export const emptyLibrarySummary: LibrarySummary = {
  tracks: 0,
  sonara: 0,
  maest_analysis: 0,
  maest_embedding: 0,
  mert: 0,
  muq: 0,
  clap: 0,
  liked: 0,
  classifiers: 0
};

type RefreshLibraryOptions = {
  databaseKey?: string | null;
  loadSize?: LibraryLoadSize;
  refreshSummary?: boolean;
  selected?: boolean;
};

function activeClassifierMinScores(scores: Record<string, number>) {
  return Object.fromEntries(Object.entries(scores).filter(([, value]) => value > 0));
}

function isAbortError(error: unknown) {
  return error instanceof Error && error.name === "AbortError";
}

export function useLibraryState({
  databaseSelected,
  databaseKey
}: {
  databaseSelected: boolean;
  databaseKey: string | null;
}) {
  const [tracks, setTracks] = useState<Track[]>([]);
  const [libraryTotal, setLibraryTotal] = useState(0);
  const [libraryOffset, setLibraryOffset] = useState(0);
  const [libraryLoading, setLibraryLoading] = useState(false);
  const [libraryProgress, setLibraryProgress] = useState<LibraryLoadProgress | null>(null);
  const [libraryError, setLibraryError] = useState<string | null>(null);
  const [librarySummary, setLibrarySummary] = useState<LibrarySummary>(emptyLibrarySummary);
  const [queryState, setQueryState] = useState("");
  const [searchModeState, setSearchModeState] = useState<LibrarySearchMode>("like");
  const [libraryPreset, setLibraryPreset] = useState<LibraryPreset>("all");
  const [librarySortDirection, setLibrarySortDirection] = useState<LibrarySortDirection>("forward");
  const [likedOnly, setLikedOnly] = useState(false);
  const [classifierMinScoresState, setClassifierMinScoresState] = useState<Record<string, number>>({});
  const [libraryLoadSize, setLibraryLoadSizeState] = useState<LibraryLoadSize>(100);
  const coordinatorRef = useRef(createLibraryLoadCoordinator());
  const summaryRequestIdRef = useRef(0);
  const databaseKeyRef = useRef(databaseKey);
  const previousDatabaseScopeRef = useRef(databaseSelected ? databaseKey : null);
  databaseKeyRef.current = databaseKey;

  const orderedTracks = useMemo(
    () => orderedLibraryTracks(tracks, librarySortDirection),
    [tracks, librarySortDirection]
  );
  const hasTracks = librarySummary.tracks > 0;
  const pageSize = libraryPageSizeForLoadSize(libraryLoadSize);
  const canGoBack = pageSize != null && libraryOffset > 0 && !libraryLoading;
  const canGoForward = pageSize != null
    && libraryOffset + pageSize < libraryTotal
    && !libraryLoading;

  const cancelLibraryLoad = useCallback(() => {
    const cancelled = coordinatorRef.current.cancel();
    if (!cancelled) return false;
    setLibraryLoading(false);
    setLibraryProgress((current) => current ? { ...current, cancelled: true } : current);
    return true;
  }, []);

  const adoptDatabaseScope = useCallback((nextDatabaseKey: string | null) => {
    databaseKeyRef.current = nextDatabaseKey;
    previousDatabaseScopeRef.current = nextDatabaseKey;
  }, []);

  function clearVisibleLibraryResult() {
    setTracks([]);
    setLibraryTotal(0);
    setLibraryOffset(0);
    setLibraryProgress(null);
    setLibraryError(null);
  }

  function cancelBeforeStateChange<T>(setter: Dispatch<SetStateAction<T>>): Dispatch<SetStateAction<T>> {
    return (next) => {
      cancelLibraryLoad();
      clearVisibleLibraryResult();
      setter(next);
    };
  }

  const setQuery = cancelBeforeStateChange(setQueryState);
  const setSearchMode = cancelBeforeStateChange(setSearchModeState);
  const setClassifierMinScores = cancelBeforeStateChange(setClassifierMinScoresState);

  useEffect(() => {
    const nextScope = databaseSelected ? databaseKey : null;
    if (previousDatabaseScopeRef.current === nextScope) return;
    previousDatabaseScopeRef.current = nextScope;
    coordinatorRef.current.cancel();
    summaryRequestIdRef.current += 1;
    setTracks([]);
    setLibraryTotal(0);
    setLibraryOffset(0);
    setLibraryLoading(false);
    setLibraryProgress(null);
    setLibraryError(null);
    setLibrarySummary(emptyLibrarySummary);
  }, [databaseKey, databaseSelected]);

  useEffect(() => () => {
    coordinatorRef.current.cancel();
    summaryRequestIdRef.current += 1;
  }, []);

  async function refreshLibrarySummary(
    selected = databaseSelected,
    requestDatabaseKey = databaseKey
  ) {
    const requestId = ++summaryRequestIdRef.current;
    if (!selected || !requestDatabaseKey) {
      setLibrarySummary(emptyLibrarySummary);
      return emptyLibrarySummary;
    }
    const summary = await api.librarySummary();
    if (requestId === summaryRequestIdRef.current && databaseKeyRef.current === requestDatabaseKey) {
      setLibrarySummary(summary);
    }
    return summary;
  }

  async function refreshLibrary(
    nextOffset = libraryOffset,
    options: RefreshLibraryOptions = {}
  ) {
    const selected = options.selected ?? databaseSelected;
    const requestDatabaseKey = options.databaseKey ?? databaseKey;
    const requestLoadSize = options.loadSize ?? libraryLoadSize;
    if (!selected || !requestDatabaseKey) {
      resetLibraryState();
      return;
    }

    const effectiveOffset = isPagedLibraryLoadSize(requestLoadSize)
      ? Math.max(0, Math.trunc(nextOffset))
      : 0;
    const classifierMinScores = activeClassifierMinScores(classifierMinScoresState);
    const requestKey = libraryRequestKey({
      databaseKey: requestDatabaseKey,
      query: queryState,
      searchMode: searchModeState,
      preset: libraryPreset,
      liked: likedOnly,
      classifierMinScores,
      loadSize: requestLoadSize,
      offset: effectiveOffset
    });
    const ticket = coordinatorRef.current.start(requestKey);
    const requestIsCurrent = () => (
      coordinatorRef.current.isCurrent(ticket)
      && databaseKeyRef.current === requestDatabaseKey
    );
    const firstChunk = firstLibraryChunk(requestLoadSize, effectiveOffset);
    setTracks([]);
    setLibraryTotal(0);
    setLibraryOffset(effectiveOffset);
    setLibraryLoading(true);
    setLibraryError(null);
    setLibraryProgress({ loaded: 0, total: 0, target: 0, cancelled: false });

    const summaryPromise = options.refreshSummary
      ? refreshLibrarySummary(selected, requestDatabaseKey).catch((error: unknown) => {
          if (databaseKeyRef.current === requestDatabaseKey) {
            setLibraryError(error instanceof Error ? error.message : String(error));
          }
          return null;
        })
      : Promise.resolve(null);

    try {
      const firstPage = await api.tracks({
        query: queryState,
        searchMode: searchModeState,
        preset: libraryPreset,
        liked: likedOnly,
        classifierMinScores,
        limit: firstChunk.limit,
        offset: firstChunk.offset,
        signal: ticket.signal
      });
      if (!requestIsCurrent()) return;
      if (!libraryTracksBelongToCatalog(firstPage.items, requestDatabaseKey)) {
        throw new Error("Library response catalog identity does not match the selected database.");
      }

      let loadedTracks = mergeLibraryTracks([], firstPage.items);
      const target = libraryLoadTarget(firstPage.total, requestLoadSize, firstPage.offset);
      setTracks(loadedTracks);
      setLibraryTotal(firstPage.total);
      setLibraryOffset(isPagedLibraryLoadSize(requestLoadSize) ? firstPage.offset : 0);
      setLibraryProgress({
        loaded: loadedTracks.length,
        total: firstPage.total,
        target,
        cancelled: false
      });

      const remainingChunks = libraryChunkPlan(
        firstPage.total,
        requestLoadSize,
        firstPage.offset
      ).slice(1);
      for (const chunk of remainingChunks) {
        const page = await api.tracks({
          query: queryState,
          searchMode: searchModeState,
          preset: libraryPreset,
          liked: likedOnly,
          classifierMinScores,
          limit: chunk.limit,
          offset: chunk.offset,
          signal: ticket.signal
        });
        if (!requestIsCurrent()) return;
        if (!libraryTracksBelongToCatalog(page.items, requestDatabaseKey)) {
          throw new Error("Library response catalog identity does not match the selected database.");
        }
        loadedTracks = mergeLibraryTracks(loadedTracks, page.items);
        setTracks(loadedTracks);
        setLibraryProgress({
          loaded: loadedTracks.length,
          total: firstPage.total,
          target,
          cancelled: false
        });
        if (page.items.length < chunk.limit) break;
      }
      await summaryPromise;
    } catch (error) {
      if (requestIsCurrent() && !isAbortError(error)) {
        setLibraryError(error instanceof Error ? error.message : String(error));
      }
    } finally {
      if (requestIsCurrent()) {
        coordinatorRef.current.complete(ticket);
        setLibraryLoading(false);
      }
    }
  }

  function resetLibraryState() {
    coordinatorRef.current.cancel();
    summaryRequestIdRef.current += 1;
    setTracks([]);
    setLibraryTotal(0);
    setLibraryOffset(0);
    setLibraryLoading(false);
    setLibraryProgress(null);
    setLibraryError(null);
    setLibrarySummary(emptyLibrarySummary);
  }

  function changeLibraryPage(delta: number) {
    if (pageSize == null) return;
    const currentPage = libraryCurrentPageNumber(libraryTotal, libraryOffset, pageSize);
    const nextOffset = libraryPageOffsetForNumber(
      currentPage + delta,
      libraryTotal,
      pageSize
    );
    void refreshLibrary(nextOffset);
  }

  function jumpToLibraryPage(pageNumber: number) {
    if (pageSize == null) return;
    const nextOffset = libraryPageOffsetForNumber(pageNumber, libraryTotal, pageSize);
    void refreshLibrary(nextOffset);
  }

  function setLibraryLoadSize(loadSize: LibraryLoadSize) {
    if (loadSize === libraryLoadSize) return;
    cancelLibraryLoad();
    clearVisibleLibraryResult();
    setLibraryLoadSizeState(loadSize);
  }

  function toggleLibraryPreset(preset: LibraryPreset) {
    cancelLibraryLoad();
    clearVisibleLibraryResult();
    setLibraryPreset((current) => (current === preset ? "all" : preset));
  }

  function toggleLikedOnly() {
    cancelLibraryLoad();
    clearVisibleLibraryResult();
    setLikedOnly((current) => toggleLikedTracksFilter(current));
  }

  function toggleLibrarySortDirection() {
    setLibrarySortDirection((current) => (current === "forward" ? "reverse" : "forward"));
  }

  async function filteredTracks() {
    const filtered = await api.filteredTracks({
      query: queryState,
      searchMode: searchModeState,
      preset: libraryPreset,
      liked: likedOnly,
      classifierMinScores: activeClassifierMinScores(classifierMinScoresState)
    });
    return mergeLibraryTracks([], filtered);
  }

  function updateTrackLiked(updated: Track) {
    const updatedKey = libraryTrackIdentityKey(updated);
    const previous = tracks.find((track) => libraryTrackIdentityKey(track) === updatedKey);
    if (!previous || updated.content_generation < previous.content_generation) return;

    setTracks((current) => {
      if (likedOnly && !updated.liked) {
        return current.filter((track) => libraryTrackIdentityKey(track) !== updatedKey);
      }
      return mergeLibraryTracks(current, [updated]);
    });
    if (previous.liked !== updated.liked) {
      setLibrarySummary((current) => ({
        ...current,
        liked: Math.max(0, current.liked + (updated.liked ? 1 : -1))
      }));
    }
    if (likedOnly && previous.liked && !updated.liked) {
      setLibraryTotal((current) => Math.max(0, current - 1));
    }
  }

  return {
    tracks,
    setTracks,
    libraryTotal,
    setLibraryTotal,
    libraryOffset,
    setLibraryOffset,
    libraryLoading,
    libraryProgress,
    libraryError,
    libraryLoadSize,
    librarySummary,
    setLibrarySummary,
    query: queryState,
    setQuery,
    searchMode: searchModeState,
    setSearchMode,
    libraryPreset,
    setLibraryPreset,
    librarySortDirection,
    likedOnly,
    classifierMinScores: classifierMinScoresState,
    setClassifierMinScores,
    orderedTracks,
    hasTracks,
    canGoBack,
    canGoForward,
    adoptDatabaseScope,
    refreshLibrary,
    refreshLibrarySummary,
    resetLibraryState,
    cancelLibraryLoad,
    changeLibraryPage,
    jumpToLibraryPage,
    setLibraryLoadSize,
    toggleLibraryPreset,
    toggleLikedOnly,
    toggleLibrarySortDirection,
    filteredTracks,
    updateTrackLiked
  };
}
