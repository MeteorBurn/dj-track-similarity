import type { Track } from "./api";
import { formatMaestGenreLabel, hasSyncopatedRhythm, SYNCOPATED_RHYTHM_LABEL } from "./syncopatedRhythm";

export type LibraryPreset = "all" | "syncopated";

export function visibleLibraryTracks(tracks: Track[], query: string, preset: LibraryPreset) {
  const needle = query.trim().toLowerCase();
  return tracks.filter((track) => {
    if (preset === "syncopated" && !hasSyncopatedRhythm(track.genres)) {
      return false;
    }
    if (!needle) {
      return true;
    }
    const genres = track.genres || [];
    const searchableValues = [
      track.artist,
      track.title,
      track.album,
      track.path,
      ...genres.map(formatMaestGenreLabel),
      hasSyncopatedRhythm(genres) ? SYNCOPATED_RHYTHM_LABEL : null
    ];
    return searchableValues.some((value) => value?.toLowerCase().includes(needle));
  });
}

export function appendVisibleTracksToPlaylist(playlist: Track[], visibleTracks: Track[]) {
  const existing = new Set(playlist.map((track) => track.id));
  const additions = visibleTracks.filter((track) => !existing.has(track.id));
  return [...playlist, ...additions];
}
