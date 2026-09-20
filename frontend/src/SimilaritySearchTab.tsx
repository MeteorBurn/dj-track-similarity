import { Search, Shuffle } from "lucide-react";
import type { Dispatch, SetStateAction } from "react";
import type { SonaraMixerWeights, SonaraModifiers } from "./api";
import type { SearchFiltersState, SearchHelpText } from "./SearchPlaylistPanel";
import { MertV2LayerSelect } from "./MertV2LayerSelect";
import type { MertV2LayerState } from "./useMertV2Layers";
import {
  seedSearchModels,
  seedSearchModelPresentation,
  type SeedSearchModel
} from "./searchSurfaceState";

export function SimilaritySearchTab({
  layerState,
  model,
  onModelChange,
  currentAnalysisCount,
  busy,
  randomTrackBusy,
  pending,
  error,
  filters,
  setFilters,
  helpText,
  onSearch,
  onAddRandomTrack
}: {
  layerState: MertV2LayerState;
  model: SeedSearchModel;
  onModelChange: (value: SeedSearchModel) => void;
  currentAnalysisCount: number;
  busy: boolean;
  randomTrackBusy: boolean;
  pending: boolean;
  error: string;
  filters: SearchFiltersState;
  setFilters: Dispatch<SetStateAction<SearchFiltersState>>;
  helpText: SearchHelpText;
  onSearch: () => void;
  onAddRandomTrack: () => void;
}) {
  const { label, title, description } = seedSearchModelPresentation[model];
  const showSonara = model === "sonara";
  const missingReason = model === "mert_v2" && layerState.loading
    ? "Loading MERT-v2 layer coverage…"
    : model === "mert_v2" && layerState.error
      ? layerState.error
      : currentAnalysisCount > 0
        ? ""
        : showSonara
          ? "No SONARA analysis is available in the selected catalog. Run SONARA analysis first."
          : `No current ${label}${model === "mert_v2" ? ` L${layerState.layer}` : ""} embeddings are available in the selected catalog. Run ${label} analysis first.`;
  const requestTitle = missingReason || (showSonara
    ? "Найти похожие треки через SONARA по выбранным seed-трекам"
    : `Find acoustically similar tracks with current ${label} embeddings.`);
  const randomTrackTitle = missingReason || (showSonara
    ? "Добавить случайный SONARA-ready трек из базы в seed"
    : `Add a random track with a current ${label} embedding as a seed.`);
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

  function setSonaraMixerValue(key: keyof SonaraMixerWeights, value: number) {
    setFilters((current) => ({ ...current, sonaraMixer: { ...current.sonaraMixer, [key]: value } }));
  }

  function setSonaraModifierValue(key: keyof SonaraModifiers, value: number) {
    setFilters((current) => ({ ...current, sonaraModifiers: { ...current.sonaraModifiers, [key]: value } }));
  }

  function resetSonaraControls() {
    setFilters((current) => ({
      ...current,
      sonaraMixer: { timbre: 1, rhythm: 1, dynamics: 0.8, harmonic: 0.8, tempo: 0.35 },
      sonaraModifiers: { energy: 0, valence: 0, acousticness: 0, brightness: 0, rhythm_density: 0, dynamic_range: 0, loudness: 0, vocalness: 0, aggression: 0 }
    }));
  }

  return (
    <>
      <div className="search-filter-grid similarity-search-controls">
        <button
          className="embedding-random-track-button"
          title={randomTrackTitle}
          disabled={randomTrackBusy || Boolean(missingReason)}
          onClick={onAddRandomTrack}
          type="button"
        >
          <Shuffle size={15} />
          <span>Add Random Track</span>
        </button>
        <label>
          Model
          <select
            className="embedding-model-select"
            name="seed-search-model"
            value={model}
            title={title}
            aria-describedby="seed-search-model-description"
            onChange={(event) => onModelChange(event.target.value as SeedSearchModel)}
          >
            {seedSearchModels.map((source) => (
              <option key={source} value={source} title={seedSearchModelPresentation[source].title}>
                {seedSearchModelPresentation[source].label.toUpperCase()}
              </option>
            ))}
          </select>
        </label>
        <label className="search-limit-control" title={helpText.limit}>
          Limit
          <input
            name="seed-search-limit"
            type="number"
            value={filters.limit}
            min={1}
            max={500}
            title={helpText.limit}
            onChange={(event) => {
              if (Number.isFinite(event.currentTarget.valueAsNumber)) {
                const limit = Math.round(Math.max(1, Math.min(500, event.currentTarget.valueAsNumber)));
                setFilters((current) => ({ ...current, limit }));
              }
            }}
          />
        </label>
      </div>
      {model === "mert_v2" ? <MertV2LayerSelect state={layerState} /> : null}
      <small id="seed-search-model-description" className="embedding-search-requirement">{description}</small>
      {showSonara ? (
        <div className="sonara-search-settings">
          <div className="custom-control-header">
            <div className="custom-control-copy">
              <span>Mixer</span>
              <small>— приоритизирует виды сходства.</small>
            </div>
            <button className="sonara-mixer-reset-button" title="Сбросить SONARA mixer и modifiers" type="button" onClick={resetSonaraControls}>Reset</button>
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
                    name={`sonara-mixer-${control.key}`}
                    type="range"
                    min={0}
                    max={5}
                    step={0.05}
                    value={value}
                    title={control.title}
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
                      disabled={isOff}
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
                    onChange={(event) => setSonaraModifierValue(control.key, Number(event.target.value))}
                  />
                </div>
              );
            })}
          </div>
        </div>
      ) : null}
      <button
        className="embedding-search-button"
        title={requestTitle}
        disabled={busy || pending || Boolean(missingReason)}
        onClick={onSearch}
        type="button"
      >
        <Search size={17} />
        {pending ? "Searching..." : "Search"}
      </button>
      {missingReason ? <span className="embedding-search-requirement">{missingReason}</span> : null}
      {error ? <span className="embedding-search-requirement error">{error}</span> : null}
    </>
  );
}

function formatSigned(value: number) {
  if (value === 0) return "0.00";
  return `${value > 0 ? "+" : ""}${value.toFixed(2)}`;
}
