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
  libraryPageSize,
  libraryRequestKey,
  libraryTrackIdentityKey,
  libraryTracksBelongToCatalog,
  mergeLibraryTracks,
  sameClassifierMinScores
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
  const [libraryError, setLibraryError] = useState<string | null>(null);
  const [librarySummary, setLibrarySummary] = useState<LibrarySummary>(emptyLibrarySummary);
  const [queryState, setQueryState] = useState("");
  const [searchModeState, setSearchModeState] = useState<LibrarySearchMode>("like");
  const [libraryPreset, setLibraryPreset] = useState<LibraryPreset>("all");
  const [librarySortDirection, setLibrarySortDirection] = useState<LibrarySortDirection>("forward");
  const [likedOnly, setLikedOnly] = useState(false);
  const [classifierMinScoresState, setClassifierMinScoresState] = useState<Record<string, number>>({});
  const classifierMinScoresRef = useRef(classifierMinScoresState);
  const coordinatorRef = useRef(createLibraryLoadCoordinator());
  const summaryRequestIdRef = useRef(0);
  const databaseKeyRef = useRef(databaseKey);
  const previousDatabaseScopeRef = useRef(databaseSelected ? databaseKey : null);
  databaseKeyRef.current = databaseKey;
  classifierMinScoresRef.current = classifierMinScoresState;

  const orderedTracks = useMemo(
    () => orderedLibraryTracks(tracks, librarySortDirection),
    [tracks, librarySortDirection]
  );
  const hasTracks = librarySummary.tracks > 0;
  const canGoBack = libraryOffset > 0 && !libraryLoading;
  const canGoForward = libraryOffset + libraryPageSize < libraryTotal
    && !libraryLoading;

  const cancelLibraryLoad = useCallback(() => {
    const cancelled = coordinatorRef.current.cancel();
    if (!cancelled) return false;
    setLibraryLoading(false);
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
  const setClassifierMinScores: Dispatch<SetStateAction<Record<string, number>>> = (next) => {
    const current = classifierMinScoresRef.current;
    const resolved = typeof next === "function" ? next(current) : next;
    if (sameClassifierMinScores(current, resolved)) return;
    cancelLibraryLoad();
    clearVisibleLibraryResult();
    classifierMinScoresRef.current = resolved;
    setClassifierMinScoresState(resolved);
  };

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
    if (!selected || !requestDatabaseKey) {
      resetLibraryState();
      return;
    }

    const effectiveOffset = Math.max(0, Math.trunc(nextOffset));
    const classifierMinScores = activeClassifierMinScores(classifierMinScoresState);
    const requestKey = libraryRequestKey({
      databaseKey: requestDatabaseKey,
      query: queryState,
      searchMode: searchModeState,
      preset: libraryPreset,
      liked: likedOnly,
      classifierMinScores,
      offset: effectiveOffset
    });
    const ticket = coordinatorRef.current.start(requestKey);
    const requestIsCurrent = () => (
      coordinatorRef.current.isCurrent(ticket)
      && databaseKeyRef.current === requestDatabaseKey
    );
    setTracks([]);
    setLibraryTotal(0);
    setLibraryOffset(effectiveOffset);
    setLibraryLoading(true);
    setLibraryError(null);

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
        limit: libraryPageSize,
        offset: effectiveOffset,
        signal: ticket.signal
      });
      if (!requestIsCurrent()) return;
      if (!libraryTracksBelongToCatalog(firstPage.items, requestDatabaseKey)) {
        throw new Error("Library response catalog identity does not match the selected database.");
      }

      setTracks(mergeLibraryTracks([], firstPage.items));
      setLibraryTotal(firstPage.total);
      setLibraryOffset(firstPage.offset);
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
    setLibraryError(null);
    setLibrarySummary(emptyLibrarySummary);
  }

  function changeLibraryPage(delta: number) {
    const currentPage = libraryCurrentPageNumber(libraryTotal, libraryOffset, libraryPageSize);
    const nextOffset = libraryPageOffsetForNumber(
      currentPage + delta,
      libraryTotal,
      libraryPageSize
    );
    void refreshLibrary(nextOffset);
  }

  function jumpToLibraryPage(pageNumber: number) {
    const nextOffset = libraryPageOffsetForNumber(pageNumber, libraryTotal, libraryPageSize);
    void refreshLibrary(nextOffset);
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
    libraryError,
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
    changeLibraryPage,
    jumpToLibraryPage,
    toggleLibraryPreset,
    toggleLikedOnly,
    toggleLibrarySortDirection,
    filteredTracks,
    updateTrackLiked
  };
}
