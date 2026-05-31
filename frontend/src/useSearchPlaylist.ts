import { useMemo, useState } from "react";
import type { SearchResult, Track } from "./api";
import type { ActivityEvent } from "./jobUi";
import { displayTrack } from "./trackDisplay";

type ActivityAppender = (level: ActivityEvent["level"], message: string, detail?: string) => void;

export function useSearchPlaylist({ onActivity }: { onActivity?: ActivityAppender } = {}) {
  const [textQuery, setTextQuery] = useState("");
  const [outputDir, setOutputDir] = useState("");
  const [seeds, setSeeds] = useState<number[]>([]);
  const [results, setResults] = useState<SearchResult[]>([]);
  const [playlist, setPlaylist] = useState<Track[]>([]);
  const [playlistName, setPlaylistName] = useState("seamless-set");
  const [preview, setPreview] = useState<Track | null>(null);
  const [metadataTrack, setMetadataTrack] = useState<Track | null>(null);
  const [seedTrackMap, setSeedTrackMap] = useState<Record<number, Track>>({});

  const seedSet = useMemo(() => new Set(seeds), [seeds]);
  const playlistSet = useMemo(() => new Set(playlist.map((track) => track.id)), [playlist]);
  const seedTracks = useMemo(() => seeds.map((id) => seedTrackMap[id]).filter(Boolean) as Track[], [seeds, seedTrackMap]);

  function addSeed(track: Track) {
    setSeedTrackMap((current) => ({ ...current, [track.id]: track }));
    setSeeds((current) => (current.includes(track.id) ? current : [...current, track.id]));
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
    if (!playlistSet.has(track.id)) {
      onActivity?.("ok", "Добавлен в сет", displayTrack(track));
    }
    setPlaylist((current) => (current.some((item) => item.id === track.id) ? current : [...current, track]));
  }

  function removeFromPlaylist(trackId: number) {
    const removed = playlist.find((track) => track.id === trackId);
    if (removed) {
      onActivity?.("warn", "Убран из сета", displayTrack(removed));
    }
    setPlaylist((current) => current.filter((track) => track.id !== trackId));
  }

  function togglePlaylist(track: Track) {
    if (playlistSet.has(track.id)) {
      removeFromPlaylist(track.id);
    } else {
      addToPlaylist(track);
    }
  }

  function resetSearchPlaylistState() {
    setSeeds([]);
    setResults([]);
    setPlaylist([]);
    setPreview(null);
    setMetadataTrack(null);
    setSeedTrackMap({});
  }

  return {
    textQuery,
    setTextQuery,
    outputDir,
    setOutputDir,
    seeds,
    setSeeds,
    results,
    setResults,
    playlist,
    setPlaylist,
    playlistName,
    setPlaylistName,
    preview,
    setPreview,
    metadataTrack,
    setMetadataTrack,
    seedTrackMap,
    setSeedTrackMap,
    seedSet,
    playlistSet,
    seedTracks,
    addSeed,
    removeSeed,
    addToPlaylist,
    removeFromPlaylist,
    togglePlaylist,
    resetSearchPlaylistState
  };
}
