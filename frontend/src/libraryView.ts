import type { Track } from "./api";

export type LibraryPreset = "all" | "syncopated";
export type LibrarySortDirection = "forward" | "reverse";

export const libraryPageSize = 200;

export function appendVisibleTracksToPlaylist(playlist: Track[], visibleTracks: Track[]) {
  const existing = new Set(playlist.map((track) => track.id));
  const additions = visibleTracks.filter((track) => !existing.has(track.id));
  return [...playlist, ...additions];
}

export function toggleLikedTracksFilter(current: boolean) {
  return !current;
}

export function orderedLibraryTracks(tracks: Track[], direction: LibrarySortDirection) {
  return direction === "reverse" ? [...tracks].reverse() : tracks;
}

export function libraryPageCount(total: number, pageSize = libraryPageSize) {
  if (total <= 0 || pageSize <= 0) return 0;
  return Math.ceil(total / pageSize);
}

export function libraryCurrentPageNumber(total: number, offset: number, pageSize = libraryPageSize) {
  const pages = libraryPageCount(total, pageSize);
  if (!pages) return 0;
  const current = Math.floor(Math.max(0, offset) / pageSize) + 1;
  return Math.min(current, pages);
}

export function libraryPageOffsetForNumber(pageNumber: number, total: number, pageSize = libraryPageSize) {
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
