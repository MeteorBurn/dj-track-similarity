import type { Track } from "./api";

export type LibraryPreset = "all" | "syncopated";

export function appendVisibleTracksToPlaylist(playlist: Track[], visibleTracks: Track[]) {
  const existing = new Set(playlist.map((track) => track.id));
  const additions = visibleTracks.filter((track) => !existing.has(track.id));
  return [...playlist, ...additions];
}

export function toggleLikedTracksFilter(current: boolean) {
  return !current;
}

export function likedTracksFilterTitle(likedOnly: boolean, likedCount: number) {
  return likedOnly
    ? `Вернуться ко всей библиотеке. Лайкнутых треков: ${likedCount}.`
    : `Показать только лайкнутые треки. Доступно: ${likedCount}.`;
}
