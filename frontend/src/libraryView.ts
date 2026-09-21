import type { Track } from "./api";
import { libraryTrackIdentityKey } from "./libraryLoading";

export type LibraryPreset = "all" | "syncopated";
export type LibrarySortDirection = "forward" | "reverse";
export type LibrarySearchMode = "like" | "fts";

export function appendVisibleTracksToPlaylist(playlist: Track[], visibleTracks: Track[]) {
  const existing = new Set(playlist.map(libraryTrackIdentityKey));
  const additions = visibleTracks.filter((track) => {
    const key = libraryTrackIdentityKey(track);
    if (existing.has(key)) return false;
    existing.add(key);
    return true;
  });
  return [...playlist, ...additions];
}

export function toggleLikedTracksFilter(current: boolean) {
  return !current;
}

export function librarySearchModeTitle(mode: LibrarySearchMode) {
  return mode === "like"
    ? "Substring LIKE search. Finds partial text inside artist, title, album, path, and metadata."
    : "FTS token search. Faster on broad text queries, but does not match arbitrary substrings inside one token.";
}

export function orderedLibraryTracks(tracks: Track[], direction: LibrarySortDirection) {
  return direction === "reverse" ? [...tracks].reverse() : tracks;
}

export function nextLibraryPlaybackTrack(
  tracks: Track[],
  currentTrackId: number,
  shuffle: boolean,
  random = Math.random
) {
  const currentIndex = tracks.findIndex((track) => track.track_id === currentTrackId);
  if (currentIndex < 0 || tracks.length < 2) return null;
  if (!shuffle) return tracks[currentIndex + 1] || null;

  const alternatives = tracks.filter((track) => track.track_id !== currentTrackId);
  return alternatives[Math.min(alternatives.length - 1, Math.floor(random() * alternatives.length))] || null;
}

export function previousLibraryPlaybackTrack(tracks: Track[], currentTrackId: number) {
  const currentIndex = tracks.findIndex((track) => track.track_id === currentTrackId);
  return currentIndex > 0 ? tracks[currentIndex - 1] : null;
}

// `pageSize` is required on purpose: the loader in `libraryLoading` owns the
// single page size, and a local default here silently disagreed with it.
export function libraryPageCount(total: number, pageSize: number) {
  if (total <= 0 || pageSize <= 0) return 0;
  return Math.ceil(total / pageSize);
}

export function libraryCurrentPageNumber(total: number, offset: number, pageSize: number) {
  const pages = libraryPageCount(total, pageSize);
  if (!pages) return 0;
  const current = Math.floor(Math.max(0, offset) / pageSize) + 1;
  return Math.min(current, pages);
}

export function libraryPageOffsetForNumber(pageNumber: number, total: number, pageSize: number) {
  const pages = libraryPageCount(total, pageSize);
  if (!pages) return 0;
  const requested = Number.isFinite(pageNumber) ? Math.trunc(pageNumber) : 1;
  const clamped = Math.min(Math.max(requested, 1), pages);
  return (clamped - 1) * pageSize;
}

export function likedTracksFilterTitle(likedOnly: boolean, likedCount: number) {
  return likedOnly
    ? `Вернуться ко всей библиотеке. Лайкнутых треков: ${likedCount}.`
    : `Показать только лайкнутые треки. Доступно: ${likedCount}.`;
}

export type CollapsiblePanel = "setup" | "library" | "search";

const panelStorageKeys: Record<CollapsiblePanel, string> = {
  setup: "dj-track-similarity-setup-collapsed",
  library: "dj-track-similarity-library-collapsed",
  search: "dj-track-similarity-search-collapsed"
};

/**
 * Whether a workspace panel was left collapsed.
 *
 * Collapsing a panel hands its column width to the expanded panels.
 *
 * The choice outlives a reload. Storage that cannot be read means open,
 * because a panel nobody can find is worse than one taking room.
 */
export function resolvePanelCollapsed(panel: CollapsiblePanel): boolean {
  if (typeof window === "undefined") return false;
  try {
    return window.localStorage.getItem(panelStorageKeys[panel]) === "collapsed";
  } catch {
    return false;
  }
}

export function storePanelCollapsed(panel: CollapsiblePanel, collapsed: boolean) {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(panelStorageKeys[panel], collapsed ? "collapsed" : "open");
  } catch {
    // Browser privacy settings can block storage; the panel still toggles, it
    // just forgets the choice on the next load.
  }
}
