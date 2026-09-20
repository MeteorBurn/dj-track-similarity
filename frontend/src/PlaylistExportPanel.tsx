import { useEffect, useState } from "react";
import { Download, FolderOpen, ListMusic, ListPlus, Pause, Play, Tags, Trash2 } from "lucide-react";
import type { Track } from "./api";
import { helpText } from "./helpText";
import { playlistPage } from "./playlistView";
import { displayTrack } from "./trackDisplay";

const playlistPageSize = 20;

export function PlaylistExportPanel({
  playlist,
  playlistName,
  onPlaylistNameChange,
  outputDir,
  onOutputDirChange,
  onChooseOutputFolder,
  busy,
  playingTrackId,
  setPreview,
  setMetadataTrack,
  removeFromPlaylist,
  handleSaveToCollection,
  handleExport
}: {
  playlist: Track[];
  playlistName: string;
  onPlaylistNameChange: (value: string) => void;
  outputDir: string;
  onOutputDirChange: (value: string) => void;
  onChooseOutputFolder: () => void;
  busy: boolean;
  playingTrackId: number | null;
  setPreview: (track: Track) => void;
  setMetadataTrack: (track: Track) => void;
  removeFromPlaylist: (trackId: number) => void;
  handleSaveToCollection: () => void;
  handleExport: (format: "m3u" | "csv") => void;
}) {
  const [playlistOffset, setPlaylistOffset] = useState(0);
  const playlistPageState = playlistPage(playlist, playlistOffset, playlistPageSize);

  useEffect(() => {
    if (playlistPageState.offset !== playlistOffset) {
      setPlaylistOffset(playlistPageState.offset);
    }
  }, [playlistOffset, playlistPageState.offset]);

  return (
    <aside className="panel playlist-export-panel" aria-labelledby="playlist-export-title">
      <div className="panel-title">
        <ListMusic size={18} aria-hidden="true" />
        <h2 id="playlist-export-title">4. Сет и экспорт</h2>
        <span className="panel-counter">{playlist.length}</span>
      </div>
      <section className="playlist-export-section" aria-label="Сет и экспорт">
        <input name="playlist-name" value={playlistName} onChange={(event) => onPlaylistNameChange(event.target.value)} title={helpText.playlistName} />
        <span className={`save-state ${playlist.length ? "dirty" : ""}`}>
          {playlist.length ? "Экспорт сохранит текущий сет" : "Сет пуст"}
        </span>
        {playlist.length > playlistPageSize ? (
          <div className="playlist-page-controls" aria-label="Пагинация сета">
            <span className="library-page-status">
              {playlistPageState.pageStart}–{playlistPageState.pageEnd} из {playlistPageState.total}
            </span>
            <button className="playlist-page-previous-button" title="Предыдущая страница сета" disabled={!playlistPageState.canGoBack} onClick={() => setPlaylistOffset((current) => Math.max(0, current - playlistPageSize))} type="button">Prev</button>
            <button className="playlist-page-next-button" title="Следующая страница сета" disabled={!playlistPageState.canGoForward} onClick={() => setPlaylistOffset((current) => current + playlistPageSize)} type="button">Next</button>
          </div>
        ) : null}
        <div className="playlist-list">
          {playlist.length === 0 ? (
            <div className="empty-state">
              Сет пуст
            </div>
          ) : (
            playlistPageState.items.map((track, index) => {
              const trackPreviewActive = playingTrackId === track.track_id;
              return (
                <div className="playlist-row" key={track.track_id}>
                  <span className="row-index">{playlistPageState.offset + index + 1}</span>
                  <button className="icon-button playlist-preview-button" title={trackPreviewActive ? "Pause preview" : "Preview"} aria-label={`${trackPreviewActive ? "Pause" : "Preview"} ${displayTrack(track)}`} onClick={() => setPreview(track)} type="button">
                    {trackPreviewActive ? <Pause size={15} /> : <Play size={15} />}
                  </button>
                  <div className="track-title-cell">
                    <strong>{displayTrack(track)}</strong>
                  </div>
                  <button className="icon-button playlist-metadata-button" title="Теги и жанры" aria-label={`Теги ${displayTrack(track)}`} onClick={() => setMetadataTrack(track)} type="button"><Tags size={15} /></button>
                  <button className="icon-button intent-remove playlist-remove-button" title="Убрать из сета" aria-label={`Убрать ${displayTrack(track)} из сета`} onClick={() => removeFromPlaylist(track.track_id)} type="button"><Trash2 size={15} /></button>
                </div>
              );
            })
          )}
        </div>
        <div className="path-row output-row">
          <input name="export-output-dir" value={outputDir} onChange={(event) => onOutputDirChange(event.target.value)} placeholder="D:/Exports" title={helpText.outputDir} />
          <button className="icon-button folder-picker export-folder-picker-button" title="Выбрать папку экспорта" aria-label="Выбрать папку экспорта" disabled={busy} onClick={onChooseOutputFolder} type="button">
            <FolderOpen size={17} />
          </button>
        </div>
        <div className="export-action-row">
          <button className="save-collection-button" title="Сохранить текущий сет в Rhythm Lab Collection" disabled={busy || !playlist.length} onClick={handleSaveToCollection} type="button"><ListPlus size={16} />Collection</button>
          <button className="export-m3u-button" title="Экспортировать текущий сет в M3U" disabled={busy || !playlist.length} onClick={() => handleExport("m3u")} type="button"><Download size={16} />M3U</button>
          <button className="export-csv-button" title="Экспортировать текущий сет в CSV" disabled={busy || !playlist.length} onClick={() => handleExport("csv")} type="button"><Download size={16} />CSV</button>
        </div>
      </section>
    </aside>
  );
}
