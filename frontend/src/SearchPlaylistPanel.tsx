import { Dispatch, Fragment, SetStateAction, useEffect, useRef, useState } from "react";
import { Download, FolderOpen, ListFilter, ListMusic, Pause, Play, RotateCcw, Search, Tags, Trash2, X } from "lucide-react";
import { AnalysisJobStatus, api, HybridSearchResult, HybridSearchSource, PromotedClassifier, SearchResult, SetBuilderBpmChange, SetBuilderBpmMode, SetBuilderClassifierFlow, SetBuilderEnergyCurve, SetBuilderGeneratePayload, SetBuilderMode, SetBuilderSeedMode, SonaraMixerWeights, SonaraModifiers, Track } from "./api";
import type { ClapPromptPreset } from "./clapPrompt";
import { playlistPage } from "./playlistView";
import { resetSetBuilderSliders, setBuilderDefaultDiversity, setBuilderDefaultFlow } from "./setBuilderControls";
import { ResultRow } from "./TrackRows";
import { displayTrack } from "./trackDisplay";

const playlistPageSize = 200;

export type SearchFiltersState = {
  minSimilarity: number;
  limit: number;
  sonaraMixer: SonaraMixerWeights;
  sonaraModifiers: SonaraModifiers;
};

type SearchHelpText = {
  textPrompt: string;
  similarity: string;
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

type SelectOption<T extends string> = {
  value: T;
  label: string;
  title: string;
};

const setSeedModeOptions: Array<SelectOption<SetBuilderSeedMode>> = [
  {
    value: "manual",
    label: "Manual - selected",
    title: "Manual: использует выбранные seed-треки как фиксированные опорные точки. Нужно выбрать 1-5 треков."
  },
  {
    value: "auto",
    label: "Auto - random start",
    title: "Auto: первый anchor выбирается из всей feature-complete library, затем SET строит связанные waypoint anchors и bridge tracks."
  }
];

const setBuilderModeOptions: Array<SelectOption<SetBuilderMode>> = [
  {
    value: "similar_crate",
    label: "Similar crate - close",
    title: "Similar crate: максимально близкая коробка. Сильнее держится за MERT/CLAP/MAEST embedding + SONARA similarity, меньше рискует с разнообразием."
  },
  {
    value: "weird_adjacent",
    label: "Weird adjacent - odd",
    title: "Weird adjacent: соседние, но менее очевидные треки. Разрешает сдвиг фактуры/настроения, пока связь с anchors остается."
  },
  {
    value: "balanced_set",
    label: "Balanced set - flow",
    title: "Balanced set: компромисс для DJ-сета. Балансирует similarity, diversity, BPM/key переходы, energy curve и artist limits."
  },
  {
    value: "discovery",
    label: "Discovery - wide",
    title: "Discovery: более широкий поиск. Больше novelty/diversity, но кандидаты все еще связаны с anchors и правилами переходов."
  }
];

const setEnergyCurveOptions: Array<SelectOption<SetBuilderEnergyCurve>> = [
  {
    value: "balanced",
    label: "Balanced - steady",
    title: "Balanced: держит энергию вокруг среднего уровня anchors без сильной драматургии."
  },
  {
    value: "warmup",
    label: "Warmup - build",
    title: "Warmup: начинает спокойнее и постепенно поднимает energy/transition pressure."
  },
  {
    value: "peak",
    label: "Peak - intense",
    title: "Peak: предпочитает более высокую energy и плотность, подходит для основной или пиковой части."
  },
  {
    value: "wave",
    label: "Wave - rise/fall",
    title: "Wave: делает волну подъема и сброса энергии внутри последовательности."
  }
];

const setBpmModeOptions: Array<SelectOption<SetBuilderBpmMode>> = [
  {
    value: "general",
    label: "General BPM - transition",
    title: "General BPM: не задает отдельную BPM-драматургию. Темп используется только как обычная soft transition compatibility вместе с key."
  },
  {
    value: "low_to_high",
    label: "Low to high - climb",
    title: "Low to high: строит сет от более низкого BPM к более высокому. Start/Target BPM можно оставить пустыми для авто-вывода."
  },
  {
    value: "high_to_low",
    label: "High to low - descend",
    title: "High to low: строит сет от более высокого BPM к более низкому. Start/Target BPM можно оставить пустыми для авто-вывода."
  }
];

const setBpmChangeOptions: Array<SelectOption<SetBuilderBpmChange>> = [
  {
    value: "slow",
    label: "Slow - late change",
    title: "Slow: BPM меняется осторожно в начале и сильнее ближе к концу."
  },
  {
    value: "medium",
    label: "Medium - linear",
    title: "Medium: BPM меняется примерно равномерно по всей последовательности."
  },
  {
    value: "fast",
    label: "Fast - early change",
    title: "Fast: BPM быстрее сдвигается к целевому диапазону в первой части сета."
  }
];

const setClassifierFlowOptions: Array<SelectOption<SetBuilderClassifierFlow>> = [
  {
    value: "flat",
    label: "Flat",
    title: "Flat: применяет Preference ровно по всему SET без отдельного роста или спада."
  },
  {
    value: "rise",
    label: "Rise",
    title: "Rise: постепенно усиливает выбранную Preference-сторону к концу SET."
  },
  {
    value: "fall",
    label: "Fall",
    title: "Fall: сильнее держит выбранную Preference-сторону в начале SET и ослабляет ее к концу."
  }
];

const hybridSourceKeys: HybridSearchSource[] = ["mert", "maest", "sonara"];

const hybridSourceOptions: Array<{ key: HybridSearchSource; label: string; title: string }> = [
  {
    key: "mert",
    label: "MERT",
    title: "MERT source for Hybrid preview. Type: checkbox on/off. Range: enabled or disabled. Requires stored MERT embeddings."
  },
  {
    key: "maest",
    label: "MAEST",
    title: "MAEST source for Hybrid preview. Type: checkbox on/off. Range: enabled or disabled. Uses stored MAEST embeddings, not genre labels."
  },
  {
    key: "sonara",
    label: "SONARA",
    title: "SONARA source for Hybrid preview. Type: checkbox on/off. Range: enabled or disabled. Requires stored SONARA features."
  }
];

export function SearchPlaylistPanel({
  seedTracks,
  textQuery,
  onTextQueryChange,
  clapAvoidQuery,
  onClapAvoidQueryChange,
  clapPresetKey,
  onClapPresetChange,
  clapPromptPresets,
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
  onAnalyzeClassifier,
  classifierJob,
  removeSeed,
  handleTextSearch,
  handleSonaraSearch,
  handleMertSearch,
  handleSetBuilderGenerate,
  addGeneratedSetToPlaylist,
  addSeed,
  togglePlaylist,
  playingTrackId,
  setPreview,
  setMetadataTrack,
  removeFromPlaylist,
  handleExport
}: {
  seedTracks: Track[];
  textQuery: string;
  onTextQueryChange: (value: string) => void;
  clapAvoidQuery: string;
  onClapAvoidQueryChange: (value: string) => void;
  clapPresetKey: string;
  onClapPresetChange: (value: string) => void;
  clapPromptPresets: ClapPromptPreset[];
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
  onAnalyzeClassifier: (classifier: PromotedClassifier) => void;
  classifierJob: AnalysisJobStatus | null;
  removeSeed: (trackId: number) => void;
  handleTextSearch: () => void;
  handleSonaraSearch: () => void;
  handleMertSearch: () => void;
  handleSetBuilderGenerate: (payload: SetBuilderGeneratePayload) => void;
  addGeneratedSetToPlaylist: () => void;
  addSeed: (track: Track) => void;
  togglePlaylist: (track: Track) => void;
  playingTrackId: number | null;
  setPreview: (track: Track) => void;
  setMetadataTrack: (track: Track) => void;
  removeFromPlaylist: (trackId: number) => void;
  handleExport: (format: "m3u" | "csv") => void;
}) {
  const [activeSearchTab, setActiveSearchTab] = useState<"set" | "sonara" | "mert" | "clap" | "class">("sonara");
  const [setAdvancedControlsOpen, setSetAdvancedControlsOpen] = useState(false);
  const [clapPresetMenuOpen, setClapPresetMenuOpen] = useState(false);
  const clapPresetMenuRef = useRef<HTMLDivElement>(null);
  const [playlistOffset, setPlaylistOffset] = useState(0);
  const [setSeedMode, setSetSeedMode] = useState<SetBuilderSeedMode>("manual");
  const [setBuilderMode, setSetBuilderMode] = useState<SetBuilderMode>("balanced_set");
  const [setBuilderLimit, setSetBuilderLimit] = useState(24);
  const [setBuilderDiversity, setSetBuilderDiversity] = useState(setBuilderDefaultDiversity);
  const [setEnergyCurve, setSetEnergyCurve] = useState<SetBuilderEnergyCurve>("balanced");
  const [setBpmMode, setSetBpmMode] = useState<SetBuilderBpmMode>("general");
  const [setBpmChange, setSetBpmChange] = useState<SetBuilderBpmChange>("medium");
  const [setBpmStart, setSetBpmStart] = useState("");
  const [setBpmTarget, setSetBpmTarget] = useState("");
  const [setAutoSeedCount, setSetAutoSeedCount] = useState(5);
  const [setClassifierPreferences, setSetClassifierPreferences] = useState<Record<string, number>>({});
  const [setClassifierFlows, setSetClassifierFlows] = useState<Record<string, SetBuilderClassifierFlow>>({});
  const [hybridSources, setHybridSources] = useState<Record<HybridSearchSource, boolean>>({ mert: true, maest: true, sonara: true });
  const [hybridWeights, setHybridWeights] = useState<Record<HybridSearchSource, number>>({ mert: 1, maest: 1, sonara: 1 });
  const [hybridPerSource, setHybridPerSource] = useState(30);
  const [hybridLimit, setHybridLimit] = useState(25);
  const [hybridLoading, setHybridLoading] = useState(false);
  const [hybridError, setHybridError] = useState("");
  const [hybridResults, setHybridResults] = useState<HybridSearchResult[]>([]);
  const [hybridWarnings, setHybridWarnings] = useState<string[]>([]);
  const [hybridLimitations, setHybridLimitations] = useState<string[]>([]);
  const [hybridWeightsUsed, setHybridWeightsUsed] = useState<Record<string, number>>({});
  const [hybridPreviewKey, setHybridPreviewKey] = useState("");
  const playlistPageState = playlistPage(playlist, playlistOffset, playlistPageSize);
  useEffect(() => {
    if (playlistPageState.offset !== playlistOffset) {
      setPlaylistOffset(playlistPageState.offset);
    }
  }, [playlistOffset, playlistPageState.offset]);
  useEffect(() => {
    if (!clapPresetMenuOpen) return;
    function closePresetMenuOnOutsideClick(event: PointerEvent) {
      const target = event.target;
      if (target instanceof Node && !clapPresetMenuRef.current?.contains(target)) {
        setClapPresetMenuOpen(false);
      }
    }
    document.addEventListener("pointerdown", closePresetMenuOnOutsideClick);
    return () => document.removeEventListener("pointerdown", closePresetMenuOnOutsideClick);
  }, [clapPresetMenuOpen]);
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
  const setSeedModeTitle = optionTitle(setSeedModeOptions, setSeedMode);
  const setBuilderModeTitle = optionTitle(setBuilderModeOptions, setBuilderMode);
  const setEnergyCurveTitle = optionTitle(setEnergyCurveOptions, setEnergyCurve);
  const setBpmModeTitle = optionTitle(setBpmModeOptions, setBpmMode);
  const setBpmChangeTitle = optionTitle(setBpmChangeOptions, setBpmChange);
  const setBuilderLimitTitle = "Сколько треков вернуть в preview. Тип: целое число 1-500. Default: 24. Seeds/anchors входят в это число и размещаются как waypoint-позиции.";
  const setAutoSeedCountTitle = "Сколько waypoint anchors использовать в Auto mode. Тип: целое число 1-5. Первый anchor стартует из всей feature-complete library; остальные подбираются вокруг маршрута.";
  const setBuilderDiversityTitle = "Насколько активно раздвигать похожие кандидаты. Тип: число 0.00-1.00. 0 = ближе к anchors, 1 = больше разнообразия при сохранении связи.";
  const setBpmStartTitle = "Start BPM для явной BPM-кривой. Тип: число 20-300 или пусто = взять из первого seed/anchor, затем из библиотеки.";
  const setBpmTargetTitle = "Target BPM для явной BPM-кривой. Тип: число 20-300 или пусто = вывести из доступного диапазона библиотеки.";
  const hybridBlockTitle = "Hybrid preview: explicit weighted RRF candidate preview inside SET. Type: action block. It reads stored MERT/MAEST/SONARA data only and does not change existing search endpoints.";
  const hybridWeightTitle = "Source weight for Weighted preview. Type: number 0.00-1.00. Equal values keep sources balanced; disabled sources are ignored.";
  const hybridPerSourceTitle = "Candidates fetched per enabled source before weighted fusion. Type: integer 1-100. Default: 30.";
  const hybridLimitTitle = "Maximum Hybrid preview rows to show. Type: integer 1-100. Default: 25.";
  const autoSeedCountDisabled = setSeedMode !== "auto";
  const autoSeedCountControlTitle = autoSeedCountDisabled ? `${setAutoSeedCountTitle} Активно только когда выбран Auto - random start.` : setAutoSeedCountTitle;
  const bpmControlsDisabled = setBpmMode === "general";
  const selectedHybridSources = hybridSourceKeys.filter((source) => hybridSources[source]);
  const hybridSeedMessage = hybridSeedRequirementMessage(seeds.length);
  const hybridSourceMessage = selectedHybridSources.length ? "" : "Enable at least one Hybrid preview source.";
  const hybridReadinessMessage = hybridSeedMessage || hybridSourceMessage;
  const hybridInputKey = formatHybridInputKey(seeds, hybridSources, hybridWeights, hybridPerSource, hybridLimit);
  const hybridInputKeyRef = useRef(hybridInputKey);
  const hybridPreviewIsCurrent = hybridPreviewKey === hybridInputKey;
  const showHybridDiagnostics = hybridPreviewIsCurrent && !hybridReadinessMessage && !hybridError;
  const showHybridResults = showHybridDiagnostics && hybridResults.length > 0;
  const hybridDiagnosticTitle = formatHybridDiagnosticTitle(showHybridDiagnostics ? hybridLimitations : []);

  useEffect(() => {
    hybridInputKeyRef.current = hybridInputKey;
    setHybridError("");
    setHybridResults([]);
    setHybridWarnings([]);
    setHybridLimitations([]);
    setHybridWeightsUsed({});
    setHybridPreviewKey("");
  }, [hybridInputKey]);

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

  function setSetBuilderClassifierPreference(classifier: string, value: number) {
    setSetClassifierPreferences((current) => ({ ...current, [classifier]: value }));
  }

  function setSetBuilderClassifierFlow(classifier: string, value: SetBuilderClassifierFlow) {
    setSetClassifierFlows((current) => ({ ...current, [classifier]: value }));
  }

  function resetSetBuilderSliderControls() {
    const next = resetSetBuilderSliders();
    setSetBuilderDiversity(next.diversity);
    setSetClassifierPreferences(next.classifierPreferences);
    setSetClassifierFlows(next.classifierFlows);
  }

  function setHybridSourceEnabled(source: HybridSearchSource, enabled: boolean) {
    setHybridSources((current) => ({ ...current, [source]: enabled }));
  }

  function setHybridSourceWeight(source: HybridSearchSource, value: number) {
    setHybridWeights((current) => ({ ...current, [source]: clampNumber(value, 0, 1) }));
  }

  async function generateHybridPreview() {
    const seedMessage = hybridSeedRequirementMessage(seeds.length);
    if (seedMessage) {
      setHybridResults([]);
      setHybridWarnings([]);
      setHybridLimitations([]);
      setHybridWeightsUsed({});
      setHybridPreviewKey("");
      setHybridError(seedMessage);
      return;
    }
    const sources = hybridSourceKeys.filter((source) => hybridSources[source]);
    if (!sources.length) {
      setHybridResults([]);
      setHybridWarnings([]);
      setHybridLimitations([]);
      setHybridWeightsUsed({});
      setHybridPreviewKey("");
      setHybridError("Enable at least one Hybrid preview source.");
      return;
    }

    const requestKey = hybridInputKey;
    setHybridLoading(true);
    setHybridError("");
    setHybridResults([]);
    setHybridWarnings([]);
    setHybridLimitations([]);
    setHybridWeightsUsed({});
    setHybridPreviewKey("");
    try {
      const response = await api.hybridSearch({
        seed_track_ids: seeds,
        sources,
        weights: Object.fromEntries(sources.map((source) => [source, hybridWeights[source]])),
        per_source: hybridPerSource,
        limit: hybridLimit,
        include_diagnostics: true
      });
      if (hybridInputKeyRef.current !== requestKey) return;
      setHybridResults(response.results);
      setHybridWarnings(response.warnings);
      setHybridLimitations(response.limitations);
      setHybridWeightsUsed(response.weights_used);
      setHybridPreviewKey(requestKey);
    } catch (error) {
      if (hybridInputKeyRef.current !== requestKey) return;
      const message = error instanceof Error ? error.message : String(error);
      setHybridResults([]);
      setHybridWarnings([]);
      setHybridLimitations([]);
      setHybridWeightsUsed({});
      setHybridPreviewKey("");
      setHybridError(message);
    } finally {
      setHybridLoading(false);
    }
  }

  function generateSetBuilder() {
    const bpmStart = optionalNumberInput(setBpmStart);
    const bpmTarget = optionalNumberInput(setBpmTarget);
    const payload: SetBuilderGeneratePayload = {
      seed_mode: setSeedMode,
      seed_track_ids: setSeedMode === "manual" ? seeds : [],
      auto_seed_count: setAutoSeedCount,
      mode: setBuilderMode,
      limit: setBuilderLimit,
      diversity: setBuilderDiversity,
      energy_curve: setEnergyCurve,
      bpm_mode: setBpmMode,
      bpm_change: setBpmChange,
      classifier_preferences: compactSignedScoreMap(setClassifierPreferences),
      classifier_flows: compactClassifierFlows(setClassifierFlows, setClassifierPreferences)
    };
    if (setBpmMode !== "general") {
      if (bpmStart !== undefined) payload.bpm_start = bpmStart;
      if (bpmTarget !== undefined) payload.bpm_target = bpmTarget;
    }
    handleSetBuilderGenerate(payload);
  }

  function applyClapPromptPreset(preset: ClapPromptPreset) {
    onClapPresetChange(preset.key);
    onTextQueryChange(preset.query);
    onClapAvoidQueryChange(preset.avoidQuery);
    setClapPresetMenuOpen(false);
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
            <button className="seed-remove-chip" key={track.id} title={`Убрать seed: ${displayTrack(track)}`} onClick={() => removeSeed(track.id)}>
              {displayTrack(track)}
              <X size={14} />
            </button>
          ))}
        </div>
        <div className="search-tabs" role="tablist" aria-label="Search model">
          <button className={`model-search-tab ${activeSearchTab === "set" ? "active" : ""}`} title="Smart Set Builder" onClick={() => setActiveSearchTab("set")} role="tab" aria-selected={activeSearchTab === "set"} type="button">
            SET
          </button>
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
        {activeSearchTab === "set" && (
          <div className="search-tab-panel" role="tabpanel">
            <div className="set-builder-controls">
              <div className="set-builder-basic-controls">
                <div className="set-builder-seed-row">
                  <div className="set-builder-seed-source-control" title={setSeedModeTitle}>
                    <span>Seed source</span>
                    <div className="segmented set-builder-seed-toggle" role="group" aria-label="Seed source">
                      {setSeedModeOptions.map((option) => (
                        <button
                          key={option.value}
                          className={`set-builder-seed-mode-button ${setSeedMode === option.value ? "active" : ""}`}
                          title={option.title}
                          aria-pressed={setSeedMode === option.value}
                          onClick={() => setSetSeedMode(option.value)}
                          type="button"
                        >
                          {option.label}
                        </button>
                      ))}
                    </div>
                  </div>
                  <label className={`set-builder-auto-anchors-control ${autoSeedCountDisabled ? "disabled-filter" : ""}`} title={autoSeedCountControlTitle}>
                    Auto anchors
                    <input type="number" value={setAutoSeedCount} min={1} max={5} title={autoSeedCountControlTitle} disabled={autoSeedCountDisabled} onChange={(event) => setSetAutoSeedCount(Number(event.target.value))} />
                  </label>
                </div>
                <div className="search-filter-grid set-builder-grid set-builder-basic-grid">
                  <label title={setBuilderModeTitle}>
                    Set mode
                    <select value={setBuilderMode} title={setBuilderModeTitle} onChange={(event) => setSetBuilderMode(event.target.value as SetBuilderMode)}>
                      {setBuilderModeOptions.map((option) => (
                        <option key={option.value} value={option.value} title={option.title}>{option.label}</option>
                      ))}
                    </select>
                  </label>
                  <label title={setEnergyCurveTitle}>
                    Energy curve
                    <select value={setEnergyCurve} title={setEnergyCurveTitle} onChange={(event) => setSetEnergyCurve(event.target.value as SetBuilderEnergyCurve)}>
                      {setEnergyCurveOptions.map((option) => (
                        <option key={option.value} value={option.value} title={option.title}>{option.label}</option>
                      ))}
                    </select>
                  </label>
                  <label title={setBuilderLimitTitle}>
                    Track limit
                    <input type="number" value={setBuilderLimit} min={1} max={500} title={setBuilderLimitTitle} onChange={(event) => setSetBuilderLimit(Number(event.target.value))} />
                  </label>
                  <label title={setBuilderDiversityTitle}>
                    Diversity
                    <input type="number" value={setBuilderDiversity} min={0} max={1} step={0.05} title={setBuilderDiversityTitle} onChange={(event) => setSetBuilderDiversity(Number(event.target.value))} />
                  </label>
                </div>
              </div>
              <div className="set-builder-advanced-header">
                <button
                  className="set-builder-advanced-toggle-button"
                  type="button"
                  aria-expanded={setAdvancedControlsOpen}
                  title="Показать или скрыть расширенные настройки SET: BPM trajectory, classifier sliders и reset."
                  onClick={() => setSetAdvancedControlsOpen((current) => !current)}
                >
                  <ListFilter size={17} />
                  {setAdvancedControlsOpen ? "Hide advanced" : "Advanced"}
                </button>
              </div>
              {setAdvancedControlsOpen ? (
                <div className="set-builder-advanced-controls">
                  <div className="search-filter-grid set-builder-grid set-builder-advanced-grid">
                    <label title={setBpmModeTitle}>
                      BPM mode
                      <select value={setBpmMode} title={setBpmModeTitle} onChange={(event) => setSetBpmMode(event.target.value as SetBuilderBpmMode)}>
                        {setBpmModeOptions.map((option) => (
                          <option key={option.value} value={option.value} title={option.title}>{option.label}</option>
                        ))}
                      </select>
                    </label>
                    <label title={setBpmChangeTitle}>
                      BPM change
                      <select value={setBpmChange} title={setBpmChangeTitle} disabled={bpmControlsDisabled} onChange={(event) => setSetBpmChange(event.target.value as SetBuilderBpmChange)}>
                        {setBpmChangeOptions.map((option) => (
                          <option key={option.value} value={option.value} title={option.title}>{option.label}</option>
                        ))}
                      </select>
                    </label>
                    <label title={setBpmStartTitle}>
                      Start BPM
                      <input type="number" value={setBpmStart} min={20} max={300} step={1} placeholder="auto" title={setBpmStartTitle} disabled={bpmControlsDisabled} onChange={(event) => setSetBpmStart(event.target.value)} />
                    </label>
                    <label title={setBpmTargetTitle}>
                      Target BPM
                      <input type="number" value={setBpmTarget} min={20} max={300} step={1} placeholder="auto" title={setBpmTargetTitle} disabled={bpmControlsDisabled} onChange={(event) => setSetBpmTarget(event.target.value)} />
                    </label>
                  </div>
                  {classifiers.length ? (
                    <div className="classifier-controls set-classifier-controls">
                      {classifiers.map((classifier) => {
                        const preference = setClassifierPreferences[classifier.classifier_key] || 0;
                        const flow = setClassifierFlows[classifier.classifier_key] || setBuilderDefaultFlow;
                        return (
                          <Fragment key={classifier.classifier_key}>
                            <div className="custom-control-header" title={setClassifierHelp(classifier)}>
                              <span>{classifier.name}</span>
                            </div>
                            <div className="range-grid set-classifier-grid">
                              <label className="range-control" title={setClassifierPreferenceHelp(classifier)}>
                                <span><strong>Preference</strong><em>{formatSigned(preference)}</em></span>
                                <input type="range" min={-1} max={1} step={0.05} value={preference} title={setClassifierPreferenceHelp(classifier)} onChange={(event) => setSetBuilderClassifierPreference(classifier.classifier_key, Number(event.target.value))} />
                              </label>
                              <label title={setClassifierFlowHelp(classifier)}>
                                Flow
                                <select value={flow} title={setClassifierFlowHelp(classifier)} onChange={(event) => setSetBuilderClassifierFlow(classifier.classifier_key, event.target.value as SetBuilderClassifierFlow)}>
                                  {setClassifierFlowOptions.map((option) => (
                                    <option key={option.value} value={option.value} title={option.title}>{option.label}</option>
                                  ))}
                                </select>
                              </label>
                            </div>
                          </Fragment>
                        );
                      })}
                    </div>
                  ) : null}
                  <button className="set-builder-reset-sliders-button" title="Reset only SET sliders: diversity plus classifier preference and flow values. Seed source, mode, limit, anchors, energy curve and BPM controls stay unchanged." onClick={resetSetBuilderSliderControls} type="button">
                    <RotateCcw size={17} />
                    Reset sliders
                  </button>
                </div>
              ) : null}
            </div>
            <div className="set-builder-actions">
              <button className="set-builder-generate-button" title="Build a new ordered SET preview. Auto mode samples the first anchor from the full eligible library, then builds a related route; Manual mode distributes selected seeds as waypoints." disabled={busy || (setSeedMode === "manual" && !seeds.length)} onClick={generateSetBuilder} type="button">
                <Search size={17} />
                Generate
              </button>
              <button className="set-builder-add-all-button" title="Add all tracks from the current SET preview to the current set. It does not replace existing set tracks." disabled={busy || !results.length} onClick={addGeneratedSetToPlaylist} type="button">
                <ListMusic size={17} />
                Add preview
              </button>
            </div>
            <div className="hybrid-preview-panel" title={hybridBlockTitle}>
              <div className="custom-control-header">
                <span>Hybrid preview</span>
                <span className="hybrid-diagnostic-chip" title={hybridDiagnosticTitle}>Score info</span>
              </div>
              <p className="hybrid-preview-note">
                Uses selected seed tracks and stored analysis data only.
              </p>
              <div className="hybrid-source-grid">
                {hybridSourceOptions.map((source) => (
                  <div className="hybrid-source-row" key={source.key}>
                    <label className="toggle hybrid-source-toggle" title={source.title}>
                      <input
                        type="checkbox"
                        checked={hybridSources[source.key]}
                        title={source.title}
                        onChange={(event) => setHybridSourceEnabled(source.key, event.target.checked)}
                      />
                      {source.label}
                    </label>
                    <label className={hybridSources[source.key] ? "" : "disabled-filter"} title={hybridWeightTitle}>
                      Weight
                      <input
                        type="number"
                        value={hybridWeights[source.key]}
                        min={0}
                        max={1}
                        step={0.01}
                        title={hybridWeightTitle}
                        disabled={!hybridSources[source.key]}
                        onChange={(event) => setHybridSourceWeight(source.key, Number(event.target.value))}
                      />
                    </label>
                  </div>
                ))}
              </div>
              <div className="search-filter-grid hybrid-preview-grid">
                <label title={hybridPerSourceTitle}>
                  Per-source
                  <input type="number" value={hybridPerSource} min={1} max={100} title={hybridPerSourceTitle} onChange={(event) => setHybridPerSource(clampNumber(Number(event.target.value), 1, 100))} />
                </label>
                <label title={hybridLimitTitle}>
                  Result limit
                  <input type="number" value={hybridLimit} min={1} max={100} title={hybridLimitTitle} onChange={(event) => setHybridLimit(clampNumber(Number(event.target.value), 1, 100))} />
                </label>
              </div>
              <button className="hybrid-preview-button" title="Generate a weighted Hybrid preview from 1-5 selected seed tracks. This does not change SET, SONARA, MERT, CLAP, or CLASS behavior." disabled={busy || hybridLoading || Boolean(hybridReadinessMessage)} onClick={() => void generateHybridPreview()} type="button">
                <Search size={17} />
                {hybridLoading ? "Generating..." : "Generate weighted preview"}
              </button>
              {hybridReadinessMessage ? <span className="hybrid-status-message">{hybridReadinessMessage}</span> : null}
              {hybridError ? <span className="hybrid-status-message error">{hybridError}</span> : null}
              {showHybridResults ? (
                <span className="hybrid-status-message" title={formatHybridWeightsTitle(hybridWeightsUsed)}>
                  {hybridResults.length} weighted preview rows · {formatHybridWeightsTitle(hybridWeightsUsed)}
                </span>
              ) : null}
              {showHybridDiagnostics && hybridWarnings.length ? (
                <div className="hybrid-warning-list">
                  {hybridWarnings.slice(0, 3).map((warning, index) => (
                    <span key={`${index}-${warning}`}>{warning}</span>
                  ))}
                </div>
              ) : null}
              {showHybridResults ? (
                <div className="hybrid-preview-results" aria-label="Hybrid preview results">
                  {hybridResults.map((result) => (
                    <ResultRow
                      key={result.track.id}
                      track={result.track}
                      score={result.score}
                      scoreBreakdown={hybridScoreBreakdown(result)}
                      reason={hybridReason(result)}
                      playingTrackId={playingTrackId}
                      isSeed={seedSet.has(result.track.id)}
                      inPlaylist={playlistSet.has(result.track.id)}
                      onSeed={addSeed}
                      onTogglePlaylist={togglePlaylist}
                      onPreview={setPreview}
                      onDetails={setMetadataTrack}
                    />
                  ))}
                </div>
              ) : null}
            </div>
          </div>
        )}
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
            <div className="search-filter-grid">
              <label title={helpText.similarity}>Similarity<input type="number" value={filters.minSimilarity} min={0} max={1} step={0.01} title={helpText.similarity} onChange={(event) => setFilters({ ...filters, minSimilarity: Number(event.target.value) })} /></label>
              <label title={helpText.limit}>Limit<input type="number" value={filters.limit} min={1} max={500} title={helpText.limit} onChange={(event) => setFilters({ ...filters, limit: Number(event.target.value) })} /></label>
            </div>
            <button className="sonara-search-button" title="Найти похожие треки через SONARA по выбранным seed-трекам" disabled={busy || !seeds.length} onClick={handleSonaraSearch}>
              <Search size={17} />
              SONARA search
            </button>
          </div>
        )}
        {activeSearchTab === "mert" && (
          <div className="search-tab-panel" role="tabpanel">
            <div className="search-filter-grid">
              <label title={helpText.similarity}>Similarity<input type="number" value={filters.minSimilarity} min={0} max={1} step={0.01} title={helpText.similarity} onChange={(event) => setFilters({ ...filters, minSimilarity: Number(event.target.value) })} /></label>
              <label title={helpText.limit}>Limit<input type="number" value={filters.limit} min={1} max={500} title={helpText.limit} onChange={(event) => setFilters({ ...filters, limit: Number(event.target.value) })} /></label>
            </div>
            <button className="mert-search-button" title="Найти похожие треки через MERT по выбранным seed-трекам" disabled={busy || !seeds.length} onClick={handleMertSearch}>
              <Search size={17} />
              MERT search
            </button>
          </div>
        )}
        {activeSearchTab === "clap" && (
          <div className="search-tab-panel" role="tabpanel">
            <div className="text-search-box clap-text-search-box">
              <div className="clap-prompt-row">
                <label className="clap-query-field" title={helpText.textPrompt}>
                  Text query
                  <input
                    value={textQuery}
                    onChange={(event) => onTextQueryChange(event.target.value)}
                    placeholder="Melancholic minimal house with broken drums, warm chords, no vocals"
                    title={helpText.textPrompt}
                  />
                </label>
                <div className="clap-prompt-actions" ref={clapPresetMenuRef}>
                  <button
                    className={`icon-button folder-picker clap-presets-button ${clapPresetMenuOpen ? "active" : ""}`}
                    title="Выбрать prompt preset для CLAP"
                    aria-label="Выбрать prompt preset для CLAP"
                    aria-expanded={clapPresetMenuOpen}
                    onClick={() => setClapPresetMenuOpen((current) => !current)}
                    type="button"
                  >
                    <ListFilter size={17} />
                  </button>
                  {clapPresetMenuOpen ? (
                    <div className="clap-preset-menu" role="menu">
                      {clapPromptPresets.map((preset) => (
                        <button
                          className={`clap-preset-option-button ${clapPresetKey === preset.key ? "active" : ""}`}
                          key={preset.key}
                          title={`Применить preset: ${preset.label}`}
                          onClick={() => applyClapPromptPreset(preset)}
                          type="button"
                        >
                          {preset.label}
                        </button>
                      ))}
                    </div>
                  ) : null}
                </div>
              </div>
              <label className="clap-avoid-field" title="Negative CLAP prompt. Type: text. Optional; presets fill this field directly.">
                Avoid
                <input
                  className="clap-avoid-input"
                  value={clapAvoidQuery}
                  onChange={(event) => onClapAvoidQueryChange(event.target.value)}
                  placeholder="bright pop, straight drums, vocals"
                  title="Negative CLAP prompt. Type: text. Optional; presets fill this field directly."
                />
              </label>
            </div>
            <div className="search-filter-grid">
              <label title={helpText.similarity}>Similarity<input type="number" value={filters.minSimilarity} min={0} max={1} step={0.01} title={helpText.similarity} onChange={(event) => setFilters({ ...filters, minSimilarity: Number(event.target.value) })} /></label>
              <label title={helpText.limit}>Limit<input type="number" value={filters.limit} min={1} max={500} title={helpText.limit} onChange={(event) => setFilters({ ...filters, limit: Number(event.target.value) })} /></label>
            </div>
            <button className="clap-text-search-button" title="Найти треки через CLAP по текстовому описанию звучания" disabled={busy || !textQuery.trim()} onClick={handleTextSearch}>
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
                      <button
                        className="icon-button classifier-analyze-button"
                        title={`Reset and rescore all ${classifier.name} classifier results`}
                        aria-label={`Reset and rescore all ${classifier.name} classifier results`}
                        disabled={busy}
                        onClick={() => onAnalyzeClassifier(classifier)}
                        type="button"
                      >
                        <Play size={15} />
                      </button>
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
          </div>
        )}
        <div className="results-list">
          {results.map(({ track, score, score_breakdown, reason, sonara_groups, classifier_scores, transition }) => (
            <ResultRow
              key={track.id}
              track={track}
              score={score}
              scoreBreakdown={score_breakdown}
              reason={reason}
              sonaraGroups={sonara_groups}
              classifierScores={classifier_scores}
              transition={transition}
              playingTrackId={playingTrackId}
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
      <section className="playlist-export-section">
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
              const trackPreviewActive = playingTrackId === track.id;
              return (
                <div className="playlist-row" key={track.id}>
                  <span className="row-index">{playlistPageState.offset + index + 1}</span>
                  <button className="icon-button playlist-preview-button" title={trackPreviewActive ? "Pause preview" : "Preview"} aria-label={`${trackPreviewActive ? "Pause" : "Preview"} ${displayTrack(track)}`} onClick={() => setPreview(track)}>
                    {trackPreviewActive ? <Pause size={15} /> : <Play size={15} />}
                  </button>
                  <div className="track-title-cell">
                    <strong>{displayTrack(track)}</strong>
                  </div>
                  <button className="icon-button playlist-metadata-button" title="Теги и жанры" aria-label={`Теги ${displayTrack(track)}`} onClick={() => setMetadataTrack(track)}><Tags size={15} /></button>
                  <button className="icon-button intent-remove playlist-remove-button" title="Убрать из сета" aria-label={`Убрать ${displayTrack(track)} из сета`} onClick={() => removeFromPlaylist(track.id)}><Trash2 size={15} /></button>
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

function optionTitle<T extends string>(options: Array<SelectOption<T>>, value: T) {
  return options.find((option) => option.value === value)?.title || "";
}

function setClassifierHelp(classifier: PromotedClassifier) {
  const label = classifier.positive_label ? ` Положительная метка: ${classifier.positive_label}.` : "";
  return `Classifier intent для ${classifier.name}. Использует только сохраненные promoted classifier scores; 0 нейтрально, отсутствующие scores остаются нейтральными.${label}`;
}

function setClassifierPreferenceHelp(classifier: PromotedClassifier) {
  return `Preference для ${classifier.name}. Тип: число -1.00..+1.00. Плюс предпочитает высокий classifier score, минус предпочитает низкий score, 0 отключает влияние.`;
}

function setClassifierFlowHelp(classifier: PromotedClassifier) {
  return `Flow для ${classifier.name}. Тип: Flat/Rise/Fall. Flat применяет Preference ровно; Rise усиливает выбранную сторону к концу SET; Fall сильнее держит ее в начале.`;
}

function compactSignedScoreMap(values: Record<string, number>) {
  return Object.fromEntries(Object.entries(values).filter(([, value]) => value !== 0));
}

function optionalNumberInput(value: string) {
  const trimmed = value.trim();
  if (!trimmed) return undefined;
  const parsed = Number(trimmed);
  return Number.isFinite(parsed) ? parsed : undefined;
}

function clampNumber(value: number, min: number, max: number) {
  if (!Number.isFinite(value)) return min;
  return Math.max(min, Math.min(max, value));
}

function hybridSeedRequirementMessage(seedCount: number) {
  if (seedCount < 1) return "Hybrid preview requires 1-5 selected seed tracks.";
  if (seedCount > 5) return "Hybrid preview uses at most 5 selected seed tracks; remove extra seeds first.";
  return "";
}

function formatHybridInputKey(
  seeds: number[],
  sources: Record<HybridSearchSource, boolean>,
  weights: Record<HybridSearchSource, number>,
  perSource: number,
  limit: number
) {
  const sourceState = hybridSourceKeys.map((source) => `${source}:${sources[source] ? "1" : "0"}:${weights[source]}`).join("|");
  return `${seeds.join(",")}|${sourceState}|${perSource}|${limit}`;
}

function formatHybridDiagnosticTitle(limitations: string[]) {
  const scoreDescription = "Preview score is weighted RRF, not confidence.";
  if (!limitations.length) return scoreDescription;
  return `${scoreDescription} ${limitations.join(" ")}`;
}

function hybridReason(result: HybridSearchResult) {
  const sourceCount = result.match_character?.source_count ?? Object.keys(result.score_breakdown).length;
  return `weighted_preview_${sourceCount}_sources`;
}

function hybridScoreBreakdown(result: HybridSearchResult) {
  const sourceCount = result.match_character?.source_count ?? Object.keys(result.score_breakdown).length;
  const breakdown: Record<string, number> = {
    raw_rrf_score: result.raw_rrf_score,
    source_count: sourceCount,
    rank: result.rank
  };
  for (const [source, details] of Object.entries(result.score_breakdown)) {
    breakdown[`${source}_rank`] = Number(details.rank);
    breakdown[`${source}_weight`] = Number(details.weight);
    breakdown[`${source}_contribution`] = Number(details.contribution);
    if (typeof details.score === "number") breakdown[`${source}_source_score`] = details.score;
  }
  return breakdown;
}

function formatHybridWeightsTitle(weights: Record<string, number>) {
  const entries = Object.entries(weights);
  if (!entries.length) return "Weights pending";
  return entries.map(([source, weight]) => `${source.toUpperCase()} ${weight.toFixed(2)}`).join(" · ");
}

function compactClassifierFlows(values: Record<string, SetBuilderClassifierFlow>, preferences: Record<string, number>) {
  return Object.fromEntries(
    Object.entries(values).filter(([key, value]) => value !== setBuilderDefaultFlow && preferences[key] !== undefined && preferences[key] !== 0)
  );
}
