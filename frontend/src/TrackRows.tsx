import { Heart, Minus, Play, Plus, Search, Tags } from "lucide-react";
import { Track } from "./api";
import { displayTrack, trackInfo } from "./trackDisplay";

type TrackActions = {
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
  return (
    <div className="track-list">
      {tracks.map((track) => {
        return (
          <div className="track-row" key={track.id}>
            <button className="icon-button track-preview-button" title="Preview" aria-label={`Preview ${displayTrack(track)}`} onClick={() => onPreview(track)}><Play size={15} /></button>
            <div className="track-copy">
              <strong>{displayTrack(track)}</strong>
              <span>{trackInfo(track)}</span>
            </div>
            <button className="icon-button track-metadata-button" title="Теги и жанры" aria-label={`Теги ${displayTrack(track)}`} onClick={() => onDetails(track)}><Tags size={15} /></button>
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
            <button className={`icon-button track-seed-button ${seedSet.has(track.id) ? "active" : ""}`} title="Seed" aria-label={`Seed ${displayTrack(track)}`} onClick={() => onSeed(track)}><Search size={15} /></button>
            <button
              className={`icon-button track-playlist-toggle-button ${playlistSet.has(track.id) ? "intent-remove active" : "intent-add"}`}
              title={playlistSet.has(track.id) ? "Убрать из сета" : "В сет"}
              aria-label={playlistSet.has(track.id) ? `Убрать ${displayTrack(track)} из сета` : `Добавить ${displayTrack(track)} в сет`}
              onClick={() => onTogglePlaylist(track)}
            >
              {playlistSet.has(track.id) ? <Minus size={15} /> : <Plus size={15} />}
            </button>
          </div>
        );
      })}
    </div>
  );
}

export function ResultRow({
  track,
  score,
  scoreBreakdown,
  isSeed,
  inPlaylist,
  onSeed,
  onTogglePlaylist,
  onPreview,
  onDetails
}: TrackActions & {
  track: Track;
  score: number;
  scoreBreakdown?: Record<string, number> | null;
  isSeed: boolean;
  inPlaylist: boolean;
}) {
  const breakdownTitle = scoreBreakdownTitle(scoreBreakdown);
  return (
    <div className="result-row">
      <button className="icon-button result-preview-button" title="Preview" aria-label={`Preview ${displayTrack(track)}`} onClick={() => onPreview(track)}><Play size={15} /></button>
      <div className="track-copy">
        <strong>{displayTrack(track)}</strong>
        <span>{trackInfo(track)}</span>
      </div>
      <button className="icon-button result-metadata-button" title="Теги и жанры" aria-label={`Теги ${displayTrack(track)}`} onClick={() => onDetails(track)}><Tags size={15} /></button>
      <meter min={0} max={1} value={Math.max(0, Math.min(1, score))} title={breakdownTitle} />
      <span className="score" title={breakdownTitle}>{score.toFixed(3)}</span>
      <button className={`icon-button result-seed-button ${isSeed ? "active" : ""}`} title="Seed" aria-label={`Seed ${displayTrack(track)}`} onClick={() => onSeed(track)}><Search size={15} /></button>
      <button
        className={`icon-button result-playlist-toggle-button ${inPlaylist ? "intent-remove active" : "intent-add"}`}
        title={inPlaylist ? "Убрать из сета" : "В сет"}
        aria-label={inPlaylist ? `Убрать ${displayTrack(track)} из сета` : `Добавить ${displayTrack(track)} в сет`}
        onClick={() => onTogglePlaylist(track)}
      >
        {inPlaylist ? <Minus size={15} /> : <Plus size={15} />}
      </button>
    </div>
  );
}

function scoreBreakdownTitle(scoreBreakdown?: Record<string, number> | null) {
  if (!scoreBreakdown || !Object.keys(scoreBreakdown).length) return "Similarity score";
  return Object.entries(scoreBreakdown)
    .map(([key, value]) => `${key.replaceAll("_", " ")}: ${value.toFixed(3)}`)
    .join("\n");
}
