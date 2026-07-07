import { Check, ListFilter, Search } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type { ClapPromptPreset } from "./clapPrompt";

export function ClapSearchTab({
  textQuery,
  onTextQueryChange,
  clapNegativeQuery,
  onClapNegativeQueryChange,
  clapUseNegativePrompt,
  onClapUseNegativePromptChange,
  clapPresetKey,
  onClapPresetChange,
  clapPromptPresets,
  clapMinSimilarity,
  onClapMinSimilarityChange,
  limit,
  onLimitChange,
  textPromptHelp,
  clapSimilarityHelp,
  limitHelp,
  hasStoredClapEmbeddings,
  busy,
  clapSearchTitle,
  handleTextSearch
}: {
  textQuery: string;
  onTextQueryChange: (value: string) => void;
  clapNegativeQuery: string;
  onClapNegativeQueryChange: (value: string) => void;
  clapUseNegativePrompt: boolean;
  onClapUseNegativePromptChange: (value: boolean) => void;
  clapPresetKey: string;
  onClapPresetChange: (value: string) => void;
  clapPromptPresets: ClapPromptPreset[];
  clapMinSimilarity: number;
  onClapMinSimilarityChange: (value: number) => void;
  limit: number;
  onLimitChange: (value: number) => void;
  textPromptHelp: string;
  clapSimilarityHelp: string;
  limitHelp: string;
  hasStoredClapEmbeddings: boolean;
  busy: boolean;
  clapSearchTitle: string;
  handleTextSearch: () => void;
}) {
  const [clapPresetMenuOpen, setClapPresetMenuOpen] = useState(false);
  const clapPresetMenuRef = useRef<HTMLDivElement>(null);

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

  function applyClapPromptPreset(preset: ClapPromptPreset) {
    onClapPresetChange(preset.key);
    onTextQueryChange(preset.query);
    onClapNegativeQueryChange(preset.negativeQuery);
    setClapPresetMenuOpen(false);
  }

  return (
    <div className="search-tab-panel" role="tabpanel">
      <div className="text-search-box clap-text-search-box">
        <div className="clap-prompt-row">
          <label className="clap-query-field" title={textPromptHelp}>
            Text query
            <textarea
              value={textQuery}
              onChange={(event) => onTextQueryChange(event.target.value)}
              placeholder={"breakbeat.\nThis audio is a breakbeat track.\nA breakbeat track with broken drums and syncopated percussion."}
              title={textPromptHelp}
              rows={5}
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
        <div className="clap-negative-row">
          <label className="clap-negative-field" title="Hard-negative CLAP bank. Type: multiline text. One line is one unwanted audible class; presets fill this field directly.">
            Negative
            <textarea
              className="clap-negative-input"
              value={clapNegativeQuery}
              onChange={(event) => onClapNegativeQueryChange(event.target.value)}
              placeholder={"This audio is a vocal pop song.\nThis audio is a straight four-on-the-floor house track."}
              title="Hard-negative CLAP bank. Type: multiline text. One line is one unwanted audible class; presets fill this field directly."
              disabled={!clapUseNegativePrompt}
              rows={4}
            />
          </label>
          <label className={`icon-button add-visible-tracks-button clap-negative-toggle ${clapUseNegativePrompt ? "intent-add active" : ""}`} title="Apply Negative as hard-negative CLAP queries. Type: checkbox on/off. When disabled, the text stays in the field but is not included in search.">
            <input
              type="checkbox"
              aria-label="Use negative prompt"
              checked={clapUseNegativePrompt}
              onChange={(event) => onClapUseNegativePromptChange(event.target.checked)}
            />
            <span className="clap-negative-checkbox" aria-hidden="true">
              {clapUseNegativePrompt ? <Check size={14} strokeWidth={2.4} /> : null}
            </span>
          </label>
        </div>
      </div>
      <div className="search-filter-grid">
        <label title={clapSimilarityHelp}>Similarity<input type="number" value={clapMinSimilarity} min={0} max={1} step={0.01} title={clapSimilarityHelp} onChange={(event) => onClapMinSimilarityChange(Number(event.target.value))} /></label>
        <label title={limitHelp}>Limit<input type="number" value={limit} min={1} max={500} title={limitHelp} onChange={(event) => onLimitChange(Number(event.target.value))} /></label>
      </div>
      <button className="clap-text-search-button" title={clapSearchTitle} disabled={busy || !textQuery.trim() || !hasStoredClapEmbeddings} onClick={handleTextSearch} type="button">
        <Search size={17} />
        CLAP search
      </button>
      {!hasStoredClapEmbeddings ? <span className="clap-search-requirement">Requires stored CLAP embeddings. Run CLAP analysis first.</span> : null}
    </div>
  );
}
