import { TextExecutionDetails } from "./TextExecutionDetails";
import type { TextSearchExecution } from "./api";
import { Dispatch, KeyboardEvent, SetStateAction, useEffect, useState } from "react";
import { ChevronsLeft, ChevronsRight, Pause, Play, Plus, Search, Trash2, X } from "lucide-react";
import { AnalysisJobStatus, EmbeddingSource, PromotedClassifier, SearchResult, SonaraMixerWeights, SonaraModifiers, Track } from "./api";
import { TextSearchTab } from "./TextSearchTab";
import {
  classifierIsAvailable,
  classifierProfileStatus,
  classifierScoringBlockedReason,
  formatClassifierScoredTracks,
  orderPromotedClassifiers,
} from "./classifierCompatibility";
import type { TextPromptAxis, TextPromptPreset } from "./textPromptPresets";
import { SimilaritySearchTab } from "./SimilaritySearchTab";
import { MAX_SEED_TRACKS } from "./useSearchPlaylist";
import type { EmbeddingLayerState } from "./useEmbeddingLayers";
import { appendVisibleTracksToPlaylist } from "./libraryView";
import { ReferenceComparePanel } from "./ReferenceComparePanel";
import {
  genericSearchResultIsCurrent,
  primarySearchTabs,
  seedSearchModelPresentation,
  tabAfterKey,
  type GenericSearchTab,
  type PrimarySearchTab,
  type SeedSearchModel
} from "./searchSurfaceState";
import { ResultRow } from "./TrackRows";
import { displayTrack } from "./trackDisplay";
import type { useActivityLog } from "./useActivityLog";
import { errorText } from "./errors";

export type SearchFiltersState = {
  limit: number;
  sonaraMixer: SonaraMixerWeights;
  sonaraModifiers: SonaraModifiers;
};

export type SearchHelpText = {
  textPrompt: string;
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
  sonaraModifierVocalness: string;
  sonaraModifierAggression: string;
};

const primaryTabPresentation: Record<PrimarySearchTab, { label: string; title: string }> = {
  similarity: { label: "SIMILARITY", title: "Seed similarity search (SONARA, MAEST, MERT-v2, MuQ, MuQ-MuLan)" },
  text: { label: "PROMPT", title: "Prompt-to-track search: describe the sound in words (CLAP or MuQ-MuLan)" },
  class: { label: "CLASSIFIER", title: "Classifier controls" },
  lab: { label: "LAB", title: "Reference Compare model groups" }
};

function searchResultOriginLabel(origin: GenericSearchTab) {
  return origin === "text"
    ? primaryTabPresentation.text.label
    : seedSearchModelPresentation[origin].label;
}

const classifierEmptyStateMessage = "No promoted classifier profiles found. Promote profiles from Rhythm Lab or place model.json + model.joblib under models/classifiers/<profile>/.";

function PromptCandidatesAddButton({ results, playlist, busy, modelLabel, onAdd }: {
  results: SearchResult[];
  playlist: Track[];
  busy: boolean;
  modelLabel: string;
  onAdd: (tracks: Track[], modelLabel: string) => void;
}) {
  const tracks = results.map(({ track }) => track);
  const additions = appendVisibleTracksToPlaylist(playlist, tracks).length - playlist.length;
  const title = busy
    ? "Дождитесь завершения текущей операции"
    : !tracks.length
      ? "Нет кандидатов для добавления в сет"
      : !additions
        ? "Все показанные кандидаты уже в сете"
        : `Добавить кандидатов ${modelLabel} в сет: ${additions} новых из ${tracks.length} показанных`;
  return (
    <button
      className="icon-button intent-add add-prompt-candidates-button"
      title={title}
      aria-label={`Добавить кандидатов ${modelLabel} в сет`}
      disabled={busy || additions === 0}
      onClick={() => onAdd(tracks, modelLabel)}
      type="button"
    >
      <Plus size={16} />
    </button>
  );
}

export function SearchPlaylistPanel({
  embeddingLayers,
  activeSearchTab,
  collapsed,
  onToggleCollapsed,
  seedTracks,
  onActivity,
  textQuery,
  textNegativeQuery,
  textUseNegativePrompt,
  onTextUseNegativePromptChange,
  textEmbeddingFamily,
  onTextEmbeddingFamilyChange,
  textCompareModels,
  textModelLoadingLabel,
  onTextCompareModelsChange,
  seedSearchModel,
  onSeedSearchModelChange,
  selectedPresetKeys,
  onTogglePreset,
  onClearPresets,
  promptAxes,
  promptPresets,
  promptNegativeWeight,
  textExecution,
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
  textComparison,
  onPrimarySearchTabChange,
  seedSet,
  playlistSet,
  playlist,
  helpText,
  sonaraCount,
  embeddingCounts,
  classifiers,
  classifierMinScores,
  onClassifierMinScoreChange,
  onAnalyzeClassifier,
  onResetClassifier,
  classifierJob,
  removeSeed,
  clearSeeds,
  handleTextSearch,
  handleSonaraSearch,
  handleAddRandomSonaraTrack,
  handleAddRandomEmbeddingTrack,
  handleEmbeddingSearch,
  addSeed,
  toggleLiked,
  togglePlaylist,
  onAddPromptCandidates,
  playingTrackId,
  setPreview,
  setMetadataTrack
}: {
  embeddingLayers: EmbeddingLayerState;
  activeSearchTab: PrimarySearchTab;
  collapsed: boolean;
  onToggleCollapsed: () => void;
  seedTracks: Track[];
  onActivity: ReturnType<typeof useActivityLog>["appendActivity"];
  textQuery: string;
  textNegativeQuery: string;
  textUseNegativePrompt: boolean;
  onTextUseNegativePromptChange: (value: boolean) => void;
  textEmbeddingFamily: Extract<EmbeddingSource, "clap" | "mulan">;
  onTextEmbeddingFamilyChange: (value: Extract<EmbeddingSource, "clap" | "mulan">) => void;
  textCompareModels: boolean;
  textModelLoadingLabel: string | null;
  onTextCompareModelsChange: (value: boolean) => void;
  seedSearchModel: SeedSearchModel;
  onSeedSearchModelChange: (value: SeedSearchModel) => void;
  selectedPresetKeys: string[];
  onTogglePreset: (key: string) => void;
  onClearPresets: () => void;
  promptAxes: TextPromptAxis[];
  promptPresets: TextPromptPreset[];
  promptNegativeWeight: number | null;
  textExecution: TextSearchExecution | null;
  databaseIdentity: string | null;
  busy: boolean;
  filters: SearchFiltersState;
  setFilters: Dispatch<SetStateAction<SearchFiltersState>>;
  seeds: number[];
  results: SearchResult[];
  genericSearchInputKey: string;
  genericSearchResultKey: string;
  genericSearchResultOrigin: GenericSearchTab | null;
  /**
   * Two ranked lists over one bank, one per model, shown side by side. Present
   * only in A/B; the ordinary search keeps its single list.
   */
  textComparison: {
    family: "clap" | "mulan";
    label: string;
    status: "pending" | "success" | "error";
    error?: string;
    execution?: TextSearchExecution;
    results: SearchResult[];
    verdicts: Record<string, 1 | -1>;
    pending: Record<string, boolean>;
    onVerdict?: (track: Track, verdict: 1 | -1) => void;
  }[] | null;
  /** Verdict state for text-search rows; null when no preset built the list. */
  textFeedback: {
    verdicts: Record<string, 1 | -1>;
    pending: Record<string, boolean>;
    onVerdict: (track: Track, verdict: 1 | -1) => void;
  } | null;
  onPrimarySearchTabChange: (tab: PrimarySearchTab) => void;
  seedSet: Set<number>;
  playlistSet: Set<number>;
  playlist: Track[];
  helpText: SearchHelpText;
  sonaraCount: number;
  embeddingCounts: Record<EmbeddingSource, number>;
  classifiers: PromotedClassifier[];
  classifierMinScores: Record<string, number>;
  onClassifierMinScoreChange: (classifier: string, value: number) => void;
  onAnalyzeClassifier: (classifier: PromotedClassifier) => void;
  onResetClassifier: (classifier: PromotedClassifier) => void;
  classifierJob: AnalysisJobStatus | null;
  removeSeed: (trackId: number) => void;
  clearSeeds: () => void;
  handleTextSearch: () => void;
  handleSonaraSearch: () => void;
  handleAddRandomSonaraTrack: () => void;
  handleAddRandomEmbeddingTrack: () => void;
  handleEmbeddingSearch: (analysisFamily: EmbeddingSource) => Promise<void>;
  addSeed: (track: Track) => void;
  toggleLiked: (track: Track) => Promise<Track | null>;
  togglePlaylist: (track: Track) => void;
  onAddPromptCandidates: (tracks: Track[], modelLabel: string) => void;
  playingTrackId: number | null;
  setPreview: (track: Track) => void;
  setMetadataTrack: (track: Track) => void;
}) {
  const [embeddingSearchPending, setEmbeddingSearchPending] = useState<Partial<Record<EmbeddingSource, boolean>>>({});
  const [embeddingSearchErrors, setEmbeddingSearchErrors] = useState<Partial<Record<EmbeddingSource, string>>>({});
  const showGenericSearchResults = genericSearchResultIsCurrent(
    activeSearchTab,
    genericSearchResultOrigin,
    genericSearchResultKey,
    genericSearchInputKey
  );
  const orderedClassifierProfiles = orderPromotedClassifiers(classifiers);
  const availableClassifierCount = orderedClassifierProfiles.filter(classifierIsAvailable).length;
  const blockedClassifierCount = orderedClassifierProfiles.length - availableClassifierCount;
  const textModelLabel = textEmbeddingFamily === "mulan" ? "MuQ-MuLan" : "CLAP";
  const hasStoredTextEmbeddings = textCompareModels
    ? embeddingCounts.clap > 0 || embeddingCounts.mulan > 0
    : embeddingCounts[textEmbeddingFamily] > 0;
  const textSearchTitle = hasStoredTextEmbeddings
    ? `Найти треки через ${textModelLabel} по текстовому описанию звучания. Требуются сохраненные ${textModelLabel} audio embeddings в SQLite.`
    : `${textModelLabel} search requires stored audio embeddings. Запустите анализ ${textModelLabel} для библиотеки, затем повторите текстовый поиск.`;

  useEffect(() => {
    setEmbeddingSearchErrors({});
    setEmbeddingSearchPending({});
  }, [databaseIdentity, embeddingLayers.layer]);

  function handlePrimaryTabKeyDown(event: KeyboardEvent<HTMLButtonElement>) {
    const target = tabAfterKey(primarySearchTabs, activeSearchTab, event.key);
    if (!target) return;
    event.preventDefault();
    selectPrimarySearchTab(target);
    queueMicrotask(() => document.getElementById(`search-tab-${target === "class" ? "classifier" : target}`)?.focus());
  }

  function selectPrimarySearchTab(target: PrimarySearchTab) {
    if (target === activeSearchTab) return;
    onPrimarySearchTabChange(target);
  }

  function selectSeedSearchModel(model: SeedSearchModel) {
    if (model === seedSearchModel) return;
    setEmbeddingSearchErrors({});
    onSeedSearchModelChange(model);
  }

  async function runEmbeddingSearch(analysisFamily: EmbeddingSource) {
    setEmbeddingSearchPending((current) => ({ ...current, [analysisFamily]: true }));
    setEmbeddingSearchErrors((current) => ({ ...current, [analysisFamily]: "" }));
    try {
      await handleEmbeddingSearch(analysisFamily);
    } catch (error) {
      const message = errorText(error);
      setEmbeddingSearchErrors((current) => ({ ...current, [analysisFamily]: message }));
    } finally {
      setEmbeddingSearchPending((current) => ({ ...current, [analysisFamily]: false }));
    }
  }

  return (
    <aside className={`panel search-panel ${collapsed ? "collapsed" : ""}`}>
      {collapsed ? (
        <button
          className="panel-rail"
          title="Развернуть «Поиск и прослушивание»"
          aria-label="Развернуть «Поиск и прослушивание»"
          aria-expanded={false}
          onClick={onToggleCollapsed}
          type="button"
        >
          <ChevronsRight size={17} />
          <span className="panel-rail-label">3. Поиск и прослушивание</span>
        </button>
      ) : null}
      <section className="search-workflow-section" hidden={collapsed}>
        <div className="panel-title">
          <Search size={18} />
          <h2>3. Поиск и прослушивание</h2>
          <button
            className="icon-button panel-collapse-button"
            title="Свернуть «Поиск и прослушивание»"
            aria-label="Свернуть «Поиск и прослушивание»"
            aria-expanded
            onClick={onToggleCollapsed}
            type="button"
          >
            <ChevronsLeft size={17} />
          </button>
        </div>
        <div className="search-tabs" role="tablist" aria-label="Search model">
          {primarySearchTabs.map((tab) => (
            <button
              key={tab}
              id={`search-tab-${tab === "class" ? "classifier" : tab}`}
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
        {seedTracks.length ? <div className="seed-controls">
          <span>Seeds · {seedTracks.length}/{MAX_SEED_TRACKS}</span>
        </div> : null}
        <div className="seed-strip">
          {seedTracks.map((track) => {
            const seedPreviewActive = playingTrackId === track.track_id;
            return (
              <div className="seed-chip" key={track.track_id}>
                <button className="icon-button seed-chip-play-button" title={seedPreviewActive ? "Pause preview" : "Preview"} aria-label={`${seedPreviewActive ? "Pause" : "Preview"} ${displayTrack(track)}`} onClick={() => setPreview(track)} type="button">
                  {seedPreviewActive ? <Pause size={11} /> : <Play size={11} />}
                </button>
                <span className="seed-chip-label" title={displayTrack(track)}>{displayTrack(track)}</span>
                <button className="icon-button seed-chip-remove-button" title={`Убрать seed: ${displayTrack(track)}`} aria-label={`Убрать seed: ${displayTrack(track)}`} onClick={() => removeSeed(track.track_id)} type="button">
                  <X size={11} />
                </button>
              </div>
            );
          })}
          {seedTracks.length ? <button className="icon-button seed-clear-button" type="button" onClick={clearSeeds} title="Убрать все seed-треки; сет останется без изменений" aria-label="Убрать все seed-треки"><Trash2 size={13} /></button> : null}
        </div>
        {activeSearchTab === "lab" && (
          <div id="search-panel-lab" className="search-tab-panel" role="tabpanel" aria-labelledby="search-tab-lab">
            <ReferenceComparePanel
              seedTracks={seedTracks}
              onActivity={onActivity}
              busy={busy}
              seedSet={seedSet}
              playlistSet={playlistSet}
              playingTrackId={playingTrackId}
              onSeed={addSeed}
              onToggleLiked={toggleLiked}
              onTogglePlaylist={togglePlaylist}
              onPreview={setPreview}
              onDetails={setMetadataTrack}
            />
          </div>
        )}
        {activeSearchTab === "similarity" && (
          <div id="search-panel-similarity" className="search-tab-panel" role="tabpanel" aria-labelledby="search-tab-similarity">
            <SimilaritySearchTab
              layerState={embeddingLayers}
              model={seedSearchModel}
              onModelChange={selectSeedSearchModel}
              currentAnalysisCount={seedSearchModel === "sonara" ? sonaraCount : embeddingLayers.layered ? embeddingLayers.trackCount : embeddingCounts[seedSearchModel]}
              busy={busy || !seeds.length}
              randomTrackBusy={busy || seedTracks.length >= MAX_SEED_TRACKS}
              pending={seedSearchModel !== "sonara" && Boolean(embeddingSearchPending[seedSearchModel])}
              error={seedSearchModel === "sonara" ? "" : embeddingSearchErrors[seedSearchModel] || ""}
              filters={filters}
              setFilters={setFilters}
              helpText={helpText}
              onSearch={seedSearchModel === "sonara" ? handleSonaraSearch : () => void runEmbeddingSearch(seedSearchModel)}
              onAddRandomTrack={seedSearchModel === "sonara" ? handleAddRandomSonaraTrack : handleAddRandomEmbeddingTrack}
            />
          </div>
        )}
        {activeSearchTab === "text" && (
          <div id="search-panel-text" className="search-tab-panel-wrapper" role="tabpanel" aria-labelledby="search-tab-text">
          <TextSearchTab
            textQuery={textQuery}
            textNegativeQuery={textNegativeQuery}
            textUseNegativePrompt={textUseNegativePrompt}
            onTextUseNegativePromptChange={onTextUseNegativePromptChange}
            textEmbeddingFamily={textEmbeddingFamily}
            onTextEmbeddingFamilyChange={onTextEmbeddingFamilyChange}
            textCompareModels={textCompareModels}
            textModelLoadingLabel={textModelLoadingLabel}
            onTextCompareModelsChange={onTextCompareModelsChange}
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
          <div id="search-panel-class" className="search-tab-panel" role="tabpanel" aria-labelledby="search-tab-classifier">
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
                          name={`classifier-min-score-${classifier.classifier_key}`}
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
        {showGenericSearchResults && genericSearchResultOrigin && textComparison ? (
          /* One bank, two models, two orders. Nothing is merged: rank fusion
             was measured and rejected, so the lists stay apart and the ear
             decides which one was right. */
          <div className="generic-search-results generic-search-compare">
            <div className="compare-columns">
              {textComparison.map((column) => (
                <div className="compare-column" key={column.family}>
                  <div className="generic-search-result-provenance" role="status">
                    {column.label} results
                    <span>{column.results.length}</span>
                    {genericSearchResultOrigin === "text" ? (
                      <PromptCandidatesAddButton
                        results={column.results}
                        playlist={playlist}
                        busy={busy || column.status !== "success"}
                        modelLabel={column.label}
                        onAdd={onAddPromptCandidates}
                      />
                    ) : null}
                  </div>
                  {column.execution ? <TextExecutionDetails execution={column.execution} /> : null}
                  {column.status === "pending" ? <div role="status">{column.label}: поиск…</div> : null}
                  {column.status === "error" ? <div role="alert">{column.error}</div> : null}
                  <div className="results-list">
                    {column.results.length ? column.results.map(({ track, score, score_breakdown, reason, sonara_groups, classifier_scores, transition }, index) => (
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
                        isSeed={seedSet.has(track.track_id)}
                        inPlaylist={playlistSet.has(track.track_id)}
                        onSeed={addSeed}
                        onToggleLiked={toggleLiked}
                        onTogglePlaylist={togglePlaylist}
                        onPreview={setPreview}
                        onDetails={setMetadataTrack}
                        feedbackVerdict={column.verdicts[track.track_uuid] ?? null}
                        onFeedback={column.pending[track.track_uuid] ? undefined : column.onVerdict}
                      />
                    )) : (
                      <div className="empty-state">
                        {column.status === "success" ? `${column.label}: пустая выдача.` : ""}
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        ) : showGenericSearchResults && genericSearchResultOrigin ? (
          <div className="generic-search-results">
            {genericSearchResultOrigin === "text" && textExecution ? <TextExecutionDetails execution={textExecution} /> : null}
            <div className="generic-search-result-provenance" role="status">
              {searchResultOriginLabel(genericSearchResultOrigin)}{genericSearchResultOrigin === seedSearchModel && embeddingLayers.layer !== null ? ` L${embeddingLayers.layer}` : ""} results
              <span>{results.length}</span>
              {genericSearchResultOrigin === "text" ? (
                <PromptCandidatesAddButton
                  results={results}
                  playlist={playlist}
                  busy={busy}
                  modelLabel={textEmbeddingFamily === "clap" ? "CLAP" : "MuQ-MuLan"}
                  onAdd={onAddPromptCandidates}
                />
              ) : null}
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
                  isSeed={seedSet.has(track.track_id)}
                  inPlaylist={playlistSet.has(track.track_id)}
                  onSeed={addSeed}
                  onToggleLiked={toggleLiked}
                  onTogglePlaylist={togglePlaylist}
                  onPreview={setPreview}
                  onDetails={setMetadataTrack}
                  feedbackVerdict={textFeedback ? textFeedback.verdicts[track.track_uuid] ?? null : null}
                  onFeedback={textFeedback && !textFeedback.pending[track.track_uuid] ? textFeedback.onVerdict : undefined}
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
    </aside>
  );
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
