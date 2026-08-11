import { Heart, Minus, Pause, Play, Plus, Search, Tags } from "lucide-react";
import type { Track } from "./api";
import { libraryTrackIdentityKey } from "./libraryLoading";
import { displayTrack } from "./trackDisplay";

type TrackActions = {
  playingTrackId: number | null;
  onSeed: (track: Track) => void;
  onToggleLiked?: (track: Track) => void;
  onTogglePlaylist: (track: Track) => void;
  onPreview: (track: Track) => void;
  onDetails: (track: Track) => void;
};

export function TrackList({
  tracks,
  seedSet,
  playlistSet,
  playingTrackId,
  previewTrackId,
  previewCurrentTime,
  previewDuration,
  onSeed,
  onToggleLiked,
  onTogglePlaylist,
  onPreview,
  onSeekPreview,
  onDetails
}: TrackActions & {
  tracks: Track[];
  seedSet: Set<number>;
  playlistSet: Set<number>;
  previewTrackId: number | null;
  previewCurrentTime: number;
  previewDuration: number;
  onSeekPreview: (track: Track, seconds: number) => void;
}) {
  return (
    <div className="track-list">
      {tracks.map((track) => {
        const trackPreviewActive = playingTrackId === track.track_id;
        const trackPreviewSelected = previewTrackId === track.track_id;
        return (
          <div
            aria-current={trackPreviewActive ? "true" : undefined}
            className={`track-row ${trackPreviewActive ? "is-playing" : ""}`}
            key={libraryTrackIdentityKey(track)}
          >
            <button className="icon-button track-preview-button" title={trackPreviewActive ? "Pause preview" : "Preview"} aria-label={`${trackPreviewActive ? "Pause" : "Preview"} ${displayTrack(track)}`} onClick={() => onPreview(track)} type="button">
              {trackPreviewActive ? <Pause size={15} /> : <Play size={15} />}
            </button>
            <div className={`track-title-cell ${trackPreviewSelected ? "with-playback" : ""}`}>
              <strong>{displayTrack(track)}</strong>
              {trackPreviewSelected ? (
                <div className="track-row-playback">
                  <input
                    aria-label={`Позиция воспроизведения ${displayTrack(track)}`}
                    disabled={previewDuration <= 0}
                    max={Math.max(previewDuration, 1)}
                    min={0}
                    onChange={(event) => onSeekPreview(track, Number(event.target.value))}
                    step={0.1}
                    title="Перемотать preview"
                    type="range"
                    value={Math.min(previewCurrentTime, Math.max(previewDuration, 1))}
                  />
                  <span>{formatPlaybackTime(previewCurrentTime)} / {formatPlaybackTime(previewDuration)}</span>
                </div>
              ) : null}
            </div>
            {onToggleLiked && (
              <button
                className={`icon-button track-liked-button ${track.liked ? "active intent-liked" : ""}`}
                title={track.liked ? "Убрать лайк" : "Лайкнуть"}
                aria-label={track.liked ? `Убрать лайк с ${displayTrack(track)}` : `Лайкнуть ${displayTrack(track)}`}
                aria-pressed={track.liked}
                onClick={() => onToggleLiked(track)}
                type="button"
              >
                <Heart size={15} fill={track.liked ? "currentColor" : "none"} />
              </button>
            )}
            <button className="icon-button track-metadata-button" title="Теги и жанры" aria-label={`Теги ${displayTrack(track)}`} onClick={() => onDetails(track)} type="button"><Tags size={15} /></button>
            <button className={`icon-button track-seed-button ${seedSet.has(track.track_id) ? "active" : ""}`} title="Seed" aria-label={`Seed ${displayTrack(track)}`} onClick={() => onSeed(track)} type="button"><Search size={15} /></button>
            <button
              className={`icon-button track-playlist-toggle-button ${playlistSet.has(track.track_id) ? "intent-remove active" : "intent-add"}`}
              title={playlistSet.has(track.track_id) ? "Убрать из сета" : "В сет"}
              aria-label={playlistSet.has(track.track_id) ? `Убрать ${displayTrack(track)} из сета` : `Добавить ${displayTrack(track)} в сет`}
              onClick={() => onTogglePlaylist(track)}
              type="button"
            >
              {playlistSet.has(track.track_id) ? <Minus size={15} /> : <Plus size={15} />}
            </button>
          </div>
        );
      })}
    </div>
  );
}

function formatPlaybackTime(seconds: number) {
  if (!Number.isFinite(seconds) || seconds <= 0) return "0:00";
  const rounded = Math.floor(seconds);
  const minutes = Math.floor(rounded / 60);
  return `${minutes}:${String(rounded % 60).padStart(2, "0")}`;
}

export function ResultRow({
  track,
  score,
  scoreBreakdown,
  reason,
  sonaraGroups,
  classifierScores,
  transition,
  playingTrackId,
  isSeed,
  inPlaylist,
  onSeed,
  onToggleLiked,
  onTogglePlaylist,
  onPreview,
  onDetails,
  selected = false,
  onSelect,
  selectTitle
}: TrackActions & {
  track: Track;
  score: number;
  scoreBreakdown?: Record<string, number> | null;
  reason?: string;
  sonaraGroups?: Record<string, number>;
  classifierScores?: Record<string, number>;
  transition?: {
    from_track_id?: number | null;
    bpm_delta?: number | null;
    key_relation?: string;
    confidence: number;
  };
  isSeed: boolean;
  inPlaylist: boolean;
  selected?: boolean;
  onSelect?: (track: Track) => void;
  selectTitle?: string;
}) {
  const breakdownTitle = scoreBreakdownTitle(scoreBreakdown, sonaraGroups, classifierScores, transition);
  const trackPreviewActive = playingTrackId === track.track_id;
  const selectableClass = onSelect ? "selectable" : "";
  const selectedClass = selected ? "selected" : "";
  return (
    <div
      className={`result-row ${selectableClass} ${selectedClass}`}
      title={selectTitle}
      role={onSelect ? "button" : undefined}
      tabIndex={onSelect ? 0 : undefined}
      onClick={onSelect ? () => onSelect(track) : undefined}
      onKeyDown={onSelect ? (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onSelect(track);
        }
      } : undefined}
    >
      <button className="icon-button result-preview-button" title={trackPreviewActive ? "Pause preview" : "Preview"} aria-label={`${trackPreviewActive ? "Pause" : "Preview"} ${displayTrack(track)}`} onClick={(event) => { event.stopPropagation(); onPreview(track); }} type="button">
        {trackPreviewActive ? <Pause size={15} /> : <Play size={15} />}
      </button>
      <div className="track-title-cell">
        <strong>{displayTrack(track)}</strong>
        {reason ? (
          <span className="result-reason-chip" title={breakdownTitle}>{reason.replaceAll("_", " ")}</span>
        ) : null}
      </div>
      <meter min={0} max={1} value={Math.max(0, Math.min(1, score))} title={breakdownTitle} />
      <span className="similarity-score" title={breakdownTitle}>{score.toFixed(3)}</span>
      {onToggleLiked && (
        <button
          className={`icon-button track-liked-button ${track.liked ? "active intent-liked" : ""}`}
          title={track.liked ? "Убрать лайк" : "Лайкнуть"}
          aria-label={track.liked ? `Убрать лайк с ${displayTrack(track)}` : `Лайкнуть ${displayTrack(track)}`}
          aria-pressed={track.liked}
          onClick={(event) => { event.stopPropagation(); onToggleLiked(track); }}
          type="button"
        >
          <Heart size={15} fill={track.liked ? "currentColor" : "none"} />
        </button>
      )}
      <button className="icon-button result-metadata-button" title="Теги и жанры" aria-label={`Теги ${displayTrack(track)}`} onClick={(event) => { event.stopPropagation(); onDetails(track); }} type="button"><Tags size={15} /></button>
      <button className={`icon-button result-seed-button ${isSeed ? "active" : ""}`} title="Seed" aria-label={`Seed ${displayTrack(track)}`} onClick={(event) => { event.stopPropagation(); onSeed(track); }} type="button"><Search size={15} /></button>
      <button
        className={`icon-button result-playlist-toggle-button ${inPlaylist ? "intent-remove active" : "intent-add"}`}
        title={inPlaylist ? "Убрать из сета" : "В сет"}
        aria-label={inPlaylist ? `Убрать ${displayTrack(track)} из сета` : `Добавить ${displayTrack(track)} в сет`}
        onClick={(event) => { event.stopPropagation(); onTogglePlaylist(track); }}
        type="button"
      >
        {inPlaylist ? <Minus size={15} /> : <Plus size={15} />}
      </button>
    </div>
  );
}

function scoreBreakdownTitle(
  scoreBreakdown?: Record<string, number> | null,
  sonaraGroups?: Record<string, number>,
  classifierScores?: Record<string, number>,
  transition?: { from_track_id?: number | null; bpm_delta?: number | null; key_relation?: string; confidence: number }
) {
  const lines: string[] = [];
  if (scoreBreakdown && Object.keys(scoreBreakdown).length) {
    lines.push(...Object.entries(scoreBreakdown)
    .map(([key, value]) => `${key.replaceAll("_", " ")}: ${value.toFixed(3)}`)
    );
  }
  if (sonaraGroups && Object.keys(sonaraGroups).length) {
    lines.push(...Object.entries(sonaraGroups)
      .map(([key, value]) => `sonara ${key.replaceAll("_", " ")}: ${value.toFixed(3)}`)
    );
  }
  if (classifierScores && Object.keys(classifierScores).length) {
    lines.push(...Object.entries(classifierScores)
      .map(([key, value]) => `classifier ${key.replaceAll("_", " ")}: ${value.toFixed(3)}`)
    );
  }
  if (transition) {
    lines.push(`transition: ${transition.confidence.toFixed(3)}`);
    if (transition.key_relation) lines.push(`key: ${transition.key_relation}`);
    if (transition.bpm_delta != null) lines.push(`bpm delta: ${transition.bpm_delta.toFixed(2)}`);
  }
  return lines.length ? lines.join("\n") : "Similarity score";
}
