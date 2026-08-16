import { Check, ListFilter, Search } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type { EmbeddingSource } from "./api";
import type { ClapPromptPreset } from "./clapPrompt";

export function ClapSearchTab({
  textQuery,
  onTextQueryChange,
  clapNegativeQuery,
  onClapNegativeQueryChange,
  clapUseNegativePrompt,
  onClapUseNegativePromptChange,
  textEmbeddingFamily,
  onTextEmbeddingFamilyChange,
  clapPresetKey,
  onClapPresetChange,
  clapPromptPresets,
  limit,
  onLimitChange,
  textPromptHelp,
  limitHelp,
  hasStoredTextEmbeddings,
  busy,
  textSearchTitle,
  handleTextSearch
}: {
  textQuery: string;
  onTextQueryChange: (value: string) => void;
  clapNegativeQuery: string;
  onClapNegativeQueryChange: (value: string) => void;
  clapUseNegativePrompt: boolean;
  onClapUseNegativePromptChange: (value: boolean) => void;
  textEmbeddingFamily: Extract<EmbeddingSource, "clap" | "mulan">;
  onTextEmbeddingFamilyChange: (value: Extract<EmbeddingSource, "clap" | "mulan">) => void;
  clapPresetKey: string;
  onClapPresetChange: (value: string) => void;
  clapPromptPresets: ClapPromptPreset[];
  limit: number;
  onLimitChange: (value: number) => void;
  textPromptHelp: string;
  limitHelp: string;
  hasStoredTextEmbeddings: boolean;
  busy: boolean;
  textSearchTitle: string;
  handleTextSearch: () => void;
}) {
  const [clapPresetMenuOpen, setClapPresetMenuOpen] = useState(false);
  const clapPresetMenuRef = useRef<HTMLDivElement>(null);
  const textModelLabel = textEmbeddingFamily === "mulan" ? "MuQ-MuLan" : "CLAP";

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
    onTextQueryChange(preset.query.replace(/\s*[\r\n]+\s*/g, " "));
    onClapNegativeQueryChange(preset.negativeQuery.replace(/\s*[\r\n]+\s*/g, " "));
    setClapPresetMenuOpen(false);
  }

  return (
    <div className="search-tab-panel" role="tabpanel">
      <div className="text-search-box clap-text-search-box">
        <div className="clap-prompt-row">
          <label className="clap-query-field" title={textPromptHelp}>
            Text query
            <input
              type="text"
              value={textQuery}
              onChange={(event) => onTextQueryChange(event.target.value)}
              placeholder="Breakbeat with broken drums and syncopated percussion"
              title={textPromptHelp}
            />
          </label>
          <div className="clap-prompt-actions" ref={clapPresetMenuRef}>
            <button
              className={`icon-button folder-picker clap-presets-button ${clapPresetMenuOpen ? "active" : ""}`}
              title="Выбрать prompt preset"
              aria-label="Выбрать prompt preset"
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
          <label className="clap-negative-field" title="Hard-negative text description. Type: text. Presets fill this field directly.">
            Negative
            <input
              type="text"
              className="clap-negative-input"
              value={clapNegativeQuery}
              onChange={(event) => onClapNegativeQueryChange(event.target.value)}
              placeholder="Vocal pop song or straight four-on-the-floor house track"
              title="Hard-negative text description. Type: text. Presets fill this field directly."
              disabled={!clapUseNegativePrompt}
            />
          </label>
          <label className={`icon-button add-visible-tracks-button clap-negative-toggle ${clapUseNegativePrompt ? "intent-add active" : ""}`} title="Apply Negative as hard-negative text queries. Type: checkbox on/off. When disabled, the text stays in the field but is not included in search.">
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
      <div className="search-filter-grid clap-search-filter-grid">
        <label title="Embedding family used for text-to-track retrieval">Model
          <select
            value={textEmbeddingFamily}
            onChange={(event) => onTextEmbeddingFamilyChange(event.target.value as Extract<EmbeddingSource, "clap" | "mulan">)}
          >
            <option value="clap">CLAP</option>
            <option value="mulan">MuQ-MuLan</option>
          </select>
        </label>
        <label title={limitHelp}>Limit<input type="number" value={limit} min={1} max={500} title={limitHelp} onChange={(event) => onLimitChange(Number(event.target.value))} /></label>
      </div>
      <button className="clap-text-search-button" title={textSearchTitle} disabled={busy || !textQuery.trim() || !hasStoredTextEmbeddings} onClick={handleTextSearch} type="button">
        <Search size={17} />
        {textModelLabel} search
      </button>
      {!hasStoredTextEmbeddings ? <span className="clap-search-requirement">Requires stored {textModelLabel} embeddings. Run {textModelLabel} analysis first.</span> : null}
    </div>
  );
}
