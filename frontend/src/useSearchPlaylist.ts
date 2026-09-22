import { useMemo, useState } from "react";
import type { SearchResult, Track, TrackDetail, TrackSummary } from "./api";
import type { ActivityEvent } from "./jobUi";
import { displayTrack, sameTrackIdentity } from "./trackDisplay";

type ActivityAppender = (level: ActivityEvent["level"], message: string, detail?: string) => void;

/**
 * What playback actually needs. The audio element resolves a source from the
 * track id alone, so any row that names a library track can be previewed.
 */
export type PreviewTarget = { track_id: number };

/** Seed search averages its seeds, so more than a handful only blurs the query. */
export const MAX_SEED_TRACKS = 5;

export function useSearchPlaylist({ onActivity, onSeedLimit }: { onActivity?: ActivityAppender; onSeedLimit?: () => void } = {}) {
  const [outputDir, setOutputDir] = useState("");
  const [seedTracks, setSeedTracks] = useState<Track[]>([]);
  const [results, setResults] = useState<SearchResult[]>([]);
  const [playlist, setPlaylist] = useState<Track[]>([]);
  const [playlistName, setPlaylistName] = useState("djts-playlist-title");
  const [metadataTrack, setMetadataTrack] = useState<TrackDetail | null>(null);

  const seeds = useMemo(() => seedTracks.map((track) => track.track_id), [seedTracks]);
  const seedSet = useMemo(() => new Set(seeds), [seeds]);
  const playlistSet = useMemo(() => new Set(playlist.map((track) => track.track_id)), [playlist]);

  function addSeed(track: Track) {
    if (!seedSet.has(track.track_id) && seedTracks.length >= MAX_SEED_TRACKS) {
      onSeedLimit?.();
      return;
    }
    setSeedTracks((current) => current.some((item) => item.track_id === track.track_id)
      ? current.map((item) => item.track_id === track.track_id ? track : item)
      : current.length < MAX_SEED_TRACKS ? [...current, track] : current);
  }

  function removeSeed(trackId: number) {
    setSeedTracks((current) => current.filter((track) => track.track_id !== trackId));
  }

  function addToPlaylist(track: Track) {
    if (!playlistSet.has(track.track_id)) {
      onActivity?.("ok", "Добавлен в сет", displayTrack(track));
    }
    setPlaylist((current) => (current.some((item) => item.track_id === track.track_id) ? current : [...current, track]));
  }

  function removeFromPlaylist(trackId: number) {
    const removed = playlist.find((track) => track.track_id === trackId);
    if (removed) {
      onActivity?.("warn", "Убран из сета", displayTrack(removed));
    }
    setPlaylist((current) => current.filter((track) => track.track_id !== trackId));
  }

  function togglePlaylist(track: Track) {
    if (playlistSet.has(track.track_id)) {
      removeFromPlaylist(track.track_id);
    } else {
      addToPlaylist(track);
    }
  }

  /**
   * A track deleted from the catalogue leaves the seeds, the results and the
   * set; everything else in them still names a live track and stays. The match
   * is the full catalogue identity, so a list read from another library keeps
   * a row that merely shares the numeric id.
   */
  function forgetTrack(deleted: TrackSummary) {
    dropTracks((track) => sameTrackIdentity(track, deleted));
  }

  /**
   * Audio Dedup reports its deletions as numeric ids of the open catalogue.
   * Ids are never reused within one catalogue, so id plus catalogue is enough.
   */
  function forgetTrackIds(catalogUuid: string, trackIds: readonly number[]) {
    const deleted = new Set(trackIds);
    dropTracks((track) => track.catalog_uuid === catalogUuid && deleted.has(track.track_id));
  }

  function dropTracks(isDeleted: (track: TrackSummary) => boolean) {
    const kept = (track: TrackSummary) => !isDeleted(track);
    setSeedTracks((current) => current.filter(kept));
    setResults((current) => current.filter((result) => kept(result.track)));
    setPlaylist((current) => current.filter(kept));
  }

  function resetSearchPlaylistState() {
    setSeedTracks([]);
    setResults([]);
    setPlaylist([]);
    setMetadataTrack(null);
  }

  return {
    outputDir,
    setOutputDir,
    seeds,
    results,
    setResults,
    playlist,
    setPlaylist,
    playlistName,
    setPlaylistName,
    metadataTrack,
    setMetadataTrack,
    setSeedTracks,
    seedSet,
    playlistSet,
    seedTracks,
    addSeed,
    removeSeed,
    removeFromPlaylist,
    togglePlaylist,
    forgetTrack,
    forgetTrackIds,
    resetSearchPlaylistState
  };
}
