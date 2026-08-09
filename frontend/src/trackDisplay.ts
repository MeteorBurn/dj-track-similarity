import type { AnalysisModel, TrackSummary } from "./api";

export function displayTrack(track: TrackSummary) {
  if (track.artist && track.title) return `${track.artist} - ${track.title}`;
  return track.title || basename(track.file_path) || track.file_path;
}

export function sameTrackIdentity(
  left: TrackSummary,
  right: TrackSummary
) {
  return (
    left.track_id === right.track_id
    && left.catalog_uuid === right.catalog_uuid
    && left.track_uuid === right.track_uuid
    && left.content_generation === right.content_generation
  );
}

export function trackHasAnalysis(track: TrackSummary, adapter: AnalysisModel) {
  if (adapter === "sonara") return track.analysis_coverage.sonara_core;
  if (adapter === "maest") return track.analysis_coverage.maest_analysis;
  return track.analysis_coverage[adapter];
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
