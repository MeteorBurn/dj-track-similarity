import { Dispatch, SetStateAction, useState } from "react";
import { Download, FolderOpen, ListMusic, Play, Save, Search, Tags, Trash2, X } from "lucide-react";
import { SearchResult, SonaraSearchMode, Track } from "./api";
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
  sonaraMode: SonaraSearchMode;
};

type SearchHelpText = {
  textPrompt: string;
  similarity: string;
  sonaraMode: string;
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
  onChooseOutputFolder,
  helpText,
  removeSeed,
  handleTextSearch,
  handleSonaraSearch,
  handleMertSearch,
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
  onChooseOutputFolder: () => void;
  helpText: SearchHelpText;
  removeSeed: (trackId: number) => void;
  handleTextSearch: () => void;
  handleSonaraSearch: () => void;
  handleMertSearch: () => void;
  addSeed: (track: Track) => void;
  togglePlaylist: (track: Track) => void;
  setPreview: (track: Track) => void;
  setMetadataTrack: (track: Track) => void;
  removeFromPlaylist: (trackId: number) => void;
  handleCreatePlaylist: () => void;
  handleExport: (format: "m3u" | "csv") => void;
  handleTags: (apply: boolean) => void;
}) {
  const [activeSearchTab, setActiveSearchTab] = useState<"sonara" | "mert" | "clap">("sonara");
  const modeOptions: Array<{ value: SonaraSearchMode; label: string }> = [
    { value: "balanced", label: "Balanced" },
    { value: "vibe", label: "Vibe" },
    { value: "sound", label: "Sound" },
    { value: "dj_transition", label: "DJ" }
  ];

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
        <div className="search-tabs" role="tablist" aria-label="Search model">
          <button className={activeSearchTab === "sonara" ? "active" : ""} onClick={() => setActiveSearchTab("sonara")} role="tab" aria-selected={activeSearchTab === "sonara"} type="button">
            SONARA
          </button>
          <button className={activeSearchTab === "mert" ? "active" : ""} onClick={() => setActiveSearchTab("mert")} role="tab" aria-selected={activeSearchTab === "mert"} type="button">
            MERT
          </button>
          <button className={activeSearchTab === "clap" ? "active" : ""} onClick={() => setActiveSearchTab("clap")} role="tab" aria-selected={activeSearchTab === "clap"} type="button">
            CLAP
          </button>
        </div>
        {activeSearchTab === "sonara" && (
          <div className="search-tab-panel" role="tabpanel">
            <label className="mode-selector" title={helpText.sonaraMode}>
              <span>Mode</span>
              <div className="segmented sonara-mode-segmented">
                {modeOptions.map((option) => (
                  <button className={filters.sonaraMode === option.value ? "active" : ""} key={option.value} onClick={() => setFilters({ ...filters, sonaraMode: option.value })} title={helpText.sonaraMode} type="button">
                    {option.label}
                  </button>
                ))}
              </div>
            </label>
            <div className="filters compact-filters">
              <label title={helpText.similarity}>Similarity<input type="number" value={filters.minSimilarity} min={0} max={1} step={0.01} title={helpText.similarity} onChange={(event) => setFilters({ ...filters, minSimilarity: Number(event.target.value) })} /></label>
              <label title={helpText.lookback}>Lookback<input type="number" value={filters.lookback} min={0} max={12} title={helpText.lookback} onChange={(event) => setFilters({ ...filters, lookback: Number(event.target.value) })} /></label>
              <label title={helpText.limit}>Limit<input type="number" value={filters.limit} min={1} max={500} title={helpText.limit} onChange={(event) => setFilters({ ...filters, limit: Number(event.target.value) })} /></label>
            </div>
            <button className="primary" disabled={busy || !seeds.length} onClick={handleSonaraSearch}>
              <Search size={17} />
              SONARA search
            </button>
          </div>
        )}
        {activeSearchTab === "mert" && (
          <div className="search-tab-panel" role="tabpanel">
            <div className="filters compact-filters">
              <label title={helpText.similarity}>Similarity<input type="number" value={filters.minSimilarity} min={0} max={1} step={0.01} title={helpText.similarity} onChange={(event) => setFilters({ ...filters, minSimilarity: Number(event.target.value) })} /></label>
              <label title={helpText.lookback}>Lookback<input type="number" value={filters.lookback} min={0} max={12} title={helpText.lookback} onChange={(event) => setFilters({ ...filters, lookback: Number(event.target.value) })} /></label>
              <label title={helpText.limit}>Limit<input type="number" value={filters.limit} min={1} max={500} title={helpText.limit} onChange={(event) => setFilters({ ...filters, limit: Number(event.target.value) })} /></label>
            </div>
            <button className="primary" disabled={busy || !seeds.length} onClick={handleMertSearch}>
              <Search size={17} />
              MERT search
            </button>
          </div>
        )}
        {activeSearchTab === "clap" && (
          <div className="search-tab-panel" role="tabpanel">
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
            </div>
            <div className="filters compact-filters">
              <label title={helpText.similarity}>Similarity<input type="number" value={filters.minSimilarity} min={0} max={1} step={0.01} title={helpText.similarity} onChange={(event) => setFilters({ ...filters, minSimilarity: Number(event.target.value) })} /></label>
              <label title={helpText.limit}>Limit<input type="number" value={filters.limit} min={1} max={500} title={helpText.limit} onChange={(event) => setFilters({ ...filters, limit: Number(event.target.value) })} /></label>
            </div>
            <button className="primary" disabled={busy || !textQuery.trim()} onClick={handleTextSearch}>
              <Search size={17} />
              CLAP text
            </button>
          </div>
        )}
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
          <button className="icon-button folder-picker" title="Выбрать папку экспорта" aria-label="Выбрать папку экспорта" disabled={busy} onClick={onChooseOutputFolder} type="button">
            <FolderOpen size={17} />
          </button>
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
