import { useEffect, useMemo, useState } from "react";
import { Heart, Minus, Pause, Play, Plus, Search, Tags } from "lucide-react";
import type { Track } from "./api";
import { libraryTrackIdentityKey } from "./libraryLoading";
import { shiftLibraryWindow, visibleLibraryWindow } from "./libraryWindow";
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
  onSeed,
  onToggleLiked,
  onTogglePlaylist,
  onPreview,
  onDetails
}: TrackActions & {
  tracks: Track[];
  seedSet: Set<number>;
  playlistSet: Set<number>;
}) {
  const [windowStart, setWindowStart] = useState(0);
  const collectionKey = tracks.length
    ? `${libraryTrackIdentityKey(tracks[0])}:${libraryTrackIdentityKey(tracks[tracks.length - 1])}:${tracks.length}`
    : "empty";
  const visibleWindow = useMemo(
    () => visibleLibraryWindow(tracks, windowStart),
    [tracks, windowStart]
  );

  useEffect(() => {
    setWindowStart(0);
  }, [collectionKey]);

  return (
    <>
      {tracks.length > visibleWindow.items.length ? (
        <div className="track-window-controls" role="group" aria-label="Окно строк библиотеки">
          <button
            className="track-window-previous-button"
            type="button"
            title="Показать предыдущие строки из загруженного набора"
            disabled={!visibleWindow.hasPrevious}
            onClick={() => setWindowStart(
              shiftLibraryWindow(tracks.length, visibleWindow.start, -1).start
            )}
          >
            Предыдущие строки
          </button>
          <span className="track-window-status" aria-live="polite">
            {visibleWindow.start + 1}–{visibleWindow.end} / {tracks.length}
          </span>
          <button
            className="track-window-next-button"
            type="button"
            title="Показать следующие строки из загруженного набора"
            disabled={!visibleWindow.hasNext}
            onClick={() => setWindowStart(
              shiftLibraryWindow(tracks.length, visibleWindow.start, 1).start
            )}
          >
            Следующие строки
          </button>
        </div>
      ) : null}
      <div className="track-list">
      {visibleWindow.items.map((track) => {
        const trackPreviewActive = playingTrackId === track.track_id;
        return (
          <div className="track-row" key={libraryTrackIdentityKey(track)}>
            <button className="icon-button track-preview-button" title={trackPreviewActive ? "Pause preview" : "Preview"} aria-label={`${trackPreviewActive ? "Pause" : "Preview"} ${displayTrack(track)}`} onClick={() => onPreview(track)} type="button">
              {trackPreviewActive ? <Pause size={15} /> : <Play size={15} />}
            </button>
            <div className="track-title-cell">
              <strong>{displayTrack(track)}</strong>
            </div>
            <button className="icon-button track-metadata-button" title="Теги и жанры" aria-label={`Теги ${displayTrack(track)}`} onClick={() => onDetails(track)} type="button"><Tags size={15} /></button>
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
    </>
  );
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
      <button className="icon-button result-metadata-button" title="Теги и жанры" aria-label={`Теги ${displayTrack(track)}`} onClick={(event) => { event.stopPropagation(); onDetails(track); }} type="button"><Tags size={15} /></button>
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
