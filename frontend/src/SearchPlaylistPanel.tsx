import { Dispatch, KeyboardEvent, SetStateAction, useEffect, useState } from "react";
import { Download, FolderOpen, ListMusic, ListPlus, Pause, Play, Search, Shuffle, Tags, Trash2, X } from "lucide-react";
import { AnalysisJobStatus, EmbeddingSource, PromotedClassifier, SearchResult, SonaraMixerWeights, SonaraModifiers, SonaraSearchMode, Track } from "./api";
import { TextSearchTab } from "./TextSearchTab";
import {
  classifierIsAvailable,
  classifierProfileStatus,
  classifierScoringBlockedReason,
  formatClassifierScoredTracks,
  orderPromotedClassifiers,
} from "./classifierCompatibility";
import type { TextPromptAxis, TextPromptPreset } from "./textPromptPresets";
import { EmbeddingSearchTab } from "./EmbeddingSearchTab";
import { playlistPage } from "./playlistView";
import { ReferenceComparePanel } from "./ReferenceComparePanel";
import {
  genericSearchResultIsCurrent,
  isSeedEmbeddingFamily,
  primarySearchTabs,
  seedEmbeddingFamilyPresentation,
  tabAfterKey,
  type GenericSearchTab,
  type PrimarySearchTab,
  type SeedEmbeddingFamily
} from "./searchSurfaceState";
import { ResultRow } from "./TrackRows";
import { displayTrack } from "./trackDisplay";

const playlistPageSize = 20;

export type SearchFiltersState = {
  limit: number;
  sonaraMode: SonaraSearchMode;
  sonaraMixer: SonaraMixerWeights;
  sonaraModifiers: SonaraModifiers;
};

type SearchHelpText = {
  textPrompt: string;
  limit: string;
  sonaraMode: string;
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
  sonaraModifierVocalness: string;
  sonaraModifierAggression: string;
  playlistName: string;
  outputDir: string;
};

type SelectOption<T extends string> = {
  value: T;
  label: string;
  title: string;
};

const sonaraModeOptions: Array<SelectOption<SonaraSearchMode>> = [
  {
    value: "balanced",
    label: "Balanced",
    title: "Balanced: универсальный поиск с балансом настроения, саунда, темпа и гармонии."
  },
  {
    value: "vibe",
    label: "Vibe",
    title: "Vibe: ищет близкие настроение, энергию, танцевальность и динамику."
  },
  {
    value: "sound",
    label: "Sound",
    title: "Sound: ищет похожий характер звука — тембр, текстуру и яркость."
  },
  {
    value: "dj_transition",
    label: "DJ transition",
    title: "DJ transition: ищет следующий трек для сета по темпу, ритму, энергии и тональности. При наличии данных учитывает outro → intro."
  },
  {
    value: "custom",
    label: "Custom mixer",
    title: "Custom mixer: вручную решает, какая похожесть важна и в какую сторону направлять выдачу."
  }
];

const primaryTabPresentation: Record<PrimarySearchTab, { label: string; title: string }> = {
  sonara: { label: "SONARA", title: "SONARA similarity search" },
  similarity: { label: "SIMILARITY", title: "Seed embedding similarity search (MAEST, MERT, MuQ, MuQ-MuLan)" },
  text: { label: "PROMPT", title: "Prompt-to-track search: describe the sound in words (CLAP or MuQ-MuLan)" },
  class: { label: "CLASS", title: "Classifier controls" },
  lab: { label: "LAB", title: "Reference Compare model groups" }
};

function searchResultOriginLabel(origin: GenericSearchTab) {
  return isSeedEmbeddingFamily(origin)
    ? seedEmbeddingFamilyPresentation[origin].label
    : primaryTabPresentation[origin].label;
}

const classifierEmptyStateMessage = "No promoted classifier profiles found. Promote profiles from Rhythm Lab or place model.json + model.joblib under models/classifiers/<profile>/.";

export function SearchPlaylistPanel({
  seedTracks,
  textQuery,
  onTextQueryChange,
  textNegativeQuery,
  onTextNegativeQueryChange,
  textUseNegativePrompt,
  onTextUseNegativePromptChange,
  textEmbeddingFamily,
  onTextEmbeddingFamilyChange,
  seedEmbeddingFamily,
  onSeedEmbeddingFamilyChange,
  selectedPresetKeys,
  onTogglePreset,
  onClearPresets,
  promptAxes,
  promptPresets,
  promptNegativeWeight,
  databaseIdentity,
  busy,
  filters,
  setFilters,
  seeds,
  results,
  genericSearchInputKey,
  genericSearchResultKey,
  genericSearchResultOrigin,
  textFeedback,
  onPrimarySearchTabChange,
  seedSet,
  playlistSet,
  playlist,
  playlistName,
  onPlaylistNameChange,
  outputDir,
  onOutputDirChange,
  onChooseOutputFolder,
  helpText,
  embeddingCounts,
  classifiers,
  classifierMinScores,
  onClassifierMinScoreChange,
  onAnalyzeClassifier,
  onResetClassifier,
  classifierJob,
  removeSeed,
  handleTextSearch,
  handleSonaraSearch,
  handleAddRandomSonaraTrack,
  handleAddRandomEmbeddingTrack,
  handleEmbeddingSearch,
  addSeed,
  toggleLiked,
  togglePlaylist,
  playingTrackId,
  previewTrackId,
  setPreview,
  onSeekPreview,
  setMetadataTrack,
  removeFromPlaylist,
  handleSaveToCollection,
  handleExport
}: {
  seedTracks: Track[];
  textQuery: string;
  onTextQueryChange: (value: string) => void;
  textNegativeQuery: string;
  onTextNegativeQueryChange: (value: string) => void;
  textUseNegativePrompt: boolean;
  onTextUseNegativePromptChange: (value: boolean) => void;
  textEmbeddingFamily: Extract<EmbeddingSource, "clap" | "mulan">;
  onTextEmbeddingFamilyChange: (value: Extract<EmbeddingSource, "clap" | "mulan">) => void;
  seedEmbeddingFamily: SeedEmbeddingFamily;
  onSeedEmbeddingFamilyChange: (value: SeedEmbeddingFamily) => void;
  selectedPresetKeys: string[];
  onTogglePreset: (key: string) => void;
  onClearPresets: () => void;
  promptAxes: TextPromptAxis[];
  promptPresets: TextPromptPreset[];
  promptNegativeWeight: number | null;
  databaseIdentity: string | null;
  busy: boolean;
  filters: SearchFiltersState;
  setFilters: Dispatch<SetStateAction<SearchFiltersState>>;
  seeds: number[];
  results: SearchResult[];
  genericSearchInputKey: string;
  genericSearchResultKey: string;
  genericSearchResultOrigin: GenericSearchTab | null;
  /** Verdict state for text-search rows; null when no preset built the list. */
  textFeedback: {
    verdicts: Record<string, 1 | -1>;
    onVerdict: (track: Track, verdict: 1 | -1) => void;
  } | null;
  onPrimarySearchTabChange: (tab: PrimarySearchTab) => void;
  seedSet: Set<number>;
  playlistSet: Set<number>;
  playlist: Track[];
  playlistName: string;
  onPlaylistNameChange: (value: string) => void;
  outputDir: string;
  onOutputDirChange: (value: string) => void;
  onChooseOutputFolder: () => void;
  helpText: SearchHelpText;
  embeddingCounts: Record<EmbeddingSource, number>;
  classifiers: PromotedClassifier[];
  classifierMinScores: Record<string, number>;
  onClassifierMinScoreChange: (classifier: string, value: number) => void;
  onAnalyzeClassifier: (classifier: PromotedClassifier) => void;
  onResetClassifier: (classifier: PromotedClassifier) => void;
  classifierJob: AnalysisJobStatus | null;
  removeSeed: (trackId: number) => void;
  handleTextSearch: () => void;
  handleSonaraSearch: () => void;
  handleAddRandomSonaraTrack: () => void;
  handleAddRandomEmbeddingTrack: () => void;
  handleEmbeddingSearch: (analysisFamily: EmbeddingSource) => Promise<void>;
  addSeed: (track: Track) => void;
  toggleLiked: (track: Track) => Promise<Track | null>;
  togglePlaylist: (track: Track) => void;
  playingTrackId: number | null;
  previewTrackId: number | null;
  setPreview: (track: Track) => void;
  onSeekPreview: (track: Track, seconds: number) => void;
  setMetadataTrack: (track: Track) => void;
  removeFromPlaylist: (trackId: number) => void;
  handleSaveToCollection: () => void;
  handleExport: (format: "m3u" | "csv") => void;
}) {
  const [activeSearchTab, setActiveSearchTab] = useState<PrimarySearchTab>("sonara");
  const [playlistExportOpen, setPlaylistExportOpen] = useState(false);
  const [playlistOffset, setPlaylistOffset] = useState(0);
  const [embeddingSearchPending, setEmbeddingSearchPending] = useState<Partial<Record<EmbeddingSource, boolean>>>({});
  const [embeddingSearchErrors, setEmbeddingSearchErrors] = useState<Partial<Record<EmbeddingSource, string>>>({});
  const playlistPageState = playlistPage(playlist, playlistOffset, playlistPageSize);
  const showGenericSearchResults = genericSearchResultIsCurrent(
    activeSearchTab,
    genericSearchResultOrigin,
    genericSearchResultKey,
    genericSearchInputKey
  );
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
    { key: "aggression", label: "Aggression", title: helpText.sonaraModifierAggression },
    { key: "vocalness", label: "Vocal", title: helpText.sonaraModifierVocalness },
    { key: "acousticness", label: "Acoustic", title: helpText.sonaraModifierAcousticness },
    { key: "brightness", label: "Bright", title: helpText.sonaraModifierBrightness },
    { key: "rhythm_density", label: "Density", title: helpText.sonaraModifierRhythmDensity },
    { key: "dynamic_range", label: "Range", title: helpText.sonaraModifierDynamicRange },
    { key: "loudness", label: "LUFS", title: helpText.sonaraModifierLoudness }
  ];
  const sonaraModeTitle = optionTitle(sonaraModeOptions, filters.sonaraMode);
  const customSonaraDisabled = filters.sonaraMode !== "custom";
  const orderedClassifierProfiles = orderPromotedClassifiers(classifiers);
  const availableClassifierCount = orderedClassifierProfiles.filter(classifierIsAvailable).length;
  const blockedClassifierCount = orderedClassifierProfiles.length - availableClassifierCount;
  const textModelLabel = textEmbeddingFamily === "mulan" ? "MuQ-MuLan" : "CLAP";
  const hasStoredTextEmbeddings = embeddingCounts[textEmbeddingFamily] > 0;
  const textSearchTitle = hasStoredTextEmbeddings
    ? `Найти треки через ${textModelLabel} по текстовому описанию звучания. Требуются сохраненные ${textModelLabel} audio embeddings в SQLite.`
    : `${textModelLabel} search requires stored audio embeddings. Запустите анализ ${textModelLabel} для библиотеки, затем повторите текстовый поиск.`;

  useEffect(() => {
    setEmbeddingSearchErrors({});
    setEmbeddingSearchPending({});
  }, [databaseIdentity]);

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
      sonaraModifiers: { energy: 0, valence: 0, acousticness: 0, brightness: 0, rhythm_density: 0, dynamic_range: 0, loudness: 0, vocalness: 0, aggression: 0 }
    }));
  }

  function handlePrimaryTabKeyDown(event: KeyboardEvent<HTMLButtonElement>) {
    const target = tabAfterKey(primarySearchTabs, activeSearchTab, event.key);
    if (!target) return;
    event.preventDefault();
    selectPrimarySearchTab(target);
    queueMicrotask(() => document.getElementById(`search-tab-${target}`)?.focus());
  }

  function selectPrimarySearchTab(target: PrimarySearchTab) {
    if (target === activeSearchTab) return;
    setActiveSearchTab(target);
    onPrimarySearchTabChange(target);
  }

  function selectSeedEmbeddingFamily(analysisFamily: SeedEmbeddingFamily) {
    if (analysisFamily === seedEmbeddingFamily) return;
    setEmbeddingSearchErrors((current) => ({ ...current, [analysisFamily]: "" }));
    onSeedEmbeddingFamilyChange(analysisFamily);
  }

  async function runEmbeddingSearch(analysisFamily: EmbeddingSource) {
    setEmbeddingSearchPending((current) => ({ ...current, [analysisFamily]: true }));
    setEmbeddingSearchErrors((current) => ({ ...current, [analysisFamily]: "" }));
    try {
      await handleEmbeddingSearch(analysisFamily);
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      setEmbeddingSearchErrors((current) => ({ ...current, [analysisFamily]: message }));
    } finally {
      setEmbeddingSearchPending((current) => ({ ...current, [analysisFamily]: false }));
    }
  }

  return (
    <aside className="panel search-panel">
      <section className="search-workflow-section">
        <div className="panel-title">
          <Search size={18} />
          <h2>3. Поиск и прослушивание</h2>
        </div>
        <div className="seed-strip">
          {seedTracks.map((track) => (
            <button className="seed-remove-chip" key={track.track_id} title={`Убрать seed: ${displayTrack(track)}`} onClick={() => removeSeed(track.track_id)} type="button">
              {displayTrack(track)}
              <X size={12} />
            </button>
          ))}
        </div>
        <div className="search-tabs" role="tablist" aria-label="Search model">
          {primarySearchTabs.map((tab) => (
            <button
              key={tab}
              id={`search-tab-${tab}`}
              className={`model-search-tab ${activeSearchTab === tab ? "active" : ""}`}
              title={primaryTabPresentation[tab].title}
              onClick={() => selectPrimarySearchTab(tab)}
              onKeyDown={handlePrimaryTabKeyDown}
              role="tab"
              aria-selected={activeSearchTab === tab}
              aria-controls={`search-panel-${tab}`}
              tabIndex={activeSearchTab === tab ? 0 : -1}
              type="button"
            >
              {primaryTabPresentation[tab].label}
            </button>
          ))}
        </div>
        {activeSearchTab === "lab" && (
          <div id="search-panel-lab" className="search-tab-panel" role="tabpanel" aria-labelledby="search-tab-lab">
            <ReferenceComparePanel
              seedTracks={seedTracks}
              busy={busy}
              seedSet={seedSet}
              playlistSet={playlistSet}
              playingTrackId={playingTrackId}
              previewTrackId={previewTrackId}
              onSeed={addSeed}
              onToggleLiked={toggleLiked}
              onTogglePlaylist={togglePlaylist}
              onPreview={setPreview}
              onSeekPreview={onSeekPreview}
              onDetails={setMetadataTrack}
            />
          </div>
        )}
        {activeSearchTab === "sonara" && (
          <div id="search-panel-sonara" className="search-tab-panel" role="tabpanel" aria-labelledby="search-tab-sonara">
            <div className={customSonaraDisabled ? "sonara-custom-controls disabled-filter" : "sonara-custom-controls"}>
              <div className="custom-control-header">
                <div className="custom-control-copy">
                  <span>Mixer</span>
                  <small>— приоритизирует виды сходства.</small>
                </div>
                <button className="sonara-mixer-reset-button" title="Сбросить SONARA mixer и modifiers" type="button" onClick={resetCustomSonara}>Reset</button>
              </div>
              <div className="range-grid mixer-grid">
                {mixerControls.map((control) => {
                  const value = filters.sonaraMixer[control.key];
                  const isOff = value === 0;
                  return (
                    <label className={isOff ? "range-control is-off" : "range-control"} key={control.key} title={control.title}>
                      <span>
                        <strong>{control.label}</strong>
                        <em>{value.toFixed(2)}</em>
                        {isOff ? <small className="sonara-control-off">Off</small> : null}
                      </span>
                      <input
                        type="range"
                        min={0}
                        max={5}
                        step={0.05}
                        value={value}
                        title={control.title}
                        disabled={customSonaraDisabled}
                        onChange={(event) => setSonaraMixerValue(control.key, Number(event.target.value))}
                      />
                    </label>
                  );
                })}
              </div>
              <div className="custom-control-header sonara-modifier-header">
                <div className="custom-control-copy">
                  <span>Modifiers</span>
                  <small>— направляют характер выдачи.</small>
                </div>
              </div>
              <div className="range-grid modifier-grid sonara-modifier-grid">
                {modifierControls.map((control) => {
                  const value = filters.sonaraModifiers[control.key];
                  const isOff = value === 0;
                  const inputId = `sonara-modifier-${control.key}`;
                  return (
                    <div className={isOff ? "range-control is-off" : "range-control"} key={control.key}>
                      <span>
                        <label htmlFor={inputId} title={control.title}><strong>{control.label}</strong></label>
                        <em className="sonara-modifier-score">{formatSigned(value)}</em>
                        <button
                          aria-label={`Reset ${control.label} modifier to zero`}
                          className="sonara-control-off sonara-modifier-reset-button"
                          disabled={isOff || customSonaraDisabled}
                          title={`Reset ${control.label} modifier to zero`}
                          type="button"
                          onClick={() => setSonaraModifierValue(control.key, 0)}
                        >
                          Off
                        </button>
                      </span>
                      <input
                        className="sonara-modifier-range"
                        id={inputId}
                        type="range"
                        min={-1}
                        max={1}
                        step={0.05}
                        value={value}
                        title={control.title}
                        disabled={customSonaraDisabled}
                        onChange={(event) => setSonaraModifierValue(control.key, Number(event.target.value))}
                      />
                    </div>
                  );
                })}
              </div>
            </div>
            <div className="sonara-random-track-action">
              <button className="sonara-random-track-button" title="Добавить случайный SONARA-ready трек из базы в seed" disabled={busy} onClick={handleAddRandomSonaraTrack} type="button">
                <Shuffle size={15} />
                Add Random Track
              </button>
            </div>
            <div className="search-filter-grid sonara-search-filter-grid">
              <label title={helpText.sonaraMode}>
                Mode
                <select
                  className="sonara-mode-select"
                  value={filters.sonaraMode}
                  title={sonaraModeTitle}
                  onChange={(event) => {
                    const selectedMode = sonaraModeOptions.find((option) => option.value === event.target.value);
                    if (selectedMode) setFilters({ ...filters, sonaraMode: selectedMode.value });
                  }}
                >
                  {sonaraModeOptions.map((option) => (
                    <option key={option.value} value={option.value} title={option.title}>{option.label}</option>
                  ))}
                </select>
              </label>
              <label title={helpText.limit}>Limit<input type="number" value={filters.limit} min={1} max={500} title={helpText.limit} onChange={(event) => {
                if (Number.isFinite(event.currentTarget.valueAsNumber)) setFilters({ ...filters, limit: Math.round(clampNumber(event.currentTarget.valueAsNumber, 1, 500)) });
              }} /></label>
            </div>
            <button className="sonara-search-button" title="Найти похожие треки через SONARA по выбранным seed-трекам" disabled={busy || !seeds.length} onClick={handleSonaraSearch} type="button">
              <Search size={17} />
              SONARA search
            </button>
          </div>
        )}
        {activeSearchTab === "similarity" && (
          <div id="search-panel-similarity" className="search-tab-panel" role="tabpanel" aria-labelledby="search-tab-similarity">
            <EmbeddingSearchTab
              analysisFamily={seedEmbeddingFamily}
              onAnalysisFamilyChange={selectSeedEmbeddingFamily}
              currentEmbeddingCount={embeddingCounts[seedEmbeddingFamily]}
              busy={busy || !seeds.length}
              randomTrackBusy={busy}
              pending={Boolean(embeddingSearchPending[seedEmbeddingFamily])}
              error={embeddingSearchErrors[seedEmbeddingFamily] || ""}
              limit={filters.limit}
              limitHelp={helpText.limit}
              onLimitChange={(value) => setFilters({ ...filters, limit: value })}
              onSearch={runEmbeddingSearch}
              onAddRandomTrack={handleAddRandomEmbeddingTrack}
            />
          </div>
        )}
        {activeSearchTab === "text" && (
          <div id="search-panel-text" className="search-tab-panel-wrapper" role="tabpanel" aria-labelledby="search-tab-text">
          <TextSearchTab
            textQuery={textQuery}
            onTextQueryChange={onTextQueryChange}
            textNegativeQuery={textNegativeQuery}
            onTextNegativeQueryChange={onTextNegativeQueryChange}
            textUseNegativePrompt={textUseNegativePrompt}
            onTextUseNegativePromptChange={onTextUseNegativePromptChange}
            textEmbeddingFamily={textEmbeddingFamily}
            onTextEmbeddingFamilyChange={onTextEmbeddingFamilyChange}
            selectedPresetKeys={selectedPresetKeys}
            onTogglePreset={onTogglePreset}
            onClearPresets={onClearPresets}
            promptAxes={promptAxes}
            promptPresets={promptPresets}
            negativeWeight={promptNegativeWeight}
            limit={filters.limit}
            onLimitChange={(value) => setFilters({ ...filters, limit: value })}
            textPromptHelp={helpText.textPrompt}
            limitHelp={helpText.limit}
            hasStoredTextEmbeddings={hasStoredTextEmbeddings}
            busy={busy}
            textSearchTitle={textSearchTitle}
            handleTextSearch={handleTextSearch}
          />
          </div>
        )}
        {activeSearchTab === "class" && (
          <div id="search-panel-class" className="search-tab-panel" role="tabpanel" aria-labelledby="search-tab-class">
            {orderedClassifierProfiles.length ? (
              <div className="classifier-controls">
                <div className="classifier-profile-summary" role="status">
                  available {availableClassifierCount} · blocked {blockedClassifierCount}
                </div>
                {orderedClassifierProfiles.map((classifier) => {
                  const title = classifierHelp(classifier);
                  const value = classifierMinScores[classifier.classifier_key] || 0;
                  const blockedReason = classifierScoringBlockedReason(classifier);
                  if (blockedReason) {
                    const status = classifierProfileStatus(classifier);
                    return (
                      <div
                        className="classifier-profile unavailable"
                        key={classifier.classifier_key}
                        title={blockedReason}
                      >
                        <div className="classifier-profile-status-heading">
                          <span>{classifier.name}</span>
                          <span className="classifier-profile-status-badge">{status}</span>
                        </div>
                        <span className="classifier-profile-status-reason">{blockedReason}</span>
                      </div>
                    );
                  }
                  const scoredTracks = Math.max(
                    0,
                    Math.trunc(Number(classifier.scored_tracks || 0)),
                  );
                  const hasScores = scoredTracks > 0;
                  const rescoreTitle = `Reset and rescore all ${classifier.name} classifier results`;
                  const sliderTitle = hasScores
                    ? title
                    : `${classifier.name} has no current calculated scores. Run classifier scoring first.`;
                  const manifestFacts = classifierManifestFacts(classifier);
                  const primaryManifestFacts = manifestFacts.filter(({ label }) => ["Status", "Type", "Models", "Calibrated"].includes(label));
                  const secondaryManifestFacts = manifestFacts.filter(({ label }) => !["Status", "Type", "Models", "Calibrated"].includes(label));
                  return (
                    <div className="classifier-profile available" key={classifier.classifier_key}>
                      <div className="custom-control-header" title={title}>
                        <div className="custom-classifier-profile-title">
                          <strong>{classifier.name}</strong>
                          <small> - {classifier.profile_description || "No description in model.json."}</small>
                        </div>
                      </div>
                      {manifestFacts.length ? (
                        <div className="classifier-profile-meta">
                          <div className="classifier-profile-facts">
                            <div className="classifier-profile-fact-row classifier-profile-primary-facts">
                              {primaryManifestFacts.map((fact) => (
                                <span
                                  className={fact.label === "Models" ? "classifier-profile-models" : undefined}
                                  key={fact.label}
                                  title={`${fact.label}: ${fact.value}`}
                                >
                                  <b>{fact.label}:</b>
                                  {fact.status ? (
                                    <span className={`classifier-profile-status-badge ${fact.value === "available" ? "available" : ""}`.trim()}>{fact.value}</span>
                                  ) : <i>{fact.value}</i>}
                                </span>
                              ))}
                            </div>
                            <div className="classifier-profile-fact-row classifier-profile-secondary-facts">
                              {secondaryManifestFacts.map((fact) => (
                                <span key={fact.label} title={`${fact.label}: ${fact.value}`}>
                                  <b>{fact.label}:</b><i>{fact.value}</i>
                                </span>
                              ))}
                            </div>
                          </div>
                          <div className="classifier-profile-actions">
                            <button
                              className="icon-button classifier-analyze-button"
                              title={rescoreTitle}
                              aria-label={rescoreTitle}
                              disabled={busy}
                              onClick={() => onAnalyzeClassifier(classifier)}
                              type="button"
                            >
                              <Play size={15} />
                            </button>
                            <button
                              className="icon-button intent-remove classifier-reset-button"
                              title={`Удалить рассчитанные данные ${classifier.name}`}
                              aria-label={`Удалить рассчитанные данные ${classifier.name}`}
                              disabled={busy}
                              onClick={() => onResetClassifier(classifier)}
                              type="button"
                            >
                              <Trash2 size={15} />
                            </button>
                          </div>
                        </div>
                      ) : null}
                      <label className="range-control" title={sliderTitle}>
                        <span>
                          <em>{value.toFixed(2)}</em>
                          <em>{formatClassifierScoredTracks(scoredTracks)}</em>
                        </span>
                        <input
                          type="range"
                          min={0}
                          max={1}
                          step={0.01}
                          value={value}
                          title={sliderTitle}
                          disabled={!hasScores}
                          onChange={(event) => onClassifierMinScoreChange(classifier.classifier_key, Number(event.target.value))}
                        />
                      </label>
                    </div>
                  );
                })}
                {classifierJob && classifierJob.failed > 0 ? (
                  <span className="classifier-job-status">failed {classifierJob.failed}</span>
                ) : null}
              </div>
            ) : (
              <div className="empty-state classifier-empty-state">{classifierEmptyStateMessage}</div>
            )}
          </div>
        )}
        {showGenericSearchResults && genericSearchResultOrigin ? (
          <div className="generic-search-results">
            <div className="generic-search-result-provenance" role="status">
              {searchResultOriginLabel(genericSearchResultOrigin)} results
              <span>{results.length}</span>
            </div>
            <div className="results-list">
              {results.length ? results.map(({ track, score, score_breakdown, reason, sonara_groups, classifier_scores, transition }, index) => (
                <ResultRow
                  key={track.track_id}
                  track={track}
                  rowIndex={index + 1}
                  score={score}
                  scoreBreakdown={score_breakdown}
                  reason={reason}
                  sonaraGroups={sonara_groups}
                  classifierScores={classifier_scores}
                  transition={transition}
                  playingTrackId={playingTrackId}
                  previewTrackId={previewTrackId}
                  isSeed={seedSet.has(track.track_id)}
                  inPlaylist={playlistSet.has(track.track_id)}
                  onSeed={addSeed}
                  onToggleLiked={toggleLiked}
                  onTogglePlaylist={togglePlaylist}
                  onPreview={setPreview}
                  onSeekPreview={onSeekPreview}
                  onDetails={setMetadataTrack}
                  feedbackVerdict={textFeedback ? textFeedback.verdicts[track.track_uuid] ?? null : null}
                  onFeedback={textFeedback ? textFeedback.onVerdict : undefined}
                />
              )) : (
                <div className="empty-state">
                  No current {searchResultOriginLabel(genericSearchResultOrigin)} results matched this request.
                </div>
              )}
            </div>
          </div>
        ) : null}
      </section>
      <details
        className="playlist-export-disclosure"
        onToggle={(event) => {
          setPlaylistExportOpen(event.currentTarget.open);
        }}
      >
        <summary className="playlist-export-summary" title="Развернуть или свернуть текущий сет и экспорт">
          <span className="playlist-export-summary-title">
            <ListMusic size={18} />
            <strong>Сет и экспорт</strong>
            <span className="panel-counter">{playlist.length}</span>
          </span>
          <span className="playlist-export-summary-toggle" aria-hidden="true" />
        </summary>
        {playlistExportOpen ? (
          <section className="playlist-export-section" aria-label="Сет и экспорт">
            <input value={playlistName} onChange={(event) => onPlaylistNameChange(event.target.value)} title={helpText.playlistName} />
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
              <input value={outputDir} onChange={(event) => onOutputDirChange(event.target.value)} placeholder="D:/Exports" title={helpText.outputDir} />
              <button className="icon-button folder-picker export-folder-picker-button" title="Выбрать папку экспорта" aria-label="Выбрать папку экспорта" disabled={busy} onClick={onChooseOutputFolder} type="button">
                <FolderOpen size={17} />
              </button>
            </div>
            <div className="export-action-row">
              <button className="save-collection-button" title="Сохранить текущий сет в Rhythm Lab Collection" disabled={busy || !playlist.length} onClick={handleSaveToCollection}><ListPlus size={16} />Collection</button>
              <button className="export-m3u-button" title="Экспортировать текущий сет в M3U" disabled={busy || !playlist.length} onClick={() => handleExport("m3u")}><Download size={16} />M3U</button>
              <button className="export-csv-button" title="Экспортировать текущий сет в CSV" disabled={busy || !playlist.length} onClick={() => handleExport("csv")}><Download size={16} />CSV</button>
            </div>
          </section>
        ) : null}
      </details>
    </aside>
  );
}

function formatSigned(value: number) {
  if (value === 0) return "0.00";
  return `${value > 0 ? "+" : ""}${value.toFixed(2)}`;
}

function classifierHelp(classifier: PromotedClassifier) {
  const label = classifier.positive_label ? ` Positive label: ${classifier.positive_label}.` : "";
  const description = classifier.profile_description ? `${classifier.profile_description} ` : "";
  return `${description}Minimum ${classifier.name}. Type: number 0.00-1.00. Filters tracks by stored promoted classifier score.${label}`;
}

function classifierManifestFacts(classifier: PromotedClassifier): Array<{ label: string; value: string; status?: boolean }> {
  const facts: Array<{ label: string; value: string; status?: boolean }> = [
    { label: "Status", value: classifierProfileStatus(classifier), status: true },
  ];
  if (classifier.profile_type) {
    facts.push({
      label: "Type",
      value: classifier.profile_type.replaceAll("_", " ").replace(/\b\w/g, (character) => character.toUpperCase()),
    });
  }
  if (classifier.feature_set) {
    facts.push({
      label: "Models",
      value: classifier.feature_set.split("+").map((source) => source.toUpperCase()).join(" + "),
    });
  }
  if (typeof classifier.feature_count === "number") {
    facts.push({ label: "Features", value: classifier.feature_count.toLocaleString("en-US") });
  }
  const trainedLabels = Object.values(classifier.trained_label_counts || {}).reduce((sum, count) => sum + count, 0);
  if (trainedLabels) {
    facts.push({ label: "Labels", value: trainedLabels.toLocaleString("en-US") });
  }
  if (classifier.calibration_status) {
    facts.push({ label: "Calibrated", value: String(classifier.calibration_status === "calibrated") });
  }
  const validationF1 = classifier.calibration?.validation_f1;
  if (typeof validationF1 === "number") {
    facts.push({ label: "Validation", value: `F1 ${(validationF1 * 100).toFixed(1)}%` });
  }
  const promotedAt = classifier.promoted_at ? new Date(classifier.promoted_at) : null;
  if (promotedAt && Number.isFinite(promotedAt.getTime())) {
    facts.push({ label: "Promoted", value: formatPromotedDate(promotedAt) });
  }
  return facts;
}

function formatPromotedDate(value: Date): string {
  const day = String(value.getDate()).padStart(2, "0");
  const month = String(value.getMonth() + 1).padStart(2, "0");
  return `${day}.${month}.${value.getFullYear()}`;
}

function optionTitle<T extends string>(options: Array<SelectOption<T>>, value: T) {
  return options.find((option) => option.value === value)?.title || "";
}

function clampNumber(value: number, min: number, max: number) {
  if (!Number.isFinite(value)) return min;
  return Math.max(min, Math.min(max, value));
}
