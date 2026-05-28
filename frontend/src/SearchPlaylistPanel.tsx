import { Dispatch, Fragment, SetStateAction, useEffect, useState } from "react";
import { Download, FolderOpen, ListMusic, Play, Search, SlidersHorizontal, Tags, Trash2, X } from "lucide-react";
import { AnalysisJobStatus, PromotedClassifier, SearchResult, SonaraMixerWeights, SonaraModifiers, Track } from "./api";
import { playlistPage } from "./playlistView";
import { ResultRow } from "./TrackRows";
import { displayTrack, trackInfo } from "./trackDisplay";

const playlistPageSize = 200;

export type SearchFiltersState = {
  minSimilarity: number;
  lookback: number;
  limit: number;
  sonaraMixer: SonaraMixerWeights;
  sonaraModifiers: SonaraModifiers;
};

type SearchHelpText = {
  textPrompt: string;
  similarity: string;
  lookback: string;
  limit: string;
  sonaraMixerTimbre: string;
  sonaraMixerRhythm: string;
  sonaraMixerDynamics: string;
  sonaraMixerHarmonic: string;
  sonaraMixerTempo: string;
  sonaraModifierEnergy: string;
  sonaraModifierValence: string;
  sonaraModifierAcousticness: string;
  sonaraModifierBrightness: string;
  sonaraModifierRhythmDensity: string;
  sonaraModifierDynamicRange: string;
  sonaraModifierLoudness: string;
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
  outputDir,
  onOutputDirChange,
  onChooseOutputFolder,
  helpText,
  classifiers,
  classifierMinScores,
  onClassifierMinScoreChange,
  classifierJob,
  removeSeed,
  handleTextSearch,
  handleSonaraSearch,
  handleMertSearch,
  handleClassifierAnalyze,
  handleResetClassifiers,
  addSeed,
  togglePlaylist,
  setPreview,
  setMetadataTrack,
  removeFromPlaylist,
  handleExport
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
  outputDir: string;
  onOutputDirChange: (value: string) => void;
  onChooseOutputFolder: () => void;
  helpText: SearchHelpText;
  classifiers: PromotedClassifier[];
  classifierMinScores: Record<string, number>;
  onClassifierMinScoreChange: (classifier: string, value: number) => void;
  classifierJob: AnalysisJobStatus | null;
  removeSeed: (trackId: number) => void;
  handleTextSearch: () => void;
  handleSonaraSearch: () => void;
  handleMertSearch: () => void;
  handleClassifierAnalyze: () => void;
  handleResetClassifiers: () => void;
  addSeed: (track: Track) => void;
  togglePlaylist: (track: Track) => void;
  setPreview: (track: Track) => void;
  setMetadataTrack: (track: Track) => void;
  removeFromPlaylist: (trackId: number) => void;
  handleExport: (format: "m3u" | "csv") => void;
}) {
  const [activeSearchTab, setActiveSearchTab] = useState<"sonara" | "mert" | "clap" | "class">("sonara");
  const [playlistOffset, setPlaylistOffset] = useState(0);
  const playlistPageState = playlistPage(playlist, playlistOffset, playlistPageSize);
  useEffect(() => {
    if (playlistPageState.offset !== playlistOffset) {
      setPlaylistOffset(playlistPageState.offset);
    }
  }, [playlistOffset, playlistPageState.offset]);
  const mixerControls: Array<{ key: keyof SonaraMixerWeights; label: string; title: string }> = [
    { key: "timbre", label: "Timbre", title: helpText.sonaraMixerTimbre },
    { key: "rhythm", label: "Rhythm", title: helpText.sonaraMixerRhythm },
    { key: "dynamics", label: "Dynamics", title: helpText.sonaraMixerDynamics },
    { key: "harmonic", label: "Harmonic", title: helpText.sonaraMixerHarmonic },
    { key: "tempo", label: "Tempo", title: helpText.sonaraMixerTempo }
  ];
  const modifierControls: Array<{ key: keyof SonaraModifiers; label: string; title: string }> = [
    { key: "energy", label: "Energy", title: helpText.sonaraModifierEnergy },
    { key: "valence", label: "Valence", title: helpText.sonaraModifierValence },
    { key: "acousticness", label: "Acoustic", title: helpText.sonaraModifierAcousticness },
    { key: "brightness", label: "Bright", title: helpText.sonaraModifierBrightness },
    { key: "rhythm_density", label: "Density", title: helpText.sonaraModifierRhythmDensity },
    { key: "dynamic_range", label: "Range", title: helpText.sonaraModifierDynamicRange },
    { key: "loudness", label: "LUFS", title: helpText.sonaraModifierLoudness }
  ];

  function setSonaraMixerValue(key: keyof SonaraMixerWeights, value: number) {
    setFilters((current) => ({ ...current, sonaraMixer: { ...current.sonaraMixer, [key]: value } }));
  }

  function setSonaraModifierValue(key: keyof SonaraModifiers, value: number) {
    setFilters((current) => ({ ...current, sonaraModifiers: { ...current.sonaraModifiers, [key]: value } }));
  }

  function resetCustomSonara() {
    setFilters((current) => ({
      ...current,
      sonaraMixer: { timbre: 1, rhythm: 1, dynamics: 0.8, harmonic: 0.8, tempo: 0.35 },
      sonaraModifiers: { energy: 0, valence: 0, acousticness: 0, brightness: 0, rhythm_density: 0, dynamic_range: 0, loudness: 0 }
    }));
  }

  return (
    <aside className="panel search-panel">
      <section className="search-section">
        <div className="panel-title">
          <Search size={18} />
          <h2>3. Поиск и прослушивание</h2>
        </div>
        <div className="seed-strip">
          {seedTracks.map((track) => (
            <button className="seed-remove-chip" key={track.id} title={`Убрать seed: ${displayTrack(track)}`} onClick={() => removeSeed(track.id)}>
              {displayTrack(track)}
              <X size={14} />
            </button>
          ))}
        </div>
        <div className="search-tabs" role="tablist" aria-label="Search model">
          <button className={`model-search-tab ${activeSearchTab === "sonara" ? "active" : ""}`} title="SONARA similarity search" onClick={() => setActiveSearchTab("sonara")} role="tab" aria-selected={activeSearchTab === "sonara"} type="button">
            SONARA
          </button>
          <button className={`model-search-tab ${activeSearchTab === "mert" ? "active" : ""}`} title="MERT seed search" onClick={() => setActiveSearchTab("mert")} role="tab" aria-selected={activeSearchTab === "mert"} type="button">
            MERT
          </button>
          <button className={`model-search-tab ${activeSearchTab === "clap" ? "active" : ""}`} title="CLAP text search" onClick={() => setActiveSearchTab("clap")} role="tab" aria-selected={activeSearchTab === "clap"} type="button">
            CLAP
          </button>
          <button className={`model-search-tab ${activeSearchTab === "class" ? "active" : ""}`} title="Classifier controls" onClick={() => setActiveSearchTab("class")} role="tab" aria-selected={activeSearchTab === "class"} type="button">
            CLASS
          </button>
        </div>
        {activeSearchTab === "sonara" && (
          <div className="search-tab-panel" role="tabpanel">
            <div className="sonara-custom-controls">
              <div className="custom-control-header">
                <span>Mixer</span>
                <button className="sonara-mixer-reset-button" title="Сбросить SONARA mixer и modifiers" type="button" onClick={resetCustomSonara}>Reset</button>
              </div>
              <div className="range-grid mixer-grid">
                {mixerControls.map((control) => (
                  <label className="range-control" key={control.key} title={control.title}>
                    <span>
                      <strong>{control.label}</strong>
                      <em>{filters.sonaraMixer[control.key].toFixed(2)}</em>
                    </span>
                    <input
                      type="range"
                      min={0}
                      max={3}
                      step={0.05}
                      value={filters.sonaraMixer[control.key]}
                      title={control.title}
                      onChange={(event) => setSonaraMixerValue(control.key, Number(event.target.value))}
                    />
                  </label>
                ))}
              </div>
              <div className="custom-control-header">
                <span>Modifiers</span>
              </div>
              <div className="range-grid modifier-grid">
                {modifierControls.map((control) => (
                  <label className="range-control" key={control.key} title={control.title}>
                    <span>
                      <strong>{control.label}</strong>
                      <em>{formatSigned(filters.sonaraModifiers[control.key])}</em>
                    </span>
                    <input
                      type="range"
                      min={-1}
                      max={1}
                      step={0.05}
                      value={filters.sonaraModifiers[control.key]}
                      title={control.title}
                      onChange={(event) => setSonaraModifierValue(control.key, Number(event.target.value))}
                    />
                  </label>
                ))}
              </div>
            </div>
            <div className="filters compact-filters">
              <label title={helpText.similarity}>Similarity<input type="number" value={filters.minSimilarity} min={0} max={1} step={0.01} title={helpText.similarity} onChange={(event) => setFilters({ ...filters, minSimilarity: Number(event.target.value) })} /></label>
              <label title={helpText.lookback}>Lookback<input type="number" value={filters.lookback} min={0} max={12} title={helpText.lookback} onChange={(event) => setFilters({ ...filters, lookback: Number(event.target.value) })} /></label>
              <label title={helpText.limit}>Limit<input type="number" value={filters.limit} min={1} max={500} title={helpText.limit} onChange={(event) => setFilters({ ...filters, limit: Number(event.target.value) })} /></label>
            </div>
            <button className="primary sonara-search-button" title="Найти похожие треки через SONARA по выбранным seed-трекам" disabled={busy || !seeds.length} onClick={handleSonaraSearch}>
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
            <button className="primary mert-search-button" title="Найти похожие треки через MERT по выбранным seed-трекам" disabled={busy || !seeds.length} onClick={handleMertSearch}>
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
                  placeholder="Melancholic minimal house with broken drums, warm chords, no vocals"
                  title={helpText.textPrompt}
                />
              </label>
            </div>
            <div className="filters compact-filters">
              <label title={helpText.similarity}>Similarity<input type="number" value={filters.minSimilarity} min={0} max={1} step={0.01} title={helpText.similarity} onChange={(event) => setFilters({ ...filters, minSimilarity: Number(event.target.value) })} /></label>
              <label title={helpText.limit}>Limit<input type="number" value={filters.limit} min={1} max={500} title={helpText.limit} onChange={(event) => setFilters({ ...filters, limit: Number(event.target.value) })} /></label>
            </div>
            <button className="primary clap-text-search-button" title="Найти треки через CLAP по текстовому описанию звучания" disabled={busy || !textQuery.trim()} onClick={handleTextSearch}>
              <Search size={17} />
              CLAP search
            </button>
          </div>
        )}
        {activeSearchTab === "class" && (
          <div className="search-tab-panel" role="tabpanel">
            <div className="classifier-controls">
              {classifiers.map((classifier) => {
                const title = classifierHelp(classifier);
                const value = classifierMinScores[classifier.classifier_key] || 0;
                return (
                  <Fragment key={classifier.classifier_key}>
                    <div className="custom-control-header" title={title}>
                      <span>{classifier.name}</span>
                    </div>
                    <label className="range-control" title={title}>
                      <span>
                        <em>{value.toFixed(2)}</em>
                      </span>
                      <input
                        type="range"
                        min={0}
                        max={1}
                        step={0.01}
                        value={value}
                        title={title}
                        onChange={(event) => onClassifierMinScoreChange(classifier.classifier_key, Number(event.target.value))}
                      />
                    </label>
                  </Fragment>
                );
              })}
              {classifierJob && classifierJob.failed > 0 ? (
                <span className="classifier-job-status">failed {classifierJob.failed}</span>
              ) : null}
            </div>
            <div className="classifier-action-row">
              <button className="primary classifier-analyze-button" title="Пересчитать promoted classifier scores для текущей базы" disabled={busy || classifiers.length === 0} onClick={handleClassifierAnalyze}>
                <SlidersHorizontal size={17} />
                Analyze Classifiers
              </button>
              <button className="analysis-reset-button classifier-reset-button" disabled={busy || classifiers.length === 0} onClick={handleResetClassifiers} title="Reset Break Energy + Live Instrumentation" aria-label="Reset Break Energy + Live Instrumentation">
                Reset
                <Trash2 size={14} />
              </button>
            </div>
          </div>
        )}
        <div className="results-list">
          {results.map(({ track, score, score_breakdown }) => (
            <ResultRow
              key={track.id}
              track={track}
              score={score}
              scoreBreakdown={score_breakdown}
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
        <span className={`save-state ${playlist.length ? "dirty" : ""}`}>
          {playlist.length ? "Экспорт сохранит текущий сет" : "Сет пуст"}
        </span>
        {playlist.length > playlistPageSize ? (
          <div className="playlist-page-controls">
            <span className="library-page-status">
              {playlistPageState.pageStart}-{playlistPageState.pageEnd} из {playlistPageState.total}
            </span>
            <button className="secondary-mini playlist-page-previous-button" title="Предыдущая страница сета" disabled={!playlistPageState.canGoBack} onClick={() => setPlaylistOffset((current) => Math.max(0, current - playlistPageSize))} type="button">Prev</button>
            <button className="secondary-mini playlist-page-next-button" title="Следующая страница сета" disabled={!playlistPageState.canGoForward} onClick={() => setPlaylistOffset((current) => current + playlistPageSize)} type="button">Next</button>
          </div>
        ) : null}
        <div className="playlist-list">
          {playlist.length === 0 ? (
            <div className="empty-state">
              Сет пуст
            </div>
          ) : (
            playlistPageState.items.map((track, index) => (
              <div className="playlist-row" key={track.id}>
                <span className="row-index">{playlistPageState.offset + index + 1}</span>
                <button className="icon-button playlist-preview-button" title="Preview" aria-label={`Preview ${displayTrack(track)}`} onClick={() => setPreview(track)}><Play size={15} /></button>
                <div className="track-copy">
                  <strong>{displayTrack(track)}</strong>
                  <span>{trackInfo(track)}</span>
                </div>
                <button className="icon-button playlist-metadata-button" title="Теги и жанры" aria-label={`Теги ${displayTrack(track)}`} onClick={() => setMetadataTrack(track)}><Tags size={15} /></button>
                <button className="icon-button intent-remove playlist-remove-button" title="Убрать из сета" aria-label={`Убрать ${displayTrack(track)} из сета`} onClick={() => removeFromPlaylist(track.id)}><Trash2 size={15} /></button>
              </div>
            ))
          )}
        </div>
        <div className="path-row output-row">
          <input value={outputDir} onChange={(event) => onOutputDirChange(event.target.value)} placeholder="D:/Exports" title={helpText.outputDir} />
          <button className="icon-button folder-picker export-folder-picker-button" title="Выбрать папку экспорта" aria-label="Выбрать папку экспорта" disabled={busy} onClick={onChooseOutputFolder} type="button">
            <FolderOpen size={17} />
          </button>
        </div>
        <div className="action-row">
          <button className="export-m3u-button" title="Экспортировать текущий сет в M3U" disabled={busy || !playlist.length} onClick={() => handleExport("m3u")}><Download size={16} />M3U</button>
          <button className="export-csv-button" title="Экспортировать текущий сет в CSV" disabled={busy || !playlist.length} onClick={() => handleExport("csv")}><Download size={16} />CSV</button>
        </div>
      </section>
    </aside>
  );
}

function formatSigned(value: number) {
  if (value === 0) return "0.00";
  return `${value > 0 ? "+" : ""}${value.toFixed(2)}`;
}

function classifierHelp(classifier: PromotedClassifier) {
  const label = classifier.positive_label ? ` Positive label: ${classifier.positive_label}.` : "";
  return `Minimum ${classifier.name}. Type: number 0.00-1.00. Filters tracks by stored promoted classifier score.${label}`;
}
