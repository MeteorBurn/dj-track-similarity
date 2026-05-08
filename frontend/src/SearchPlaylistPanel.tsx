import { Dispatch, SetStateAction } from "react";
import { Download, ListMusic, Play, Save, Search, Tags, Trash2, X } from "lucide-react";
import { SearchResult, Track } from "./api";
import { ResultRow } from "./TrackRows";
import { displayTrack, trackInfo } from "./trackDisplay";

export type SearchFiltersState = {
  bpmTolerance: number;
  keyCompatibility: boolean;
  energyEnabled: boolean;
  energyMin: number;
  energyMax: number;
  minSimilarity: number;
  epsilon: number;
  noise: number;
  lookback: number;
  limit: number;
};

type SearchHelpText = {
  textPrompt: string;
  disabledBpm: string;
  disabledEpsilon: string;
  disabledNoise: string;
  disabledEnergy: string;
  disabledKey: string;
  similarity: string;
  lookback: string;
  limit: string;
  playlistName: string;
  outputDir: string;
};

export function SearchPlaylistPanel({
  seedTracks,
  textQuery,
  onTextQueryChange,
  busy,
  filters,
  setFilters,
  seeds,
  results,
  seedSet,
  playlistSet,
  playlist,
  playlistName,
  onPlaylistNameChange,
  playlistId,
  outputDir,
  onOutputDirChange,
  helpText,
  removeSeed,
  handleTextSearch,
  handleSearch,
  addSeed,
  togglePlaylist,
  setPreview,
  setMetadataTrack,
  removeFromPlaylist,
  handleCreatePlaylist,
  handleExport,
  handleTags
}: {
  seedTracks: Track[];
  textQuery: string;
  onTextQueryChange: (value: string) => void;
  busy: boolean;
  filters: SearchFiltersState;
  setFilters: Dispatch<SetStateAction<SearchFiltersState>>;
  seeds: number[];
  results: SearchResult[];
  seedSet: Set<number>;
  playlistSet: Set<number>;
  playlist: Track[];
  playlistName: string;
  onPlaylistNameChange: (value: string) => void;
  playlistId: number | null;
  outputDir: string;
  onOutputDirChange: (value: string) => void;
  helpText: SearchHelpText;
  removeSeed: (trackId: number) => void;
  handleTextSearch: () => void;
  handleSearch: () => void;
  addSeed: (track: Track) => void;
  togglePlaylist: (track: Track) => void;
  setPreview: (track: Track) => void;
  setMetadataTrack: (track: Track) => void;
  removeFromPlaylist: (trackId: number) => void;
  handleCreatePlaylist: () => void;
  handleExport: (format: "m3u" | "csv") => void;
  handleTags: (apply: boolean) => void;
}) {
  return (
    <aside className="panel search-panel">
      <section className="search-section">
        <div className="panel-title">
          <Search size={18} />
          <h2>3. Поиск и прослушивание</h2>
        </div>
        <div className="seed-strip">
          {seedTracks.map((track) => (
            <button className="seed-chip" key={track.id} onClick={() => removeSeed(track.id)}>
              {displayTrack(track)}
              <X size={14} />
            </button>
          ))}
        </div>
        <div className="mert-mode-note">
          Seed search использует MERT. Text search использует CLAP и требует отдельного CLAP-анализа библиотеки.
        </div>
        <div className="text-search-box">
          <label title={helpText.textPrompt}>
            Text query
            <input
              value={textQuery}
              onChange={(event) => onTextQueryChange(event.target.value)}
              placeholder="dark hypnotic techno, rolling bass, no vocals"
              title={helpText.textPrompt}
            />
          </label>
          <button disabled={busy || !textQuery.trim()} onClick={handleTextSearch}>
            <Search size={16} />
            Text
          </button>
        </div>
        <div className="filters">
          <label className="disabled-filter" title={helpText.disabledBpm}><span>BPM ±</span><input type="number" disabled value={filters.bpmTolerance} min={0} max={32} title={helpText.disabledBpm} onChange={(event) => setFilters({ ...filters, bpmTolerance: Number(event.target.value) })} /></label>
          <label title={helpText.similarity}>Similarity<input type="number" value={filters.minSimilarity} min={0} max={1} step={0.01} title={helpText.similarity} onChange={(event) => setFilters({ ...filters, minSimilarity: Number(event.target.value) })} /></label>
          <label className="disabled-filter" title={helpText.disabledEpsilon}><span>Epsilon</span><input type="number" disabled value={filters.epsilon} min={0} max={1} step={0.01} title={helpText.disabledEpsilon} onChange={(event) => setFilters({ ...filters, epsilon: Number(event.target.value) })} /></label>
          <label className="disabled-filter" title={helpText.disabledNoise}><span>Noise</span><input type="number" disabled value={filters.noise} min={0} max={1} step={0.01} title={helpText.disabledNoise} onChange={(event) => setFilters({ ...filters, noise: Number(event.target.value) })} /></label>
          <label title={helpText.lookback}>Lookback<input type="number" value={filters.lookback} min={0} max={12} title={helpText.lookback} onChange={(event) => setFilters({ ...filters, lookback: Number(event.target.value) })} /></label>
          <label className="disabled-filter" title={helpText.disabledEnergy}><span>Energy min</span><input type="number" disabled value={filters.energyMin} min={0} max={1} step={0.01} title={helpText.disabledEnergy} onChange={(event) => setFilters({ ...filters, energyMin: Number(event.target.value) })} /></label>
          <label className="disabled-filter" title={helpText.disabledEnergy}><span>Energy max</span><input type="number" disabled value={filters.energyMax} min={0} max={1} step={0.01} title={helpText.disabledEnergy} onChange={(event) => setFilters({ ...filters, energyMax: Number(event.target.value) })} /></label>
          <label title={helpText.limit}>Limit<input type="number" value={filters.limit} min={1} max={500} title={helpText.limit} onChange={(event) => setFilters({ ...filters, limit: Number(event.target.value) })} /></label>
          <label className="toggle disabled-filter" title={helpText.disabledKey}><input type="checkbox" disabled checked={filters.keyCompatibility} onChange={(event) => setFilters({ ...filters, keyCompatibility: event.target.checked })} />Key</label>
          <label className="toggle disabled-filter" title={helpText.disabledEnergy}><input type="checkbox" disabled checked={filters.energyEnabled} onChange={(event) => setFilters({ ...filters, energyEnabled: event.target.checked })} />Energy</label>
        </div>
        <button className="primary" disabled={busy || !seeds.length} onClick={handleSearch}>
          <Search size={17} />
          Seed search
        </button>
        <div className="results-list">
          {results.map(({ track, score }) => (
            <ResultRow
              key={track.id}
              track={track}
              score={score}
              isSeed={seedSet.has(track.id)}
              inPlaylist={playlistSet.has(track.id)}
              onSeed={addSeed}
              onTogglePlaylist={togglePlaylist}
              onPreview={setPreview}
              onDetails={setMetadataTrack}
            />
          ))}
        </div>
      </section>
      <section className="playlist-section">
        <div className="panel-title">
          <ListMusic size={18} />
          <h2>Сет и экспорт</h2>
          <span className="panel-counter">{playlist.length}</span>
        </div>
        <input value={playlistName} onChange={(event) => onPlaylistNameChange(event.target.value)} title={helpText.playlistName} />
        <span className={`save-state ${playlistId ? "saved" : "dirty"}`}>
          {playlistId ? `Сохранен #${playlistId}` : playlist.length ? "Есть несохраненные изменения" : "Сет пуст"}
        </span>
        <div className="playlist-list">
          {playlist.length === 0 ? (
            <div className="empty-state">
              Сет пуст
            </div>
          ) : (
            playlist.map((track, index) => (
              <div className="playlist-row" key={track.id}>
                <span className="row-index">{index + 1}</span>
                <button className="icon-button" title="Preview" aria-label={`Preview ${displayTrack(track)}`} onClick={() => setPreview(track)}><Play size={15} /></button>
                <div className="track-copy">
                  <strong>{displayTrack(track)}</strong>
                  <span>{trackInfo(track)}</span>
                </div>
                <button className="icon-button" title="Теги и жанры" aria-label={`Теги ${displayTrack(track)}`} onClick={() => setMetadataTrack(track)}><Tags size={15} /></button>
                <button className="icon-button intent-remove" title="Убрать из сета" aria-label={`Убрать ${displayTrack(track)} из сета`} onClick={() => removeFromPlaylist(track.id)}><Trash2 size={15} /></button>
              </div>
            ))
          )}
        </div>
        <button className="primary" disabled={busy || !playlist.length} onClick={handleCreatePlaylist}>
          <Save size={17} />
          Сохранить
        </button>
        <div className="path-row output-row">
          <input value={outputDir} onChange={(event) => onOutputDirChange(event.target.value)} placeholder="D:/Exports" title={helpText.outputDir} />
        </div>
        <div className="action-row">
          <button disabled={busy || !playlistId} onClick={() => handleExport("m3u")}><Download size={16} />M3U</button>
          <button disabled={busy || !playlistId} onClick={() => handleExport("csv")}><Download size={16} />CSV</button>
        </div>
        <div className="action-row">
          <button disabled={busy} onClick={() => handleTags(false)}><Tags size={16} />Preview</button>
          <button disabled={busy} onClick={() => handleTags(true)}><Tags size={16} />Write</button>
        </div>
      </section>
    </aside>
  );
}
