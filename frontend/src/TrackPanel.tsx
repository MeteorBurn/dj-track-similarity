import { AudioWaveform, ListMusic, Plus, Save, Search } from "lucide-react";
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
  total,
  offset,
  loading,
  canGoBack,
  canGoForward,
  onPreviousPage,
  onNextPage,
  busy,
  maestGenreTrackCount,
  writeMaestGenresHelp,
  onWriteMaestGenres,
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
  total: number;
  offset: number;
  loading: boolean;
  canGoBack: boolean;
  canGoForward: boolean;
  onPreviousPage: () => void;
  onNextPage: () => void;
  busy: boolean;
  maestGenreTrackCount: number;
  writeMaestGenresHelp: string;
  onWriteMaestGenres: () => void;
  seedSet: Set<number>;
  playlistSet: Set<number>;
  librarySearchHelp: string;
  onAddVisibleTracks: () => void;
  onSeed: (track: Track) => void;
  onTogglePlaylist: (track: Track) => void;
  onPreview: (track: Track) => void;
  onDetails: (track: Track) => void;
}) {
  const pageStart = total && tracks.length ? offset + 1 : 0;
  const pageEnd = Math.min(offset + tracks.length, total);
  const addVisibleTitle = total === 0
    ? "Нет отфильтрованных треков для добавления"
    : "Добавить все отфильтрованные треки в сет с учетом поиска, preset-фильтра и всех страниц. Уже добавленные треки будут пропущены.";
  return (
    <section className="panel track-panel">
      <div className="panel-title">
        <ListMusic size={18} />
        <h2>2. Библиотека и прослушивание</h2>
        <div className="panel-title-actions track-panel-actions">
          <button
            className="icon-button intent-add add-visible-tracks-button"
            title={addVisibleTitle}
            aria-label="Добавить все отфильтрованные треки в сет"
            disabled={busy || total === 0}
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
          className="icon-button genre-save-button"
          title={`${writeMaestGenresHelp} Доступно: ${maestGenreTrackCount}.`}
          aria-label="Сохранить MAEST жанры в теги всех доступных треков"
          disabled={busy || !maestGenreTrackCount}
          onClick={onWriteMaestGenres}
          type="button"
        >
          <Save size={16} />
        </button>
        <button
          className={`icon-button library-preset-button ${libraryPreset === "syncopated" ? "active" : ""}`}
          title="Показать только треки с сохранённым MAEST-флагом syncopated rhythm"
          aria-label="Показать только треки с сохранённым MAEST-флагом syncopated rhythm"
          aria-pressed={libraryPreset === "syncopated"}
          onClick={() => onToggleLibraryPreset("syncopated")}
          type="button"
        >
          <AudioWaveform size={16} />
        </button>
        <span className="library-page-status">
          {loading ? "Загрузка..." : `${pageStart}-${pageEnd} из ${total}`}
        </span>
        <button className="secondary-mini library-page-previous-button" disabled={!canGoBack} onClick={onPreviousPage} type="button">Prev</button>
        <button className="secondary-mini library-page-next-button" disabled={!canGoForward} onClick={onNextPage} type="button">Next</button>
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
