import { Dispatch, Fragment, SetStateAction, useEffect, useRef, useState } from "react";
import { Download, FolderOpen, ListFilter, ListMusic, Pause, Play, RotateCcw, Search, Tags, Trash2, X } from "lucide-react";
import { AnalysisJobStatus, PromotedClassifier, SearchResult, SetBuilderBpmChange, SetBuilderBpmMode, SetBuilderEnergyCurve, SetBuilderGeneratePayload, SetBuilderMode, SetBuilderSeedMode, SonaraMixerWeights, SonaraModifiers, Track } from "./api";
import type { ClapPromptPreset } from "./clapPrompt";
import { playlistPage } from "./playlistView";
import { resetSetBuilderSliders, setBuilderDefaultCurve, setBuilderDefaultDiversity } from "./setBuilderControls";
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
    label: "Auto - random related",
    title: "Auto: каждый запуск случайно выбирает 1-5 связанных feature-complete waypoint anchors и распределяет их по SET preview."
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
  const [setClassifierTargets, setSetClassifierTargets] = useState<Record<string, number>>({});
  const [setClassifierAvoid, setSetClassifierAvoid] = useState<Record<string, number>>({});
  const [setClassifierCurves, setSetClassifierCurves] = useState<Record<string, { start: number; end: number }>>({});
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
  const setAutoSeedCountTitle = "Сколько случайных связанных waypoint anchors выбрать в Auto mode. Тип: целое число 1-5. Каждый запуск пересэмпливает anchors.";
  const setBuilderDiversityTitle = "Насколько активно раздвигать похожие кандидаты. Тип: число 0.00-1.00. 0 = ближе к anchors, 1 = больше разнообразия при сохранении связи.";
  const setBpmStartTitle = "Start BPM для явной BPM-кривой. Тип: число 20-300 или пусто = взять из первого seed/anchor, затем из библиотеки.";
  const setBpmTargetTitle = "Target BPM для явной BPM-кривой. Тип: число 20-300 или пусто = вывести из доступного диапазона библиотеки.";
  const bpmControlsDisabled = setBpmMode === "general";

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

  function setSetBuilderClassifierTarget(classifier: string, value: number) {
    setSetClassifierTargets((current) => ({ ...current, [classifier]: value }));
  }

  function setSetBuilderClassifierAvoid(classifier: string, value: number) {
    setSetClassifierAvoid((current) => ({ ...current, [classifier]: value }));
  }

  function setSetBuilderClassifierCurveValue(classifier: string, key: "start" | "end", value: number) {
    setSetClassifierCurves((current) => ({
      ...current,
      [classifier]: { start: current[classifier]?.start ?? 0.5, end: current[classifier]?.end ?? 0.5, [key]: value }
    }));
  }

  function resetSetBuilderSliderControls() {
    const next = resetSetBuilderSliders();
    setSetBuilderDiversity(next.diversity);
    setSetClassifierTargets(next.classifierTargets);
    setSetClassifierAvoid(next.classifierAvoid);
    setSetClassifierCurves(next.classifierCurves);
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
      classifier_targets: compactScoreMap(setClassifierTargets),
      classifier_avoid: compactScoreMap(setClassifierAvoid),
      classifier_curves: compactCurves(setClassifierCurves)
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
              <div className="search-filter-grid set-builder-grid set-builder-basic-controls">
                <label title={setSeedModeTitle}>
                  Seed source
                  <select value={setSeedMode} title={setSeedModeTitle} onChange={(event) => setSetSeedMode(event.target.value as SetBuilderSeedMode)}>
                    {setSeedModeOptions.map((option) => (
                      <option key={option.value} value={option.value} title={option.title}>{option.label}</option>
                    ))}
                  </select>
                </label>
                <label title={setBuilderModeTitle}>
                  Set mode
                  <select value={setBuilderMode} title={setBuilderModeTitle} onChange={(event) => setSetBuilderMode(event.target.value as SetBuilderMode)}>
                    {setBuilderModeOptions.map((option) => (
                      <option key={option.value} value={option.value} title={option.title}>{option.label}</option>
                    ))}
                  </select>
                </label>
                <label title={setBuilderLimitTitle}>
                  Track limit
                  <input type="number" value={setBuilderLimit} min={1} max={500} title={setBuilderLimitTitle} onChange={(event) => setSetBuilderLimit(Number(event.target.value))} />
                </label>
                <label title={setEnergyCurveTitle}>
                  Energy curve
                  <select value={setEnergyCurve} title={setEnergyCurveTitle} onChange={(event) => setSetEnergyCurve(event.target.value as SetBuilderEnergyCurve)}>
                    {setEnergyCurveOptions.map((option) => (
                      <option key={option.value} value={option.value} title={option.title}>{option.label}</option>
                    ))}
                  </select>
                </label>
                {setSeedMode === "auto" && (
                  <label title={setAutoSeedCountTitle}>
                    Auto anchors
                    <input type="number" value={setAutoSeedCount} min={1} max={5} title={setAutoSeedCountTitle} onChange={(event) => setSetAutoSeedCount(Number(event.target.value))} />
                  </label>
                )}
              </div>
              <div className="set-builder-advanced-header">
                <button
                  className="set-builder-advanced-toggle-button"
                  type="button"
                  aria-expanded={setAdvancedControlsOpen}
                  title="Показать или скрыть расширенные настройки SET: diversity, BPM trajectory, classifier sliders и reset."
                  onClick={() => setSetAdvancedControlsOpen((current) => !current)}
                >
                  <ListFilter size={17} />
                  {setAdvancedControlsOpen ? "Hide advanced" : "Advanced"}
                </button>
              </div>
              {setAdvancedControlsOpen ? (
                <div className="set-builder-advanced-controls">
                  <div className="search-filter-grid set-builder-grid set-builder-advanced-grid">
                    <label title={setBuilderDiversityTitle}>
                      Diversity
                      <input type="number" value={setBuilderDiversity} min={0} max={1} step={0.05} title={setBuilderDiversityTitle} onChange={(event) => setSetBuilderDiversity(Number(event.target.value))} />
                    </label>
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
                        const target = setClassifierTargets[classifier.classifier_key] || 0;
                        const avoid = setClassifierAvoid[classifier.classifier_key] || 0;
                        const curve = setClassifierCurves[classifier.classifier_key] || setBuilderDefaultCurve;
                        return (
                          <Fragment key={classifier.classifier_key}>
                            <div className="custom-control-header" title={setClassifierHelp(classifier)}>
                              <span>{classifier.name}</span>
                            </div>
                            <div className="range-grid set-classifier-grid">
                              <label className="range-control" title={setClassifierTargetHelp(classifier)}>
                                <span><strong>Target boost</strong><em>{target.toFixed(2)}</em></span>
                                <input type="range" min={0} max={1} step={0.05} value={target} title={setClassifierTargetHelp(classifier)} onChange={(event) => setSetBuilderClassifierTarget(classifier.classifier_key, Number(event.target.value))} />
                              </label>
                              <label className="range-control" title={setClassifierAvoidHelp(classifier)}>
                                <span><strong>Avoid cut</strong><em>{avoid.toFixed(2)}</em></span>
                                <input type="range" min={0} max={1} step={0.05} value={avoid} title={setClassifierAvoidHelp(classifier)} onChange={(event) => setSetBuilderClassifierAvoid(classifier.classifier_key, Number(event.target.value))} />
                              </label>
                              <label className="range-control" title={setClassifierCurveStartHelp(classifier)}>
                                <span><strong>Curve start</strong><em>{curve.start.toFixed(2)}</em></span>
                                <input type="range" min={0} max={1} step={0.05} value={curve.start} title={setClassifierCurveStartHelp(classifier)} onChange={(event) => setSetBuilderClassifierCurveValue(classifier.classifier_key, "start", Number(event.target.value))} />
                              </label>
                              <label className="range-control" title={setClassifierCurveEndHelp(classifier)}>
                                <span><strong>Curve end</strong><em>{curve.end.toFixed(2)}</em></span>
                                <input type="range" min={0} max={1} step={0.05} value={curve.end} title={setClassifierCurveEndHelp(classifier)} onChange={(event) => setSetBuilderClassifierCurveValue(classifier.classifier_key, "end", Number(event.target.value))} />
                              </label>
                            </div>
                          </Fragment>
                        );
                      })}
                    </div>
                  ) : null}
                  <button className="set-builder-reset-sliders-button" title="Reset only SET sliders: diversity and classifier target/avoid/curve values. Seed source, mode, limit, anchors, energy curve and BPM controls stay unchanged." onClick={resetSetBuilderSliderControls} type="button">
                    <RotateCcw size={17} />
                    Reset sliders
                  </button>
                </div>
              ) : null}
            </div>
            <div className="set-builder-actions">
              <button className="set-builder-generate-button" title="Build a new ordered SET preview. Auto mode resamples related waypoint anchors on every run; Manual mode distributes selected seeds as waypoints." disabled={busy || (setSeedMode === "manual" && !seeds.length)} onClick={generateSetBuilder} type="button">
                <Search size={17} />
                Generate
              </button>
              <button className="set-builder-add-all-button" title="Add all tracks from the current SET preview to the current set. It does not replace existing set tracks." disabled={busy || !results.length} onClick={addGeneratedSetToPlaylist} type="button">
                <ListMusic size={17} />
                Add preview
              </button>
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
  return `Смещение SET для ${classifier.name}. Использует только сохраненные promoted classifier scores; отсутствующие scores остаются нейтральными.${label}`;
}

function setClassifierTargetHelp(classifier: PromotedClassifier) {
  return `Target boost для ${classifier.name}. Тип: число 0.00-1.00. Треки с сохраненным score на этом уровне или выше получают усиление; 0 отключает этот target.`;
}

function setClassifierAvoidHelp(classifier: PromotedClassifier) {
  return `Avoid cut для ${classifier.name}. Тип: число 0.00-1.00. Треки с сохраненным score на этом уровне или выше понижаются в ранжировании; 0 отключает это avoid-правило.`;
}

function setClassifierCurveStartHelp(classifier: PromotedClassifier) {
  return `Curve start для ${classifier.name}. Тип: число 0.00-1.00. Желаемая интенсивность classifier-сигнала в начале сгенерированного SET; 0.50 нейтрально.`;
}

function setClassifierCurveEndHelp(classifier: PromotedClassifier) {
  return `Curve end для ${classifier.name}. Тип: число 0.00-1.00. Желаемая интенсивность classifier-сигнала в конце сгенерированного SET; 0.50 нейтрально.`;
}

function compactScoreMap(values: Record<string, number>) {
  return Object.fromEntries(Object.entries(values).filter(([, value]) => value > 0));
}

function optionalNumberInput(value: string) {
  const trimmed = value.trim();
  if (!trimmed) return undefined;
  const parsed = Number(trimmed);
  return Number.isFinite(parsed) ? parsed : undefined;
}

function compactCurves(values: Record<string, { start: number; end: number }>) {
  return Object.fromEntries(
    Object.entries(values).filter(([, value]) => value.start !== 0.5 || value.end !== 0.5)
  );
}
