import { Track } from "./api";

export function displayTrack(track: Track) {
  if (track.artist && track.title) return `${track.artist} - ${track.title}`;
  return track.title || basename(track.path) || track.path;
}

export function trackInfo(track: Track) {
  return analysisStatusLabel(track);
}

export function trackCountLabel(count: number) {
  const lastTwo = count % 100;
  const last = count % 10;
  if (lastTwo >= 11 && lastTwo <= 14) return "треков";
  if (last === 1) return "трек";
  if (last >= 2 && last <= 4) return "трека";
  return "треков";
}

export function analysisStatusLabel(track: Track) {
  const labels = [
    trackHasAnalysis(track, "sonara") ? "sonara" : null,
    trackHasAnalysis(track, "maest") ? "maest" : null,
    trackHasAnalysis(track, "mert") ? "mert" : null,
    trackHasAnalysis(track, "clap") ? "clap" : null
  ].filter(Boolean);
  return labels.length ? labels.join(" ") : "";
}

export function trackHasAnalysis(track: Track, adapter: "sonara" | "maest" | "mert" | "clap") {
  const analyses = new Set(track.analyses || []);
  if (track.metadata?.sonara_features) analyses.add("sonara");
  if (track.genres?.length) analyses.add("maest");
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
