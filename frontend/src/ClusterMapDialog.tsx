import { CircleAlert, Pause, Play, Star, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import type {
  ClusterMapFeatureValue,
  ClusterMapPoint,
  ClusterMapResponse,
  EmbeddingLayersResponse,
  Track,
} from "./api";
import { ClusterMapPlot, OrbitSkeleton } from "./ClusterMapPlot";
import { seedSearchModelPresentation, tabAfterKey } from "./searchSurfaceState";
import { formatSonaraCoreValue, sonaraCoreFeatureGroups } from "./TrackMetadataDialog";
import { displayTrack } from "./trackDisplay";
import type { ClusterMapEntry } from "./useClusterMap";
import type { EmbeddingLayerState } from "./useEmbeddingLayers";

type RailTab = "tracks" | "layer";
type LayerRow = EmbeddingLayersResponse["layers"][number];
type Candidate = { point: ClusterMapPoint; rank: number };
type MapView = {
  seeds: ClusterMapPoint[];
  candidates: Candidate[];
  /** Both in search order, so the first exception is the one nearest the core. */
  exceptions: Candidate[];
  swarm: Candidate[];
  medianSimilarity: number;
};

const railTabs: readonly RailTab[] = ["tracks", "layer"];
const DRIFT_SHOWN = 5;
// SONARA labels that name a component rather than a feature read under their group title.
const groupScopedLabels = new Set(["Score", "Rhythm", "Level"]);
const FOCUSABLE = [
  "button:not([disabled]):not([tabindex='-1'])",
  "summary",
  "[href]",
  "input:not([disabled])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  "[tabindex]:not([tabindex='-1'])",
].join(", ");

/** The cluster map of one REFERENCE search. It stays mounted while its build is
 * cached, so a closed map keeps its zoom and tab. */
export function ClusterMapDialog({
  entry,
  open,
  layerState,
  playingTrackId,
  onPreview,
  onClose,
  onRetry,
}: {
  entry: ClusterMapEntry;
  open: boolean;
  layerState: EmbeddingLayerState;
  playingTrackId: number | null;
  onPreview: (track: Track) => void;
  onClose: () => void;
  onRetry: () => void;
}) {
  const sectionRef = useRef<HTMLElement | null>(null);
  const pressedOnBackdrop = useRef(false);
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;
  const [tab, setTab] = useState<RailTab>("tracks");
  const { payload, response } = entry;
  const view = useMemo(() => (response ? mapView(response) : null), [response]);
  const layer = payload.layer ?? null;
  const subject = layer !== null ? "layer" : "model";
  const layerRow = layer === null ? null : layerState.layers?.find((row) => row.layer === layer) ?? null;
  const seedCount = payload.seed_track_ids.length;
  const summary = view
    ? [
      plural(seedCount, "reference track"),
      plural(view.candidates.length, "candidate"),
      `median similarity ${view.medianSimilarity.toFixed(3)}`,
    ].join(" · ")
    : `${plural(seedCount, "reference track")} · up to ${plural(payload.limit, "candidate")}`;

  useEffect(() => {
    if (!open) return undefined;
    sectionRef.current?.focus({ preventScroll: true });
    const closeOnEscape = (event: globalThis.KeyboardEvent) => {
      if (event.key !== "Escape") return;
      event.preventDefault();
      requestClose();
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [open]);

  function requestClose() {
    const active = document.activeElement;
    const restoreFocus = !active || active === document.body || Boolean(sectionRef.current?.contains(active));
    onCloseRef.current();
    if (restoreFocus) document.getElementById("cluster-map-button")?.focus();
  }

  function keepFocusInside(event: KeyboardEvent<HTMLElement>) {
    if (event.key !== "Tab") return;
    const section = event.currentTarget;
    const focusable = [...section.querySelectorAll<HTMLElement>(FOCUSABLE)]
      .filter((element) => element.getClientRects().length > 0);
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (!first || !last) {
      event.preventDefault();
      return;
    }
    const active = document.activeElement;
    if (event.shiftKey && (active === first || active === section)) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && active === last) {
      event.preventDefault();
      first.focus();
    }
  }

  function selectTabByKey(event: KeyboardEvent<HTMLButtonElement>) {
    const target = tabAfterKey(railTabs, tab, event.key);
    if (!target) return;
    event.preventDefault();
    setTab(target);
    document.getElementById(`cluster-map-tab-${target}`)?.focus();
  }

  return (
    <div
      className="cluster-map-backdrop"
      role="presentation"
      data-open={open ? "true" : "false"}
      inert={!open}
      onPointerDown={(event) => {
        pressedOnBackdrop.current = event.target === event.currentTarget;
      }}
      onClick={(event) => {
        // A pan or selection that merely ends on the backdrop must not close the map.
        const fromBackdrop = pressedOnBackdrop.current && event.target === event.currentTarget;
        pressedOnBackdrop.current = false;
        if (fromBackdrop) requestClose();
      }}
    >
      <section
        ref={sectionRef}
        className="cluster-map-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="cluster-map-title"
        aria-describedby="cluster-map-summary"
        aria-busy={entry.status === "loading" || undefined}
        tabIndex={-1}
        onKeyDown={keepFocusInside}
      >
        <header className="cluster-map-header">
          <div className="cluster-map-heading">
            <h2 id="cluster-map-title">Cluster map</h2>
            <span className="cluster-map-chip">{seedSearchModelPresentation[payload.analysis_family].label}</span>
            {layer !== null ? (
              <span className="cluster-map-chip" title={[layerRow?.source, layerState.note].filter(Boolean).join("\n") || undefined}>
                L{layer}{layerState.layers ? ` / ${layerState.layers.length}` : ""}
              </span>
            ) : null}
            {layerRow?.label ? <span className="cluster-map-layer-hint">{layerRow.label}</span> : null}
          </div>
          <p id="cluster-map-summary" className="cluster-map-summary">{summary}</p>
          <button className="icon-button cluster-map-close-button" type="button" title="Закрыть" aria-label="Закрыть" onClick={requestClose}>
            <X size={16} />
          </button>
        </header>
        {entry.status === "loading" ? (
          <div className="cluster-map-body">
            <p className="cluster-map-status" role="status">Building the cluster map…</p>
            <div className="cluster-map-kpis" aria-hidden="true">
              {[0, 1].map((tile) => (
                <div key={tile} className="cluster-map-kpi">
                  <span className="cluster-map-skeleton-line" />
                  <span className="cluster-map-skeleton-line is-value" />
                </div>
              ))}
            </div>
            <div className="cluster-map-main" aria-hidden="true">
              <div className="cluster-map-figure">
                <div className="cluster-map-plot-frame"><OrbitSkeleton /></div>
              </div>
              <div className="cluster-map-rail">
                {[0, 1, 2].map((card) => (
                  <div key={card} className="cluster-map-card">
                    <span className="cluster-map-skeleton-line" />
                    <span className="cluster-map-skeleton-line is-wide" />
                    <span className="cluster-map-skeleton-line is-wide" />
                  </div>
                ))}
              </div>
            </div>
          </div>
        ) : entry.status === "error" ? (
          <div className="cluster-map-body">
            <div className="cluster-map-error" role="alert">
              <CircleAlert size={18} aria-hidden="true" />
              <div>
                <strong>Could not build the cluster map</strong>
                <p>{entry.error}</p>
              </div>
              <button type="button" title="Build the cluster map again" onClick={onRetry}>Retry</button>
            </div>
          </div>
        ) : response && view ? (
          <div className="cluster-map-body">
            <KpiRow view={view} subject={subject} />
            <div className="cluster-map-main">
              <figure className="cluster-map-figure">
                <figcaption>
                  Candidates orbit the reference core: the closer a point, the more similar the {subject} finds the track.
                  Tracks that differ from the reference the same way form one swarm; an exception is a track the {subject} pulls
                  in for another reason. Click a point to preview it.
                </figcaption>
                <ClusterMapPlot
                  mapKey={entry.key}
                  points={response.points}
                  center={response.candidates_center}
                  playingTrackId={playingTrackId}
                  reasonText={reasonText}
                  onPreview={onPreview}
                />
                <div className="cluster-map-legend">
                  <span className="cluster-map-key">
                    <span className="cluster-map-swatch is-swarm" aria-hidden="true" />
                    Swarm · {view.swarm.length}
                  </span>
                  <span className="cluster-map-key" title={`Candidates that do not fit in with the rest in the ${subject}'s space (LocalOutlierFactor)`}>
                    <span className="cluster-map-key-exception" aria-hidden="true" />
                    Exceptions · {view.exceptions.length}
                  </span>
                  <span className="cluster-map-key">
                    <span className="cluster-map-key-core" aria-hidden="true" />
                    Core · {view.seeds.length}
                  </span>
                  <span className="cluster-map-key" title="The candidates' centre of mass; its distance from the core shows how far the search drifts">
                    <Star className="cluster-map-key-center" size={12} aria-hidden="true" />
                    Candidates center · {response.candidates_center.similarity.toFixed(3)}
                  </span>
                </div>
              </figure>
              <aside className="cluster-map-rail" aria-label="Map details">
                <div className="search-tabs cluster-map-tabs" role="tablist" aria-label="Detail views">
                  {railTabs.map((name) => (
                    <button
                      key={name}
                      id={`cluster-map-tab-${name}`}
                      className={`model-search-tab ${tab === name ? "active" : ""}`}
                      title={railTabTitle(name, subject)}
                      role="tab"
                      aria-selected={tab === name}
                      aria-controls={`cluster-map-panel-${name}`}
                      tabIndex={tab === name ? 0 : -1}
                      type="button"
                      onClick={() => setTab(name)}
                      onKeyDown={selectTabByKey}
                    >
                      {name === "tracks" ? "Tracks" : layer !== null ? "Layer" : "Model"}
                    </button>
                  ))}
                </div>
                <div
                  id={`cluster-map-panel-${tab}`}
                  className="cluster-map-tab-panel"
                  role="tabpanel"
                  aria-labelledby={`cluster-map-tab-${tab}`}
                >
                  {tab === "tracks" ? (
                    <TracksPanel view={view} subject={subject} playingTrackId={playingTrackId} onPreview={onPreview} />
                  ) : (
                    <LayerPanel response={response} layer={layer} layerRow={layerRow} note={layerState.note} />
                  )}
                </div>
              </aside>
            </div>
          </div>
        ) : null}
        <footer className="cluster-map-footer">Scores rank candidates; the final pick is made by ear.</footer>
      </section>
    </div>
  );
}

function KpiRow({ view, subject }: { view: MapView; subject: string }) {
  const nearest = view.exceptions[0];
  return (
    <dl className="cluster-map-kpis">
      <div className="cluster-map-kpi">
        <dt>Exceptions</dt>
        <dd className="cluster-map-kpi-value">{view.exceptions.length}</dd>
        <dd className="cluster-map-kpi-note">
          of {plural(view.candidates.length, "candidate")}, apart from the swarm in the {subject}'s space
        </dd>
      </div>
      <div className="cluster-map-kpi">
        <dt>Nearest exception</dt>
        <dd className="cluster-map-kpi-value">{nearest ? `#${nearest.rank}` : "—"}</dd>
        <dd className="cluster-map-kpi-note">
          {nearest ? "its place in the search: the lower, the nearer the core" : "every candidate fits the swarm"}
        </dd>
      </div>
    </dl>
  );
}

function TracksPanel({ view, subject, playingTrackId, onPreview }: {
  view: MapView;
  subject: string;
  playingTrackId: number | null;
  onPreview: (track: Track) => void;
}) {
  return (
    <>
      <article className="cluster-map-card cluster-map-core-card">
        <header className="cluster-map-card-head">
          <span className="cluster-map-key-core" aria-hidden="true" />
          <h3>Core</h3>
          <span className="cluster-map-card-meta">{plural(view.seeds.length, "reference track")}</span>
        </header>
        <TrackList
          items={view.seeds.map((point) => ({ point, meta: `${point.similarity.toFixed(3)} to core` }))}
          playingTrackId={playingTrackId}
          onPreview={onPreview}
        />
      </article>
      <section className="cluster-map-list">
        <h3>Exceptions · {view.exceptions.length}</h3>
        <p className="cluster-map-prose">
          {view.exceptions.length
            ? `Tracks the ${subject} pulls toward the references for another reason than the swarm. Listen to them first: if they are wrong, the ${subject} misses what you are after.`
            : "Every candidate fits the swarm."}
        </p>
        {view.exceptions.length ? (
          <CandidateList items={view.exceptions} playingTrackId={playingTrackId} onPreview={onPreview} />
        ) : null}
      </section>
      <section className="cluster-map-list">
        <h3>Swarm · {view.swarm.length}</h3>
        <CandidateList items={view.swarm} playingTrackId={playingTrackId} onPreview={onPreview} />
      </section>
    </>
  );
}

function CandidateList({ items, playingTrackId, onPreview }: {
  items: Candidate[];
  playingTrackId: number | null;
  onPreview: (track: Track) => void;
}) {
  return (
    <ul className="cluster-map-anomalies">
      {items.map(({ point, rank }) => {
        const name = displayTrack(point.track);
        return (
          <li key={point.track.track_id} className="cluster-map-anomaly">
            <PlayButton track={point.track} playingTrackId={playingTrackId} onPreview={onPreview} />
            <div className="cluster-map-anomaly-title">
              <strong title={name}>{name}</strong>
              <span className="cluster-map-anomaly-meta">#{rank} · {point.similarity.toFixed(3)}</span>
            </div>
            <div className="cluster-map-reasons">
              {point.sonara_gaps.map((item) => (
                <span
                  key={item.group}
                  className="cluster-map-reason"
                  title="SONARA: this group's widest gap from the references' mean, in library σ"
                >
                  {reasonText(item)}
                </span>
              ))}
            </div>
          </li>
        );
      })}
    </ul>
  );
}

function LayerPanel({ response, layer, layerRow, note }: {
  response: ClusterMapResponse;
  layer: number | null;
  layerRow: LayerRow | null;
  note: string | null;
}) {
  const subject = layer !== null ? "layer" : "model";
  const widest = Math.max(...response.profile.map((spread) => spread.std), 1e-9);
  // The drift runs from the largest shift down, so a group's first entry is its largest.
  const drift = response.drift.filter((item, index, all) => all.findIndex((other) => other.group === item.group) === index);
  return (
    <div className="cluster-map-layer">
      {layer !== null ? (
        <div className="cluster-map-layer-about">
          <h3>L{layer}{layerRow?.label ? ` · ${layerRow.label}` : ""}</h3>
          {layerRow?.source ? <p className="cluster-map-prose">{layerRow.source}</p> : null}
          {note ? <p className="cluster-map-prose">{note}</p> : null}
        </div>
      ) : null}
      <div className="cluster-map-focus">
        <h3>What the {subject} holds</h3>
        <p className="cluster-map-prose">
          The spread of each SONARA group across the candidates, in library σ. The {subject} holds the group with the
          smallest spread and lets the one with the largest vary.
        </p>
        {response.profile.map((spread, position) => (
          <div
            key={spread.group}
            className="cluster-map-focus-row"
            data-holds={position === 0 || undefined}
            title={`${groupLabel(spread.group)}: std ${spread.std.toFixed(2)}`}
          >
            <span className="cluster-map-focus-label">{groupLabel(spread.group)}</span>
            <span className="cluster-map-focus-track">
              <span className="cluster-map-focus-bar" style={{ left: 0, width: `${(spread.std / widest) * 100}%` }} />
            </span>
            <span className="cluster-map-focus-value">{spread.std.toFixed(2)}</span>
          </div>
        ))}
      </div>
      <div className="cluster-map-focus">
        <h3>Drift from the references</h3>
        <p className="cluster-map-prose">
          The candidates' mean minus the references' mean, in library σ: where this {subject} pulls the search.
          Each SONARA group shows its largest shift.
        </p>
        <div className="cluster-map-reasons">
          {drift.slice(0, DRIFT_SHOWN).map((item) => (
            <span key={item.group} className="cluster-map-reason">
              {`${featureName(item)} ${signed(item.delta, 2)}σ`}
            </span>
          ))}
        </div>
      </div>
      <p className="cluster-map-prose">
        Distance from the centre is exact (1 − similarity to the core); the angle only approximates the direction of
        difference and keeps {Math.round(response.angle_variance_kept * 100)}% of it.
      </p>
      <p className="cluster-map-prose">
        Each map covers one model and layer; switch Model or Layer in the panel and open the map again to compare.
      </p>
    </div>
  );
}

function TrackList({ items, playingTrackId, onPreview }: {
  items: { point: ClusterMapPoint; meta: string }[];
  playingTrackId: number | null;
  onPreview: (track: Track) => void;
}) {
  return (
    <ul className="cluster-map-track-list">
      {items.map(({ point, meta }) => {
        const name = displayTrack(point.track);
        return (
          <li key={point.track.track_id}>
            <div className="cluster-map-track">
              <PlayButton track={point.track} playingTrackId={playingTrackId} onPreview={onPreview} />
              <span className="cluster-map-track-name" title={name}>{name}</span>
              <span className="cluster-map-track-meta">{meta}</span>
            </div>
          </li>
        );
      })}
    </ul>
  );
}

function PlayButton({ track, playingTrackId, onPreview }: {
  track: Track;
  playingTrackId: number | null;
  onPreview: (track: Track) => void;
}) {
  const playing = playingTrackId === track.track_id;
  const name = displayTrack(track);
  return (
    <button
      className="icon-button cluster-map-play-button"
      data-playing={playing || undefined}
      title={playing ? "Pause preview" : "Preview"}
      aria-label={`${playing ? "Pause" : "Preview"} ${name}`}
      type="button"
      onClick={() => onPreview(track)}
    >
      {playing ? <Pause size={13} /> : <Play size={13} />}
    </button>
  );
}

function mapView(response: ClusterMapResponse): MapView {
  const seeds: ClusterMapPoint[] = [];
  const candidates: Candidate[] = [];
  for (const point of response.points) {
    if (point.seed) seeds.push(point);
    else candidates.push({ point, rank: candidates.length + 1 });
  }
  return {
    seeds,
    candidates,
    exceptions: candidates.filter(({ point }) => point.exception),
    swarm: candidates.filter(({ point }) => !point.exception),
    medianSimilarity: median(candidates.map(({ point }) => point.similarity)),
  };
}

function median(values: number[]) {
  const sorted = [...values].sort((left, right) => left - right);
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2;
}

function plural(count: number, noun: string) {
  return `${count} ${noun}${count === 1 ? "" : "s"}`;
}

function signed(value: number, digits: number) {
  return `${value > 0 ? "+" : ""}${value.toFixed(digits)}`;
}

function railTabTitle(tab: RailTab, subject: string) {
  return tab === "tracks"
    ? "The core, the exceptions and the swarm, each in search order"
    : `What this ${subject} holds, and where it pulls the search`;
}

/** Timbre reads as one group, since a single MFCC means nothing on its own. */
function featureName(item: { feature: string; group: string }) {
  return item.group === "timbral" ? "Timbre" : featureLabel(item.feature);
}

/** A SONARA reason: the feature, its value where it reads, and its gap from the references. */
function reasonText(item: ClusterMapFeatureValue) {
  const gap = `${signed(item.delta, 1)}σ`;
  return item.group === "timbral"
    ? `${featureName(item)} ${gap}`
    : `${featureName(item)} ${formatFeatureValue(item.feature, item.value)} (${gap})`;
}

function groupLabel(group: string) {
  return group.charAt(0).toUpperCase() + group.slice(1);
}

function sonaraFeature(feature: string) {
  for (const group of sonaraCoreFeatureGroups) {
    const descriptor = group.features.find((candidate) => candidate.key === feature);
    if (descriptor) return { key: descriptor.key, label: descriptor.label, group: group.title };
  }
  return null;
}

/** SONARA labels and units come from the track metadata dialog. */
function featureLabel(feature: string) {
  const descriptor = sonaraFeature(feature);
  if (!descriptor) return feature.replaceAll("_", " ");
  return groupScopedLabels.has(descriptor.label)
    ? `${descriptor.group} ${descriptor.label.toLowerCase()}`
    : descriptor.label;
}

function formatFeatureValue(feature: string, value: number) {
  const descriptor = sonaraFeature(feature);
  return descriptor ? formatSonaraCoreValue(descriptor.key, value) : value.toFixed(2);
}
