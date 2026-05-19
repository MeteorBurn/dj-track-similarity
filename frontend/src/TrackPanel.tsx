import { AudioWaveform, ListMusic, Plus, Search } from "lucide-react";
import { Track } from "./api";
import type { LibraryPreset } from "./libraryView";
import { TrackList } from "./TrackRows";
import { displayTrack } from "./trackDisplay";

export function TrackPanel({
  query,
  onQueryChange,
  libraryPreset,
  onToggleLibraryPreset,
  preview,
  tracks,
  seedSet,
  playlistSet,
  librarySearchHelp,
  onAddVisibleTracks,
  onSeed,
  onTogglePlaylist,
  onPreview,
  onDetails
}: {
  query: string;
  onQueryChange: (value: string) => void;
  libraryPreset: LibraryPreset;
  onToggleLibraryPreset: (preset: LibraryPreset) => void;
  preview: Track | null;
  tracks: Track[];
  seedSet: Set<number>;
  playlistSet: Set<number>;
  librarySearchHelp: string;
  onAddVisibleTracks: () => void;
  onSeed: (track: Track) => void;
  onTogglePlaylist: (track: Track) => void;
  onPreview: (track: Track) => void;
  onDetails: (track: Track) => void;
}) {
  const newVisibleTracks = tracks.filter((track) => !playlistSet.has(track.id)).length;
  const addVisibleTitle = tracks.length === 0
    ? "Нет видимых треков для добавления"
    : newVisibleTracks === 0
      ? "Все видимые треки уже в сете"
      : "Добавить все видимые треки в сет. Уже добавленные треки будут пропущены.";
  return (
    <section className="panel track-panel">
      <div className="panel-title">
        <ListMusic size={18} />
        <h2>2. Библиотека и прослушивание</h2>
        <div className="panel-title-actions track-panel-actions">
          <button
            className="icon-button intent-add"
            title={addVisibleTitle}
            aria-label="Добавить все видимые треки в сет"
            disabled={!newVisibleTracks}
            onClick={onAddVisibleTracks}
            type="button"
          >
            <Plus size={16} />
          </button>
        </div>
      </div>
      <div className="search-input">
        <Search size={16} />
        <input value={query} onChange={(event) => onQueryChange(event.target.value)} placeholder="artist, title, genre, path" title={librarySearchHelp} />
      </div>
      <div className="library-view-controls">
        <button
          className={`icon-button library-preset-button ${libraryPreset === "syncopated" ? "active" : ""}`}
          title="Показать только треки с syncopated rhythm по MAEST-жанрам"
          aria-label="Показать только треки с syncopated rhythm по MAEST-жанрам"
          aria-pressed={libraryPreset === "syncopated"}
          onClick={() => onToggleLibraryPreset("syncopated")}
          type="button"
        >
          <AudioWaveform size={16} />
        </button>
      </div>
      <div className="player library-player">
        <span>{preview ? displayTrack(preview) : "Preview"}</span>
        {preview && <audio controls src={`/media/${preview.id}`} />}
      </div>
      <TrackList
        tracks={tracks}
        seedSet={seedSet}
        playlistSet={playlistSet}
        onSeed={onSeed}
        onTogglePlaylist={onTogglePlaylist}
        onPreview={onPreview}
        onDetails={onDetails}
      />
    </section>
  );
}
