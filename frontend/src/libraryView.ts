import type { Track } from "./api";

export type LibraryPreset = "all" | "syncopated";
export type LibrarySortDirection = "forward" | "reverse";

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

export function likedTracksFilterTitle(likedOnly: boolean, likedCount: number) {
  return likedOnly
    ? `Вернуться ко всей библиотеке. Лайкнутых треков: ${likedCount}.`
    : `Показать только лайкнутые треки. Доступно: ${likedCount}.`;
}
