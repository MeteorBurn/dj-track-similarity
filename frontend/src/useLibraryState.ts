import { useMemo, useState } from "react";
import { api, type LibrarySummary, type Track } from "./api";
import {
  libraryCurrentPageNumber,
  libraryPageOffsetForNumber,
  libraryPageSize,
  orderedLibraryTracks,
  toggleLikedTracksFilter,
  type LibraryPreset,
  type LibrarySearchMode,
  type LibrarySortDirection
} from "./libraryView";

export const emptyLibrarySummary: LibrarySummary = { tracks: 0, sonara: 0, maest: 0, mert: 0, clap: 0, liked: 0, classifiers: 0 };

function activeClassifierMinScores(scores: Record<string, number>) {
  return Object.fromEntries(Object.entries(scores).filter(([, value]) => value > 0));
}

export function useLibraryState({ databaseSelected }: { databaseSelected: boolean }) {
  const [tracks, setTracks] = useState<Track[]>([]);
  const [libraryTotal, setLibraryTotal] = useState(0);
  const [libraryOffset, setLibraryOffset] = useState(0);
  const [libraryLoading, setLibraryLoading] = useState(false);
  const [librarySummary, setLibrarySummary] = useState<LibrarySummary>(emptyLibrarySummary);
  const [query, setQuery] = useState("");
  const [searchMode, setSearchMode] = useState<LibrarySearchMode>("like");
  const [libraryPreset, setLibraryPreset] = useState<LibraryPreset>("all");
  const [librarySortDirection, setLibrarySortDirection] = useState<LibrarySortDirection>("forward");
  const [likedOnly, setLikedOnly] = useState(false);
  const [classifierMinScores, setClassifierMinScores] = useState<Record<string, number>>({});

  const orderedTracks = useMemo(() => orderedLibraryTracks(tracks, librarySortDirection), [tracks, librarySortDirection]);
  const hasTracks = librarySummary.tracks > 0;
  const canGoBack = libraryOffset > 0 && !libraryLoading;
  const canGoForward = libraryOffset + tracks.length < libraryTotal && !libraryLoading;

  async function refreshLibrary(nextOffset = libraryOffset, selected = databaseSelected) {
    if (!selected) {
      resetLibraryState();
      return;
    }
    setLibraryLoading(true);
    try {
      const [page, summary] = await Promise.all([
        api.tracks({
          query,
          searchMode,
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

  function resetLibraryState() {
    setTracks([]);
    setLibraryTotal(0);
    setLibraryOffset(0);
    setLibraryLoading(false);
    setLibrarySummary(emptyLibrarySummary);
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

  function toggleLibraryPreset(preset: LibraryPreset) {
    setLibraryPreset((current) => (current === preset ? "all" : preset));
  }

  function toggleLikedOnly() {
    setLikedOnly((current) => toggleLikedTracksFilter(current));
  }

  function toggleLibrarySortDirection() {
    setLibrarySortDirection((current) => (current === "forward" ? "reverse" : "forward"));
  }

  function filteredTracks() {
    return api.filteredTracks({
      query,
      searchMode,
      preset: libraryPreset,
      liked: likedOnly,
      classifierMinScores: activeClassifierMinScores(classifierMinScores)
    });
  }

  function updateTrackLiked(updated: Track) {
    setTracks((current) => {
      if (likedOnly && !updated.liked) return current.filter((item) => item.id !== updated.id);
      return current.map((item) => (item.id === updated.id ? { ...item, liked: updated.liked } : item));
    });
    setLibrarySummary((current) => ({
      ...current,
      liked: Math.max(0, current.liked + (updated.liked ? 1 : -1))
    }));
    setLibraryTotal((current) => (likedOnly && !updated.liked ? Math.max(0, current - 1) : current));
  }

  return {
    tracks,
    setTracks,
    libraryTotal,
    setLibraryTotal,
    libraryOffset,
    setLibraryOffset,
    libraryLoading,
    librarySummary,
    setLibrarySummary,
    query,
    setQuery,
    searchMode,
    setSearchMode,
    libraryPreset,
    setLibraryPreset,
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
  };
}
