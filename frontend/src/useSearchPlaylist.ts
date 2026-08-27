import { useMemo, useState } from "react";
import type { SearchResult, Track, TrackDetail } from "./api";
import type { ActivityEvent } from "./jobUi";
import { displayTrack } from "./trackDisplay";

type ActivityAppender = (level: ActivityEvent["level"], message: string, detail?: string) => void;

/**
 * What playback actually needs. The audio element resolves a source from the
 * track id alone, so any row that names a library track can be previewed.
 */
export type PreviewTarget = { track_id: number };

export function useSearchPlaylist({ onActivity }: { onActivity?: ActivityAppender } = {}) {
  const [textQuery, setTextQuery] = useState("");
  const [outputDir, setOutputDir] = useState("");
  const [seeds, setSeeds] = useState<number[]>([]);
  const [results, setResults] = useState<SearchResult[]>([]);
  const [playlist, setPlaylist] = useState<Track[]>([]);
  const [playlistName, setPlaylistName] = useState("seamless-set");
  const [preview, setPreview] = useState<PreviewTarget | null>(null);
  const [playingTrackId, setPlayingTrackId] = useState<number | null>(null);
  const [metadataTrack, setMetadataTrack] = useState<TrackDetail | null>(null);
  const [seedTrackMap, setSeedTrackMap] = useState<Record<number, Track>>({});

  const seedSet = useMemo(() => new Set(seeds), [seeds]);
  const playlistSet = useMemo(() => new Set(playlist.map((track) => track.track_id)), [playlist]);
  const seedTracks = useMemo(() => seeds.map((id) => seedTrackMap[id]).filter(Boolean) as Track[], [seeds, seedTrackMap]);

  function addSeed(track: Track) {
    setSeedTrackMap((current) => ({ ...current, [track.track_id]: track }));
    setSeeds((current) => (current.includes(track.track_id) ? current : [...current, track.track_id]));
  }

  function removeSeed(trackId: number) {
    setSeedTrackMap((current) => {
      const next = { ...current };
      delete next[trackId];
      return next;
    });
    setSeeds((current) => current.filter((id) => id !== trackId));
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

  function togglePreview(track: PreviewTarget) {
    if (preview?.track_id === track.track_id && playingTrackId === track.track_id) {
      setPlayingTrackId(null);
      return;
    }
    setPreview(track);
    setPlayingTrackId(track.track_id);
  }

  function markPreviewPlaying(trackId: number) {
    setPlayingTrackId(trackId);
  }

  function markPreviewPaused(trackId: number) {
    setPlayingTrackId((current) => (current === trackId ? null : current));
  }

  function resetSearchPlaylistState() {
    setSeeds([]);
    setResults([]);
    setPlaylist([]);
    setPreview(null);
    setPlayingTrackId(null);
    setMetadataTrack(null);
    setSeedTrackMap({});
  }

  return {
    textQuery,
    setTextQuery,
    outputDir,
    setOutputDir,
    seeds,
    results,
    setResults,
    playlist,
    setPlaylist,
    playlistName,
    setPlaylistName,
    preview,
    playingTrackId,
    togglePreview,
    markPreviewPlaying,
    markPreviewPaused,
    metadataTrack,
    setMetadataTrack,
    setSeedTrackMap,
    seedSet,
    playlistSet,
    seedTracks,
    addSeed,
    removeSeed,
    removeFromPlaylist,
    togglePlaylist,
    resetSearchPlaylistState
  };
}
