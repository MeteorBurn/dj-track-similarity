import { Track, TrackDetailV7 } from "./api";

export function displayTrack(track: Track | TrackDetailV7) {
  if (track.artist && track.title) return `${track.artist} - ${track.title}`;
  const path = "file_path" in track ? track.file_path : track.path;
  return track.title || basename(path) || path;
}

export function trackCountLabel(count: number) {
  const lastTwo = count % 100;
  const last = count % 10;
  if (lastTwo >= 11 && lastTwo <= 14) return "треков";
  if (last === 1) return "трек";
  if (last >= 2 && last <= 4) return "трека";
  return "треков";
}

export function trackHasAnalysis(track: Track | TrackDetailV7, adapter: "sonara" | "maest" | "mert" | "muq" | "clap") {
  if ("analysis_coverage" in track) {
    if (adapter === "sonara") return !!track.analysis_coverage.sonara_core;
    return !!track.analysis_coverage[adapter];
  }
  const analyses = new Set(track.analyses || []);
  if (track.metadata?.sonara_features) analyses.add("sonara");
  if (track.embedding_model) analyses.add("mert");
  return analyses.has(adapter);
}

export function basename(path: string) {
  return path.split(/[\\/]/).pop() || path;
}

export function formatEta(seconds: number) {
  const minutes = Math.floor(seconds / 60);
  const rest = Math.round(seconds % 60);
  if (minutes < 60) return `${minutes}m ${rest}s`;
  const hours = Math.floor(minutes / 60);
  return `${hours}h ${minutes % 60}m`;
}
