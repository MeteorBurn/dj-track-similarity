import type { Track } from "./api";

export type LibraryPreset = "all" | "syncopated";

export function appendVisibleTracksToPlaylist(playlist: Track[], visibleTracks: Track[]) {
  const existing = new Set(playlist.map((track) => track.id));
  const additions = visibleTracks.filter((track) => !existing.has(track.id));
  return [...playlist, ...additions];
}
