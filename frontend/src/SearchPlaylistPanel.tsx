import { Dispatch, Fragment, SetStateAction, useEffect, useRef, useState } from "react";
import { Download, FolderOpen, ListFilter, ListMusic, Pause, Play, RotateCcw, Search, Tags, Trash2, X } from "lucide-react";
import { AnalysisJobStatus, api, HybridClassifierSignal, HybridMatchAxis, HybridSearchResult, HybridSearchSource, PromotedClassifier, SearchResult, SetBuilderBpmChange, SetBuilderBpmMode, SetBuilderClassifierFlow, SetBuilderEnergyCurve, SetBuilderGeneratePayload, SetBuilderMode, SetBuilderSeedMode, SonaraMixerWeights, SonaraModifiers, Track } from "./api";
import type { EvaluationPairFeedbackResult, EvaluationPairFeedbackState, EvaluationPairReasonTag } from "./api";
import { classifierScoringBlockedReason } from "./classifierCompatibility";
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

const hybridSourceKeys: HybridSearchSource[] = ["mert", "maest", "sonara", "clap"];

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
  },
  {
    key: "clap",
    label: "CLAP",
    title: "CLAP source for Hybrid preview. Type: checkbox on/off. Range: enabled or disabled. Uses stored CLAP audio embeddings only, without prompt input."
  }
];
const hybridAxisOrder: HybridMatchAxis[] = ["groove", "density", "texture", "mood", "tonal", "vocalness", "energy_flow", "novelty"];
const hybridAxisLabels: Record<HybridMatchAxis, string> = {
  groove: "Groove",
  density: "Density",
  texture: "Texture",
  mood: "Mood",
  tonal: "Tonal",
  vocalness: "Vocalness",
  energy_flow: "Energy flow",
  novelty: "Novelty"
};

type HybridClassifierSignalOption = {
  key: string;
  classifierKey: string;
  label: string;
  title: string;
  role: string;
  axis: string;
  enabledByDefault: boolean;
  preference?: number;
  riskWeight?: number;
};

type PairFeedbackRating = 0 | 1 | 2 | 3;

type HybridFeedbackDraft = {
  rating: PairFeedbackRating | null;
  reasonTags: EvaluationPairReasonTag[];
  status: "unrated" | "rated" | "mixed";
};

const hybridFeedbackSource = "hybrid_ui";

const hybridFeedbackRatings: Array<{ value: PairFeedbackRating; label: string }> = [
  { value: 3, label: "Strong" },
  { value: 2, label: "Works" },
  { value: 1, label: "Maybe" },
  { value: 0, label: "Reject" }
];

const hybridFeedbackReasonTags: Array<{ value: EvaluationPairReasonTag; label: string }> = [
  { value: "good_groove", label: "Good groove" },
  { value: "good_density", label: "Good density" },
  { value: "good_texture", label: "Good texture" },
  { value: "good_mood", label: "Good mood" },
  { value: "good_tonal", label: "Good tonal" },
  { value: "too_vocal", label: "Too vocal" },
  { value: "bad_density", label: "Bad density" },
  { value: "bad_tonal", label: "Bad tonal" },
  { value: "too_obvious", label: "Too obvious" },
  { value: "interesting_adjacent", label: "Interesting adjacent" },
  { value: "wrong_energy", label: "Wrong energy" },
  { value: "wrong_texture", label: "Wrong texture" },
  { value: "bad_transition_risk", label: "Bad transition risk" }
];

const classifierEmptyStateMessage = "No promoted classifier profiles found. Promote profiles from Rhythm Lab or place model.json + model.joblib under models/classifiers/<profile>/.";

export function SearchPlaylistPanel({
  seedTracks,
  textQuery,
  onTextQueryChange,
  clapAvoidQuery,
  onClapAvoidQueryChange,
  clapPresetKey,
  onClapPresetChange,
  clapPromptPresets,
  databasePath,
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
  clapEmbeddingCount,
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
  databasePath: string | null;
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
  clapEmbeddingCount: number;
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
  const [hybridSources, setHybridSources] = useState<Record<HybridSearchSource, boolean>>({ mert: true, maest: true, sonara: true, clap: true });
  const [hybridWeights, setHybridWeights] = useState<Record<HybridSearchSource, number>>({ mert: 1, maest: 1, sonara: 1, clap: 1 });
  const [hybridPerSource, setHybridPerSource] = useState(30);
  const [hybridLimit, setHybridLimit] = useState(25);
  const [hybridTransitionRiskWeight, setHybridTransitionRiskWeight] = useState(0);
  const [hybridUseClassifierPreferences, setHybridUseClassifierPreferences] = useState(false);
  const [hybridClassifierToggles, setHybridClassifierToggles] = useState<Record<string, boolean>>({});
  const [hybridLoading, setHybridLoading] = useState(false);
  const [hybridError, setHybridError] = useState("");
  const [hybridResults, setHybridResults] = useState<HybridSearchResult[]>([]);
  const [hybridWarnings, setHybridWarnings] = useState<string[]>([]);
  const [hybridLimitations, setHybridLimitations] = useState<string[]>([]);
  const [hybridWeightsUsed, setHybridWeightsUsed] = useState<Record<string, number>>({});
  const [hybridPreviewKey, setHybridPreviewKey] = useState("");
  const [hybridSessionId, setHybridSessionId] = useState<number | null>(null);
  const [hybridFeedbackDrafts, setHybridFeedbackDrafts] = useState<Record<number, HybridFeedbackDraft>>({});
  const [hybridFeedbackSaving, setHybridFeedbackSaving] = useState<Record<number, boolean>>({});
  const [hybridFeedbackErrors, setHybridFeedbackErrors] = useState<Record<number, string>>({});
  const [hybridSelectedResultId, setHybridSelectedResultId] = useState<number | null>(null);
  const [evaluationLabelCounts, setEvaluationLabelCounts] = useState<{ pair: number; transition: number } | null>(null);
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
  const hybridBlockTitle = "Hybrid preview: explicit weighted RRF candidate preview inside SET. Type: action block. Direct API calls are read-only by default; this UI records evaluation session/event rows for feedback only.";
  const hybridWeightTitle = "Source weight for Weighted preview. Type: number 0.00-1.00. Equal values keep sources balanced; disabled sources are ignored.";
  const hybridPerSourceTitle = "Candidates fetched per enabled source before weighted fusion. Type: integer 1-100. Default: 30.";
  const hybridLimitTitle = "Maximum Hybrid preview rows to show. Type: integer 1-100. Default: 25.";
  const hybridRiskPenaltyTitle = "Optional penalty for diagnostic transition risk. Type: number 0.00-1.00. Score remains an unsupervised diagnostic.";
  const hybridClassifierTitle = "Optional Hybrid classifier controls. Type: checkboxes. They read stored promoted classifier scores only; missing scores stay neutral.";
  const autoSeedCountDisabled = setSeedMode !== "auto";
  const autoSeedCountControlTitle = autoSeedCountDisabled ? `${setAutoSeedCountTitle} Активно только когда выбран Auto - random start.` : setAutoSeedCountTitle;
  const bpmControlsDisabled = setBpmMode === "general";
  const selectedHybridSources = hybridSourceKeys.filter((source) => hybridSources[source]);
  const hybridClassifierOptions = hybridClassifierSignalOptions(classifiers);
  const hybridSeedMessage = hybridSeedRequirementMessage(seeds.length);
  const hybridSourceMessage = selectedHybridSources.length ? "" : "Enable at least one Hybrid preview source.";
  const hybridReadinessMessage = hybridSeedMessage || hybridSourceMessage;
  const hybridInputKey = formatHybridInputKey(seeds, hybridSources, hybridWeights, hybridPerSource, hybridLimit, hybridTransitionRiskWeight, hybridUseClassifierPreferences, hybridClassifierToggles, hybridClassifierOptions);
  const hybridInputKeyRef = useRef(hybridInputKey);
  const hybridPreviewIsCurrent = hybridPreviewKey === hybridInputKey;
  const showHybridDiagnostics = hybridPreviewIsCurrent && !hybridReadinessMessage && !hybridError;
  const showHybridResults = showHybridDiagnostics && hybridResults.length > 0;
  const selectedHybridResult = showHybridResults ? hybridResults.find((result) => result.track.id === hybridSelectedResultId) || hybridResults[0] : null;
  const hybridDiagnosticTitle = formatHybridDiagnosticTitle(showHybridDiagnostics ? hybridLimitations : []);
  const hasStoredClapEmbeddings = clapEmbeddingCount > 0;
  const clapSearchTitle = hasStoredClapEmbeddings
    ? "Найти треки через CLAP по текстовому описанию звучания. Требуются сохраненные CLAP audio embeddings в SQLite."
    : "CLAP search requires stored CLAP audio embeddings. Запустите анализ CLAP для библиотеки, затем повторите текстовый поиск.";

  useEffect(() => {
    hybridInputKeyRef.current = hybridInputKey;
    setHybridError("");
    setHybridResults([]);
    setHybridWarnings([]);
    setHybridLimitations([]);
    setHybridWeightsUsed({});
    setHybridPreviewKey("");
    setHybridSessionId(null);
    setHybridFeedbackDrafts({});
    setHybridFeedbackSaving({});
    setHybridFeedbackErrors({});
    setHybridSelectedResultId(null);
  }, [hybridInputKey]);

  useEffect(() => {
    if (!databasePath) {
      setEvaluationLabelCounts(null);
      return;
    }
    void refreshEvaluationLabelCounts();
  }, [databasePath]);

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

  function setHybridClassifierToggle(toggle: string, enabled: boolean) {
    setHybridClassifierToggles((current) => ({ ...current, [toggle]: enabled }));
  }

  async function refreshEvaluationLabelCounts() {
    try {
      const summary = await api.evaluationSummary();
      setEvaluationLabelCounts({
        pair: summary.counts.track_pair_feedback,
        transition: summary.counts.transition_feedback
      });
    } catch {
      setEvaluationLabelCounts(null);
    }
  }

  async function saveHybridFeedback(result: HybridSearchResult, rating: PairFeedbackRating, reasonTags: EvaluationPairReasonTag[]) {
    const candidateTrackId = result.track.id;
    if (!hybridPreviewIsCurrent) return;
    if (hybridReadinessMessage) return;
    setHybridFeedbackSaving((current) => ({ ...current, [candidateTrackId]: true }));
    setHybridFeedbackErrors((current) => ({ ...current, [candidateTrackId]: "" }));
    try {
      const response = await api.evaluationPairFeedback({
        session_id: hybridSessionId,
        seed_track_ids: seeds,
        candidate_track_id: candidateTrackId,
        rating,
        reason_tags: reasonTags,
        notes: "",
        source: hybridFeedbackSource
      });
      const feedback = hybridFeedbackFromResponse(response);
      setHybridResults((current) => current.map((row) => (row.track.id === candidateTrackId ? { ...row, feedback } : row)));
      setHybridFeedbackDrafts((current) => ({ ...current, [candidateTrackId]: hybridFeedbackDraftFromState(feedback) }));
      await refreshEvaluationLabelCounts();
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      setHybridFeedbackErrors((current) => ({ ...current, [candidateTrackId]: message }));
    } finally {
      setHybridFeedbackSaving((current) => ({ ...current, [candidateTrackId]: false }));
    }
  }

  function setHybridFeedbackRating(result: HybridSearchResult, rating: PairFeedbackRating) {
    const draft = hybridFeedbackDrafts[result.track.id] || emptyHybridFeedbackDraft();
    void saveHybridFeedback(result, rating, draft.reasonTags);
  }

  function toggleHybridFeedbackReason(result: HybridSearchResult, reasonTag: EvaluationPairReasonTag) {
    const draft = hybridFeedbackDrafts[result.track.id] || emptyHybridFeedbackDraft();
    const reasonTags = toggleReasonTag(draft.reasonTags, reasonTag);
    if (draft.rating == null) {
      setHybridFeedbackDrafts((current) => ({ ...current, [result.track.id]: { ...draft, reasonTags } }));
      return;
    }
    void saveHybridFeedback(result, draft.rating, reasonTags);
  }

  async function generateHybridPreview() {
    const seedMessage = hybridSeedRequirementMessage(seeds.length);
    if (seedMessage) {
      setHybridResults([]);
      setHybridWarnings([]);
      setHybridLimitations([]);
      setHybridWeightsUsed({});
      setHybridPreviewKey("");
      setHybridSessionId(null);
      setHybridFeedbackDrafts({});
      setHybridFeedbackSaving({});
      setHybridFeedbackErrors({});
      setHybridSelectedResultId(null);
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
      setHybridSessionId(null);
      setHybridFeedbackDrafts({});
      setHybridFeedbackSaving({});
      setHybridFeedbackErrors({});
      setHybridSelectedResultId(null);
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
    setHybridSessionId(null);
    setHybridFeedbackDrafts({});
    setHybridFeedbackSaving({});
    setHybridFeedbackErrors({});
    setHybridSelectedResultId(null);
    try {
      const response = await api.hybridSearch({
        seed_track_ids: seeds,
        sources,
        weights: Object.fromEntries(sources.map((source) => [source, hybridWeights[source]])),
        per_source: hybridPerSource,
        limit: hybridLimit,
        transition_risk_weight: hybridTransitionRiskWeight,
        transition_risk_version: "v2",
        classifier_preferences: hybridUseClassifierPreferences ? hybridClassifierPreferences(hybridClassifierToggles, hybridClassifierOptions) : {},
        classifier_risk_weights: hybridUseClassifierPreferences ? hybridClassifierRiskWeights(hybridClassifierToggles, hybridClassifierOptions) : {},
        include_diagnostics: true,
        record_session: true
      });
      if (hybridInputKeyRef.current !== requestKey) return;
      setHybridResults(response.results);
      setHybridSessionId(response.session_id ?? null);
      setHybridFeedbackDrafts(hybridFeedbackDraftsFromResults(response.results));
      setHybridFeedbackErrors({});
      setHybridSelectedResultId(response.results[0]?.track.id ?? null);
      setHybridWarnings(response.warnings);
      setHybridLimitations(response.limitations);
      setHybridWeightsUsed(response.weights_used);
      setHybridPreviewKey(requestKey);
      void refreshEvaluationLabelCounts();
    } catch (error) {
      if (hybridInputKeyRef.current !== requestKey) return;
      const message = error instanceof Error ? error.message : String(error);
      setHybridResults([]);
      setHybridWarnings([]);
      setHybridLimitations([]);
      setHybridWeightsUsed({});
      setHybridPreviewKey("");
      setHybridSessionId(null);
      setHybridFeedbackDrafts({});
      setHybridFeedbackSaving({});
      setHybridFeedbackErrors({});
      setHybridSelectedResultId(null);
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
                Uses stored MERT, MAEST, SONARA, and CLAP analysis data only. Direct API calls are read-only by default; this UI records evaluation session/event rows so feedback can be attached.
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
              <div className="hybrid-classifier-controls" title={hybridClassifierTitle}>
                <label className="toggle hybrid-classifier-master" title={hybridClassifierTitle}>
                  <input
                    type="checkbox"
                    checked={hybridUseClassifierPreferences}
                    title={hybridClassifierTitle}
                    onChange={(event) => setHybridUseClassifierPreferences(event.target.checked)}
                  />
                  Use classifier preferences
                </label>
                <div className="hybrid-classifier-toggle-grid">
                  {hybridClassifierOptions.length ? (
                    hybridClassifierOptions.map((option) => (
                      <label className="toggle hybrid-classifier-toggle" key={option.key} title={option.title}>
                        <input
                          type="checkbox"
                          checked={hybridClassifierToggleEnabled(hybridClassifierToggles, option)}
                          disabled={!hybridUseClassifierPreferences}
                          title={option.title}
                          onChange={(event) => setHybridClassifierToggle(option.key, event.target.checked)}
                        />
                        {option.label}
                      </label>
                    ))
                  ) : (
                    <span className="muted-inline">No Hybrid classifier signals</span>
                  )}
                </div>
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
                <label title={hybridRiskPenaltyTitle}>
                  Risk penalty
                  <input type="number" value={hybridTransitionRiskWeight} min={0} max={1} step={0.01} title={hybridRiskPenaltyTitle} onChange={(event) => setHybridTransitionRiskWeight(clampNumber(Number(event.target.value), 0, 1))} />
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
              {evaluationLabelCounts ? (
                <span className="hybrid-status-message">
                  Evaluation labels: {evaluationLabelCounts.pair} pair ratings / {evaluationLabelCounts.transition} transition ratings.
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
                      selected={selectedHybridResult?.track.id === result.track.id}
                      onSelect={() => setHybridSelectedResultId(result.track.id)}
                      selectTitle={`Show Hybrid diagnostics for ${displayTrack(result.track)}`}
                    />
                  ))}
                  {selectedHybridResult ? (
                    <HybridResultDetails
                      result={selectedHybridResult}
                      draft={hybridFeedbackDrafts[selectedHybridResult.track.id] || emptyHybridFeedbackDraft()}
                      saving={Boolean(hybridFeedbackSaving[selectedHybridResult.track.id])}
                      error={hybridFeedbackErrors[selectedHybridResult.track.id] || ""}
                      onRate={(rating) => setHybridFeedbackRating(selectedHybridResult, rating)}
                      onToggleReason={(reasonTag) => toggleHybridFeedbackReason(selectedHybridResult, reasonTag)}
                    />
                  ) : null}
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
            <button className="clap-text-search-button" title={clapSearchTitle} disabled={busy || !textQuery.trim() || !hasStoredClapEmbeddings} onClick={handleTextSearch} type="button">
              <Search size={17} />
              CLAP search
            </button>
            {!hasStoredClapEmbeddings ? <span className="clap-search-requirement">Requires stored CLAP embeddings. Run CLAP analysis first.</span> : null}
          </div>
        )}
        {activeSearchTab === "class" && (
          <div className="search-tab-panel" role="tabpanel">
            {classifiers.length ? (
              <div className="classifier-controls">
                {classifiers.map((classifier) => {
                  const title = classifierHelp(classifier);
                  const value = classifierMinScores[classifier.classifier_key] || 0;
                  const blockedReason = classifierScoringBlockedReason(classifier);
                  const rescoreTitle = blockedReason ? `Cannot rescore ${classifier.name}: ${blockedReason}` : `Reset and rescore all ${classifier.name} classifier results`;
                  return (
                    <Fragment key={classifier.classifier_key}>
                      <div className="custom-control-header" title={title}>
                        <span>{classifier.name}</span>
                        <button
                          className="icon-button classifier-analyze-button"
                          title={rescoreTitle}
                          aria-label={rescoreTitle}
                          disabled={busy || Boolean(blockedReason)}
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
            ) : (
              <div className="empty-state classifier-empty-state">{classifierEmptyStateMessage}</div>
            )}
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

function HybridResultDetails({
  result,
  draft,
  saving,
  error,
  onRate,
  onToggleReason
}: {
  result: HybridSearchResult;
  draft: HybridFeedbackDraft;
  saving: boolean;
  error: string;
  onRate: (rating: PairFeedbackRating) => void;
  onToggleReason: (reasonTag: EvaluationPairReasonTag) => void;
}) {
  const topSources = hybridTopSources(result);
  const topAxes = hybridTopMatchAxes(result);
  return (
    <div className="hybrid-result-details" title="Selected Hybrid row details, feedback, source support, classifier support, and risk diagnostics.">
      <div className="hybrid-result-details-header">
        <strong>{displayTrack(result.track)}</strong>
        <span className="hybrid-result-summary-content">
          <span className="hybrid-summary-chip">Risk {formatOptionalUnitScore(result.transition_risk)}</span>
          {topSources.map(({ source, support }) => (
            <span className="hybrid-summary-chip active" key={source} title={hybridSourceSupportTitle(source, support)}>
              {source.toUpperCase()} {hybridSourceSupportLabel(support)}
            </span>
          ))}
          {topAxes.map(({ axis, value }) => (
            <span className="hybrid-summary-chip" key={axis}>
              {hybridAxisLabels[axis]} {value.toFixed(2)}
            </span>
          ))}
          <span className={`hybrid-feedback-state compact ${error ? "error" : ""}`}>
            {error || (saving ? "Saving feedback..." : hybridFeedbackStateText(draft))}
          </span>
        </span>
      </div>
      <div className="hybrid-row-diagnostics">
        <HybridWhyThisTrack result={result} />
        <HybridFeedbackControls
          draft={draft}
          saving={saving}
          error={error}
          onRate={onRate}
          onToggleReason={onToggleReason}
        />
      </div>
    </div>
  );
}

function HybridWhyThisTrack({ result }: { result: HybridSearchResult }) {
  const axes = hybridAxisOrder.map((axis) => ({ axis, value: clampNumber(result.match_character[axis], 0, 1) }));
  const sourceRows = hybridSourceKeys.map((source) => ({ source, support: result.source_support[source] }));
  const classifierRows = Object.entries(result.classifier_support || {}).filter(([, support]) => support.available);
  const riskRows = Object.entries(result.risk_breakdown).filter((entry): entry is [string, number] => typeof entry[1] === "number");
  const explanationLines = result.explanation.length ? result.explanation : ["Reason signals are unavailable for this row."];
  return (
    <div className="hybrid-why-panel" title="Unsupervised diagnostic. Adjusted score, reason signals, and risk estimate use stored analysis data only.">
      <div className="hybrid-why-header">
        <span>Why this track?</span>
        <em>Unsupervised diagnostic</em>
      </div>
      <div className="hybrid-score-summary">
        <span>Adjusted score {formatDiagnosticScore(result.total_score)}</span>
        <span>Risk estimate {formatOptionalUnitScore(result.transition_risk)}</span>
      </div>
      <ul className="hybrid-explanation-list">
        {explanationLines.slice(0, 3).map((line) => (
          <li key={line}>{line}</li>
        ))}
      </ul>
      <div className="hybrid-axis-grid" aria-label="Hybrid match character axes">
        {axes.map(({ axis, value }) => (
          <div className="hybrid-axis-row" key={axis}>
            <span>{hybridAxisLabels[axis]}</span>
            <div className="hybrid-axis-bar" aria-hidden="true"><i style={{ width: `${Math.round(value * 100)}%` }} /></div>
            <em>{value.toFixed(2)}</em>
          </div>
        ))}
      </div>
      <div className="hybrid-source-support" aria-label="Hybrid source support">
        {sourceRows.map(({ source, support }) => (
          <span className={support?.available ? "active" : ""} key={source} title={hybridSourceSupportTitle(source, support)}>
            {source.toUpperCase()} {hybridSourceSupportLabel(support)}
          </span>
        ))}
      </div>
      {classifierRows.length ? (
        <div className="hybrid-classifier-support" aria-label="Hybrid classifier support">
          {classifierRows.map(([classifierKey, support]) => (
            <span key={classifierKey} title={hybridClassifierSupportTitle(classifierKey, support)}>
              CLASS {support.label || classifierKey} {formatOptionalUnitScore(support.score)}
            </span>
          ))}
        </div>
      ) : null}
      {riskRows.length ? (
        <div className="hybrid-risk-breakdown" aria-label="Hybrid risk estimate components">
          {riskRows.map(([name, value]) => (
            <span key={name}>{name.replaceAll("_", " ")} {value.toFixed(2)}</span>
          ))}
        </div>
      ) : null}
      {result.warnings.length ? (
        <div className="hybrid-row-warning-list" aria-label="Hybrid row warnings">
          {result.warnings.slice(0, 3).map((warning) => (
            <span key={warning}>{warning}</span>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function HybridFeedbackControls({
  draft,
  saving,
  error,
  onRate,
  onToggleReason
}: {
  draft: HybridFeedbackDraft;
  saving: boolean;
  error: string;
  onRate: (rating: PairFeedbackRating) => void;
  onToggleReason: (reasonTag: EvaluationPairReasonTag) => void;
}) {
  return (
    <div className="hybrid-feedback-controls" title="Rate this Hybrid preview row for local evaluation only. Feedback updates SQLite labels and never writes audio files.">
      <div className="hybrid-feedback-rating-row" role="group" aria-label="Hybrid feedback rating">
        {hybridFeedbackRatings.map((rating) => (
          <button
            className={`hybrid-feedback-rating-button ${draft.rating === rating.value ? "active" : ""}`}
            key={rating.value}
            type="button"
            title={`Save Hybrid feedback rating: ${rating.label}`}
            disabled={saving}
            aria-pressed={draft.rating === rating.value}
            onClick={() => onRate(rating.value)}
          >
            {rating.label}
          </button>
        ))}
      </div>
      <div className="hybrid-feedback-tag-row" role="group" aria-label="Hybrid feedback reasons">
        {hybridFeedbackReasonTags.map((reasonTag) => (
          <button
            className={`hybrid-feedback-tag-button ${draft.reasonTags.includes(reasonTag.value) ? "active" : ""}`}
            key={reasonTag.value}
            type="button"
            title={`Toggle Hybrid feedback reason: ${reasonTag.label}`}
            disabled={saving}
            aria-pressed={draft.reasonTags.includes(reasonTag.value)}
            onClick={() => onToggleReason(reasonTag.value)}
          >
            {reasonTag.label}
          </button>
        ))}
      </div>
      <span className={`hybrid-feedback-state ${error ? "error" : ""}`}>
        {error || (saving ? "Saving feedback..." : hybridFeedbackStateText(draft))}
      </span>
    </div>
  );
}

function emptyHybridFeedbackDraft(): HybridFeedbackDraft {
  return { rating: null, reasonTags: [], status: "unrated" };
}

function hybridFeedbackDraftsFromResults(results: HybridSearchResult[]) {
  const drafts: Record<number, HybridFeedbackDraft> = {};
  for (const result of results) {
    drafts[result.track.id] = hybridFeedbackDraftFromState(result.feedback);
  }
  return drafts;
}

function hybridFeedbackDraftFromState(feedback?: EvaluationPairFeedbackState | null): HybridFeedbackDraft {
  if (!feedback) return emptyHybridFeedbackDraft();
  if (feedback.rating == null) return { rating: null, reasonTags: feedback.reason_tags || [], status: feedback.state };
  return { rating: feedback.rating, reasonTags: feedback.reason_tags || [], status: feedback.state };
}

function hybridFeedbackFromResponse(response: EvaluationPairFeedbackResult): EvaluationPairFeedbackState {
  return {
    state: "rated",
    source: response.source,
    seed_track_ids: response.seed_track_ids,
    candidate_track_id: response.candidate_track_id,
    rating: response.rating,
    reason_tags: response.reason_tags,
    notes: response.notes ?? null,
    per_seed: response.seed_track_ids.map((seedTrackId, index) => ({
      id: response.ids[index],
      seed_track_id: seedTrackId,
      candidate_track_id: response.candidate_track_id,
      rating: response.rating,
      reason_tags: response.reason_tags,
      notes: response.notes ?? null,
      source: response.source
    }))
  };
}

function toggleReasonTag(reasonTags: EvaluationPairReasonTag[], reasonTag: EvaluationPairReasonTag) {
  if (reasonTags.includes(reasonTag)) {
    return reasonTags.filter((current) => current !== reasonTag);
  }
  return [...reasonTags, reasonTag];
}

function hybridFeedbackStateText(draft: HybridFeedbackDraft) {
  if (draft.status === "mixed") return "Rated: Mixed feedback across seeds";
  if (draft.rating == null) return "Unrated";
  const ratingLabel = hybridFeedbackRatings.find((rating) => rating.value === draft.rating)?.label || String(draft.rating);
  const tagText = draft.reasonTags.length ? ` · ${draft.reasonTags.join(", ")}` : "";
  return `Rated: ${ratingLabel}${tagText}`;
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
  limit: number,
  transitionRiskWeight: number,
  useClassifierPreferences: boolean,
  classifierToggles: Record<string, boolean>,
  classifierOptions: HybridClassifierSignalOption[]
) {
  const sourceState = hybridSourceKeys.map((source) => `${source}:${sources[source] ? "1" : "0"}:${weights[source]}`).join("|");
  const classifierState = classifierOptions.map((option) => `${option.key}:${hybridClassifierToggleEnabled(classifierToggles, option) ? "1" : "0"}`).join("|");
  return `${seeds.join(",")}|${sourceState}|${perSource}|${limit}|risk:${transitionRiskWeight}|class:${useClassifierPreferences ? "1" : "0"}:${classifierState}`;
}

function hybridClassifierPreferences(toggles: Record<string, boolean>, classifierOptions: HybridClassifierSignalOption[]) {
  const preferences: Record<string, number> = {};
  for (const option of classifierOptions) {
    if (!hybridClassifierToggleEnabled(toggles, option) || !option.preference) continue;
    preferences[option.classifierKey] = option.preference;
  }
  return preferences;
}

function hybridClassifierRiskWeights(toggles: Record<string, boolean>, classifierOptions: HybridClassifierSignalOption[]) {
  const riskWeights: Record<string, number> = {};
  for (const option of classifierOptions) {
    if (!hybridClassifierToggleEnabled(toggles, option) || !option.riskWeight) continue;
    riskWeights[option.classifierKey] = option.riskWeight;
  }
  return riskWeights;
}

function hybridClassifierSignalOptions(classifiers: PromotedClassifier[]): HybridClassifierSignalOption[] {
  const options: HybridClassifierSignalOption[] = [];
  for (const classifier of classifiers) {
    const signal = classifier.hybrid_signal;
    if (!signal || !hybridSignalAllowsMode(signal, "hybrid")) continue;
    const label = signal.label || classifier.name || classifier.classifier_key;
    options.push({
      key: classifier.classifier_key,
      classifierKey: classifier.classifier_key,
      label,
      title: hybridClassifierSignalTitle(classifier, signal, label),
      role: signal.role || "context_modifier",
      axis: signal.axis || "novelty",
      enabledByDefault: signal.enabled_by_default === true,
      preference: hybridSignalPreference(signal),
      riskWeight: hybridSignalRiskWeight(signal)
    });
  }
  return options;
}

function hybridSignalAllowsMode(signal: HybridClassifierSignal, mode: string) {
  if (!signal.allowed_modes?.length) return true;
  return signal.allowed_modes.includes(mode);
}

function hybridSignalPreference(signal: HybridClassifierSignal) {
  if (signal.role === "risk_penalty") return undefined;
  if (typeof signal.default_preference === "number") return clampNumber(signal.default_preference, -1, 1);
  if (signal.role === "preference_penalty") return -0.6;
  if (signal.role === "preference_boost") return 0.6;
  return undefined;
}

function hybridSignalRiskWeight(signal: HybridClassifierSignal) {
  if (signal.role !== "risk_penalty") return undefined;
  if (typeof signal.default_risk_weight === "number") return clampNumber(signal.default_risk_weight, 0, 1);
  return 1.0;
}

function hybridClassifierToggleEnabled(toggles: Record<string, boolean>, option: HybridClassifierSignalOption) {
  return toggles[option.key] ?? option.enabledByDefault;
}

function hybridClassifierSignalTitle(classifier: PromotedClassifier, signal: HybridClassifierSignal, label: string) {
  const description = signal.description || `Uses stored ${classifier.classifier_key} classifier scores as a local Hybrid signal.`;
  const role = signal.role ? ` Role: ${signal.role.replaceAll("_", " ")}.` : "";
  const axis = signal.axis ? ` Axis: ${hybridAxisLabels[signal.axis as HybridMatchAxis] || String(signal.axis)}.` : "";
  const source = classifier.hybrid_signal_source ? ` Source: ${classifier.hybrid_signal_source.replaceAll("_", " ")}.` : "";
  return `${label}. ${description}${role}${axis}${source} Type: checkbox on/off. Missing scores stay neutral.`;
}

function formatHybridDiagnosticTitle(limitations: string[]) {
  const scoreDescription = "Preview score is adjusted weighted RRF. Risk penalty is an optional diagnostic transition estimate.";
  if (!limitations.length) return scoreDescription;
  return `${scoreDescription} ${limitations.join(" ")}`;
}

function hybridReason(result: HybridSearchResult) {
  const sourceCount = hybridAvailableSourceCount(result);
  if (typeof result.transition_risk !== "number") return `weighted_preview_${sourceCount}_sources`;
  return `weighted_preview_${sourceCount}_sources · risk ${result.transition_risk.toFixed(2)}`;
}

function hybridScoreBreakdown(result: HybridSearchResult) {
  const sourceCount = hybridAvailableSourceCount(result);
  const breakdown: Record<string, number> = {
    total_score: result.total_score,
    adjusted_score: result.adjusted_score,
    raw_rrf_score: result.raw_rrf_score,
    transition_risk: typeof result.transition_risk === "number" ? result.transition_risk : 0,
    transition_risk_penalty: result.transition_risk_penalty,
    transition_risk_weight: result.transition_risk_weight,
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

function hybridAvailableSourceCount(result: HybridSearchResult) {
  const sourceSupport = result.source_support || {};
  const availableSources = Object.values(sourceSupport).filter((support) => support.available).length;
  return availableSources || Object.keys(result.score_breakdown).length;
}

function hybridTopSources(result: HybridSearchResult) {
  return hybridSourceKeys
    .map((source) => ({ source, support: result.source_support[source] }))
    .filter(({ support }) => support?.available)
    .sort((left, right) => {
      const leftRank = typeof left.support.rank === "number" ? left.support.rank : Number.POSITIVE_INFINITY;
      const rightRank = typeof right.support.rank === "number" ? right.support.rank : Number.POSITIVE_INFINITY;
      if (leftRank !== rightRank) return leftRank - rightRank;
      const leftScore = typeof left.support.score === "number" ? left.support.score : -1;
      const rightScore = typeof right.support.score === "number" ? right.support.score : -1;
      return rightScore - leftScore;
    })
    .slice(0, 2);
}

function hybridTopMatchAxes(result: HybridSearchResult) {
  return hybridAxisOrder
    .map((axis) => ({ axis, value: clampNumber(result.match_character[axis], 0, 1) }))
    .sort((left, right) => right.value - left.value)
    .slice(0, 2);
}

function formatUnitScore(value: number) {
  return clampNumber(value, 0, 1).toFixed(2);
}

function formatDiagnosticScore(value: number) {
  return Number.isFinite(value) ? value.toFixed(2) : "unavailable";
}

function formatOptionalUnitScore(value?: number | null) {
  return typeof value === "number" ? formatUnitScore(value) : "unavailable";
}

function hybridSourceSupportLabel(support?: HybridSearchResult["source_support"][string]) {
  if (!support?.available) return "unavailable";
  if (typeof support.rank === "number") return `rank ${support.rank}`;
  return "available";
}

function hybridSourceSupportTitle(source: HybridSearchSource, support?: HybridSearchResult["source_support"][string]) {
  if (!support?.available) return `${source.toUpperCase()} source unavailable for this row; missing data stays neutral.`;
  const score = typeof support.score === "number" ? ` score ${support.score.toFixed(3)}` : "";
  const seeds = support.supporting_seed_track_ids?.length ? ` seeds ${support.supporting_seed_track_ids.join(", ")}` : "";
  return `${source.toUpperCase()} source support: ${hybridSourceSupportLabel(support)}${score}${seeds}.`;
}

function hybridClassifierSupportTitle(classifierKey: string, support: HybridSearchResult["classifier_support"][string]) {
  const label = support.label || classifierKey;
  const role = support.role ? ` role ${String(support.role).replaceAll("_", " ")}` : "";
  const axis = support.axis ? ` axis ${String(support.axis).replaceAll("_", " ")}` : "";
  const status = support.production_status || support.manifest_status ? ` status ${support.production_status || support.manifest_status}` : "";
  const stale = support.stale ? " stale stored score" : support.fresh ? " fresh stored score" : "";
  const preference = typeof support.preference === "number" && support.preference !== 0 ? ` preference ${formatSigned(support.preference)}` : "";
  const contribution = typeof support.score_contribution === "number" && support.score_contribution !== 0 ? ` score contribution ${formatSigned(support.score_contribution)}` : "";
  const risk = typeof support.risk_contribution === "number" ? ` risk contribution ${support.risk_contribution.toFixed(2)}` : "";
  return `Classifier ${label}: stored score ${formatOptionalUnitScore(support.score)}.${role}${axis}${status}${stale}${preference}${contribution}${risk}`;
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
