import { ArrowDown, ArrowUp, CircleAlert, OctagonAlert, Pause, Play, TriangleAlert, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import type {
  ClusterMapFeature,
  ClusterMapPoint,
  ClusterMapReason,
  ClusterMapResponse,
  ClusterMapTrait,
  EmbeddingLayersResponse,
  Track,
} from "./api";
import { ClusterMapPlot, OrbitSkeleton, clusterLetter } from "./ClusterMapPlot";
import { formatMaestGenreLabel } from "./maestGenres";
import { seedSearchModelPresentation, tabAfterKey } from "./searchSurfaceState";
import { formatSonaraCoreValue, sonaraCoreFeatureGroups } from "./TrackMetadataDialog";
import { displayTrack } from "./trackDisplay";
import type { ClusterMapEntry } from "./useClusterMap";
import type { EmbeddingLayerState } from "./useEmbeddingLayers";

type RailTab = "clusters" | "anomalies" | "layer";
type LayerRow = EmbeddingLayersResponse["layers"][number];
type Candidate = { point: ClusterMapPoint; rank: number };
type MapView = {
  seeds: ClusterMapPoint[];
  candidates: Candidate[];
  members: Candidate[][];
  flagged: Candidate[];
  withSonara: number;
  medianSimilarity: number | null;
};

const railTabs: readonly RailTab[] = ["clusters", "anomalies", "layer"];
const TEMPO_FEATURE = "detected_bpm";
const TIMBRE_FEATURE = "mfcc_mean_blob";
// Two clusters need at least eight candidates (four per cluster) before the server tries them.
const FEW_CANDIDATES = 8;
const CLOSEST_MEMBERS = 4;
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
 * cached, so a closed map keeps its zoom, tab and isolated cluster. */
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
  const [tab, setTab] = useState<RailTab>("clusters");
  const [isolated, setIsolated] = useState<number | null>(null);
  const { payload, response } = entry;
  const view = useMemo(() => (response ? mapView(response) : null), [response]);
  const layer = payload.layer ?? null;
  const layerRow = layer === null ? null : layerState.layers?.find((row) => row.layer === layer) ?? null;
  const seedCount = payload.seed_track_ids.length;
  const summary = view
    ? [
      plural(seedCount, "reference track"),
      plural(view.candidates.length, "candidate"),
      view.medianSimilarity === null ? "" : `median similarity ${view.medianSimilarity.toFixed(3)}`,
    ].filter(Boolean).join(" · ")
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
              {[0, 1, 2, 3].map((tile) => (
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
        ) : response && view && view.candidates.length === 0 ? (
          <div className="cluster-map-body">
            <div className="empty-state">The search returned no candidates, so there is nothing to map.</div>
          </div>
        ) : response && view ? (
          <div className="cluster-map-body">
            <KpiRow response={response} view={view} />
            <div className="cluster-map-main">
              <figure className="cluster-map-figure">
                <figcaption>Candidates orbit the reference core: the closer a point, the more similar the track. Click a point to preview it.</figcaption>
                <ClusterMapPlot
                  mapKey={entry.key}
                  points={response.points}
                  clusterCount={response.clusters.length}
                  isolated={isolated}
                  playingTrackId={playingTrackId}
                  featureLabel={featureLabel}
                  onPreview={onPreview}
                />
                {response.clusters.length === 1 && view.candidates.length < FEW_CANDIDATES ? (
                  <p className="cluster-map-note">
                    Only {plural(view.candidates.length, "candidate")}. Raise Limit for a denser map.
                  </p>
                ) : null}
                <div className="cluster-map-legend">
                  {response.clusters.length > 1 ? response.clusters.map((_, cluster) => (
                    <button
                      key={cluster}
                      type="button"
                      className="cluster-map-legend-chip"
                      data-slot={cluster + 1}
                      aria-pressed={isolated === cluster}
                      aria-label={`Cluster ${clusterLetter(cluster)}, ${plural(view.members[cluster].length, "candidate")}`}
                      title={isolated === cluster ? "Show every cluster" : `Show only cluster ${clusterLetter(cluster)}`}
                      onClick={() => setIsolated(isolated === cluster ? null : cluster)}
                    >
                      <span className="cluster-map-dot" />
                      {clusterLetter(cluster)}
                      <span className="cluster-map-legend-count">{view.members[cluster].length}</span>
                    </button>
                  )) : null}
                  <span className="cluster-map-key">
                    <span className="cluster-map-key-core" aria-hidden="true" />
                    Core · {view.seeds.length}
                  </span>
                  <span className="cluster-map-key">
                    <span className="cluster-map-key-ring" aria-hidden="true" />
                    Stands out · {view.flagged.length}
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
                      title={railTabTitle(name, layer)}
                      role="tab"
                      aria-selected={tab === name}
                      aria-controls={`cluster-map-panel-${name}`}
                      tabIndex={tab === name ? 0 : -1}
                      type="button"
                      onClick={() => setTab(name)}
                      onKeyDown={selectTabByKey}
                    >
                      {name === "clusters" ? "Clusters" : name === "anomalies" ? "Anomalies" : layer !== null ? "Layer" : "Model"}
                    </button>
                  ))}
                </div>
                <div
                  id={`cluster-map-panel-${tab}`}
                  className="cluster-map-tab-panel"
                  role="tabpanel"
                  aria-labelledby={`cluster-map-tab-${tab}`}
                >
                  {tab === "clusters" ? (
                    <ClustersPanel
                      response={response}
                      view={view}
                      isolated={isolated}
                      playingTrackId={playingTrackId}
                      onPreview={onPreview}
                    />
                  ) : tab === "anomalies" ? (
                    <AnomaliesPanel view={view} playingTrackId={playingTrackId} onPreview={onPreview} />
                  ) : (
                    <LayerPanel response={response} view={view} layer={layer} layerRow={layerRow} note={layerState.note} />
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

function KpiRow({ response, view }: { response: ClusterMapResponse; view: MapView }) {
  const total = view.candidates.length;
  const clusterCount = response.clusters.length;
  const largest = Math.max(...view.members.map((members) => members.length));
  const percent = (count: number) => `${Math.round((count / total) * 100)}%`;
  return (
    <dl className="cluster-map-kpis">
      <div className="cluster-map-kpi">
        <dt>Separation</dt>
        <dd className="cluster-map-kpi-value">{response.silhouette === null ? "—" : response.silhouette.toFixed(2)}</dd>
        <dd className="cluster-map-kpi-note">{separationNote(response.silhouette)}</dd>
      </div>
      <div className="cluster-map-kpi">
        <dt>Clusters</dt>
        <dd className="cluster-map-kpi-value">{clusterCount}</dd>
        <dd className="cluster-map-kpi-note">{clusterCount === 1 ? "all candidates in one" : `${percent(largest)} in the largest`}</dd>
      </div>
      <div className="cluster-map-kpi">
        <dt>In cluster A</dt>
        <dd className="cluster-map-kpi-value">{percent(view.members[0]?.length ?? 0)}</dd>
        <dd className="cluster-map-kpi-note">nearest to the references</dd>
      </div>
      <div className="cluster-map-kpi">
        <dt>Anomalies</dt>
        <dd className="cluster-map-kpi-value">{view.withSonara ? view.flagged.length : "—"}</dd>
        <dd className="cluster-map-kpi-note">
          {!view.withSonara ? "no SONARA to compare" : view.flagged.length ? (
            <>
              <TriangleAlert size={13} aria-hidden="true" />
              stand out
            </>
          ) : "none stand out"}
        </dd>
      </div>
    </dl>
  );
}

function ClustersPanel({ response, view, isolated, playingTrackId, onPreview }: {
  response: ClusterMapResponse;
  view: MapView;
  isolated: number | null;
  playingTrackId: number | null;
  onPreview: (track: Track) => void;
}) {
  const several = response.clusters.length > 1;
  return (
    <>
      <SonaraCoverageNote
        view={view}
        none="None of these tracks has SONARA analysis, so the clusters show no SONARA traits."
        partial={`Traits use ${view.withSonara} of ${view.candidates.length} tracks with SONARA.`}
      />
      <div className="cluster-map-cards">
        <article className="cluster-map-card cluster-map-core-card">
          <header className="cluster-map-card-head">
            <span className="cluster-map-key-core" aria-hidden="true" />
            <h3>Core</h3>
            <span className="cluster-map-card-meta">{plural(view.seeds.length, "reference track")}</span>
          </header>
          <ul className="cluster-map-track-list">
            {view.seeds.map((point) => (
              <li key={point.track.track_id}>
                <TrackLine
                  track={point.track}
                  meta={`${point.similarity.toFixed(3)} to core`}
                  playingTrackId={playingTrackId}
                  onPreview={onPreview}
                />
              </li>
            ))}
          </ul>
        </article>
        {response.clusters.map((cluster, index) => {
          const members = view.members[index];
          const representative = view.candidates.find(({ point }) => point.track.track_id === cluster.representative_track_id);
          const letter = clusterLetter(index);
          return (
            <article
              key={index}
              className="cluster-map-card"
              data-slot={index + 1}
              data-active={isolated === index || undefined}
              data-dimmed={(isolated !== null && isolated !== index) || undefined}
            >
              <header className="cluster-map-card-head">
                <span className="cluster-map-dot" aria-hidden="true" />
                <h3>Cluster {letter}</h3>
                <span className="cluster-map-card-meta">
                  {plural(members.length, "candidate")} · median {cluster.median_similarity.toFixed(3)}
                </span>
              </header>
              {representative ? (
                <div className="cluster-map-field">
                  <span className="cluster-map-field-label">Representative</span>
                  <TrackLine
                    track={representative.point.track}
                    meta={`#${representative.rank} · ${representative.point.similarity.toFixed(3)}`}
                    playingTrackId={playingTrackId}
                    onPreview={onPreview}
                  />
                </div>
              ) : null}
              {cluster.traits.length ? (
                <div className="cluster-map-traits">
                  {cluster.traits.map((trait) => <TraitChip key={trait.feature} trait={trait} />)}
                </div>
              ) : several && view.withSonara ? (
                <p className="cluster-map-muted">No SONARA trait sets this cluster apart.</p>
              ) : null}
              {cluster.maest_genres.length ? (
                <p className="cluster-map-genres" title="MAEST genres: each genre's share of the cluster's summed genre scores">
                  {cluster.maest_genres
                    .map((genre) => `${formatMaestGenreLabel(genre.genre_name)} ${Math.round(genre.share * 100)}%`)
                    .join(" · ")}
                </p>
              ) : null}
              <ul className="cluster-map-track-list">
                {members.slice(0, CLOSEST_MEMBERS).map((member) => (
                  <li key={member.point.track.track_id}>
                    <TrackLine
                      track={member.point.track}
                      meta={`#${member.rank} · ${member.point.similarity.toFixed(3)}`}
                      playingTrackId={playingTrackId}
                      onPreview={onPreview}
                    />
                  </li>
                ))}
              </ul>
              {members.length > CLOSEST_MEMBERS ? (
                <details className="cluster-map-more">
                  <summary>Show all {members.length}</summary>
                  <ul className="cluster-map-track-list">
                    {members.slice(CLOSEST_MEMBERS).map((member) => (
                      <li key={member.point.track.track_id}>
                        <TrackLine
                          track={member.point.track}
                          meta={`#${member.rank} · ${member.point.similarity.toFixed(3)}`}
                          playingTrackId={playingTrackId}
                          onPreview={onPreview}
                        />
                      </li>
                    ))}
                  </ul>
                </details>
              ) : null}
            </article>
          );
        })}
      </div>
    </>
  );
}

function AnomaliesPanel({ view, playingTrackId, onPreview }: {
  view: MapView;
  playingTrackId: number | null;
  onPreview: (track: Track) => void;
}) {
  if (!view.withSonara) {
    return (
      <div className="empty-state">
        Anomalies compare SONARA features, and none of these candidates has SONARA analysis. Run SONARA analysis to see which tracks stand out.
      </div>
    );
  }
  const coverage = (
    <SonaraCoverageNote
      view={view}
      none=""
      partial={`Checked ${view.withSonara} of ${view.candidates.length} tracks: the rest have no SONARA analysis.`}
    />
  );
  if (!view.flagged.length) {
    return (
      <>
        {coverage}
        <div className="empty-state">No candidate leaves the references' SONARA range far enough to stand out.</div>
      </>
    );
  }
  const rows = [...view.flagged].sort((left, right) =>
    Number(isStrong(right.point)) - Number(isStrong(left.point))
    || right.point.anomalies.length - left.point.anomalies.length
    || left.rank - right.rank);
  return (
    <>
      <p className="cluster-map-anomaly-summary">{anomalySummary(view.flagged)}</p>
      {coverage}
      <ul className="cluster-map-anomalies">
        {rows.map(({ point, rank }) => {
          const name = displayTrack(point.track);
          const strong = isStrong(point);
          return (
            <li key={point.track.track_id} className="cluster-map-anomaly">
              <PlayButton track={point.track} playingTrackId={playingTrackId} onPreview={onPreview} />
              <div className="cluster-map-anomaly-title">
                <strong title={name}>{name}</strong>
                <span className="cluster-map-anomaly-meta" data-slot={point.cluster + 1}>
                  <span className="cluster-map-dot" aria-hidden="true" />
                  Cluster {clusterLetter(point.cluster)} · #{rank} · {point.similarity.toFixed(3)}
                </span>
              </div>
              <span className="cluster-map-severity" data-severity={strong ? "strong" : "mild"}>
                {strong ? <OctagonAlert size={12} aria-hidden="true" /> : <TriangleAlert size={12} aria-hidden="true" />}
                {strong ? "Strong" : "Mild"}
              </span>
              <div className="cluster-map-reasons">
                {point.anomalies.map((reason) => (
                  <span key={reason.feature} className="cluster-map-reason" title={reasonTitle(reason)}>
                    {reasonText(reason)}
                  </span>
                ))}
              </div>
            </li>
          );
        })}
      </ul>
    </>
  );
}

function LayerPanel({ response, view, layer, layerRow, note }: {
  response: ClusterMapResponse;
  view: MapView;
  layer: number | null;
  layerRow: LayerRow | null;
  note: string | null;
}) {
  const subject = layer !== null ? "layer" : "model";
  const kept = response.angle_variance_kept;
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
          Each bar divides how far the candidates sit from the references on a SONARA feature by how far a random library
          track sits. Below 1× the {subject} keeps that feature closer to the references than chance.
        </p>
        {view.withSonara ? (
          <>
            <div className="cluster-map-focus-scale" aria-hidden="true">
              <span>0.25×</span>
              <span>1×</span>
              <span>4×</span>
            </div>
            {groupFeatures(response.features).map(([group, features]) => (
              <div key={group} className="cluster-map-focus-group">
                <h4>{group.charAt(0).toUpperCase() + group.slice(1)}</h4>
                {features.map((feature) => <FocusBar key={feature.feature} feature={feature} />)}
              </div>
            ))}
          </>
        ) : (
          <div className="empty-state">None of these candidates has SONARA analysis, so there is nothing to compare.</div>
        )}
      </div>
      <div className="cluster-map-focus">
        <h3>Separation</h3>
        <p className="cluster-map-prose">
          Separation is the silhouette score of the clusters, measured on the directions in which the candidates differ from
          the core: near 1 the groups are distinct, near 0 they overlap. Below 0.15 the map keeps one cluster, because no
          split is clear enough to trust.
        </p>
      </div>
      <p className="cluster-map-prose">
        Distance from the centre is exact (1 − similarity to the core); the angle only approximates the direction of
        difference{kept === null ? "" : ` and keeps ${Math.round(kept * 100)}% of it`}.
      </p>
      <p className="cluster-map-prose">
        Each map covers one model and layer; switch Model or Layer in the panel and open the map again to compare.
      </p>
    </div>
  );
}

function SonaraCoverageNote({ view, none, partial }: { view: MapView; none: string; partial: string }) {
  if (view.withSonara === view.candidates.length) return null;
  const text = view.withSonara ? partial : none;
  return text ? <p className="cluster-map-note empty-state">{text}</p> : null;
}

function TrackLine({ track, meta, playingTrackId, onPreview }: {
  track: Track;
  meta: string;
  playingTrackId: number | null;
  onPreview: (track: Track) => void;
}) {
  const name = displayTrack(track);
  return (
    <div className="cluster-map-track">
      <PlayButton track={track} playingTrackId={playingTrackId} onPreview={onPreview} />
      <span className="cluster-map-track-name" title={name}>{name}</span>
      <span className="cluster-map-track-meta">{meta}</span>
    </div>
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

function TraitChip({ trait }: { trait: ClusterMapTrait }) {
  return (
    <span
      className="cluster-map-trait"
      title={`Cluster median ${formatFeatureValue(trait.feature, trait.cluster_median)} · others ${formatFeatureValue(trait.feature, trait.rest_median)}`}
    >
      {trait.delta > 0 ? <ArrowUp size={12} aria-hidden="true" /> : <ArrowDown size={12} aria-hidden="true" />}
      {`${featureLabel(trait.feature)} ${trait.delta > 0 ? "+" : ""}${trait.delta.toFixed(1)}σ`}
    </span>
  );
}

function FocusBar({ feature }: { feature: ClusterMapFeature }) {
  const label = featureLabel(feature.feature);
  const ratio = feature.results_gap !== null && feature.library_gap !== null && feature.library_gap !== 0
    ? feature.results_gap / feature.library_gap
    : null;
  if (ratio === null) {
    return (
      <div className="cluster-map-focus-row" title={`${label}: not enough SONARA data to compare.`}>
        <span className="cluster-map-focus-label">{label}</span>
        <span className="cluster-map-focus-track" />
        <span className="cluster-map-focus-value">—</span>
      </div>
    );
  }
  // A log2 scale centred on 1×, clamped to 0.25×–4×.
  const position = Math.max(-2, Math.min(2, Math.log2(ratio)));
  const reference = feature.core_low !== null && feature.core_high !== null
    ? ` References ${formatRange(feature.feature, feature.core_low, feature.core_high)}.`
    : "";
  return (
    <div
      className="cluster-map-focus-row"
      data-holds={ratio < 1 || undefined}
      title={`${label}: candidates sit a median ${formatFeatureValue(feature.feature, feature.results_gap ?? 0)} from the references' range, a random library track ${formatFeatureValue(feature.feature, feature.library_gap ?? 0)}.${reference}`}
    >
      <span className="cluster-map-focus-label">{label}</span>
      <span className="cluster-map-focus-track">
        <span className="cluster-map-focus-bar" style={{ left: `${50 + Math.min(0, position) * 25}%`, width: `${Math.abs(position) * 25}%` }} />
      </span>
      <span className="cluster-map-focus-value">{formatRatio(ratio)}</span>
    </div>
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
    members: response.clusters.map((_, cluster) => candidates.filter(({ point }) => point.cluster === cluster)),
    flagged: candidates.filter(({ point }) => point.anomalies.length > 0),
    withSonara: candidates.filter(({ point }) => point.has_sonara).length,
    medianSimilarity: median(candidates.map(({ point }) => point.similarity)),
  };
}

function median(values: number[]) {
  if (!values.length) return null;
  const sorted = [...values].sort((left, right) => left - right);
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2;
}

function plural(count: number, noun: string) {
  return `${count} ${noun}${count === 1 ? "" : "s"}`;
}

function separationNote(silhouette: number | null) {
  if (silhouette === null || silhouette < 0.15) return "no clear sub-groups";
  return silhouette < 0.35 ? "moderate sub-groups" : "clear sub-groups";
}

function railTabTitle(tab: RailTab, layer: number | null) {
  if (tab === "clusters") return "The core and each cluster: representative, traits, genres and closest tracks";
  if (tab === "anomalies") return "Candidates whose SONARA features leave the references' range";
  return layer !== null
    ? "What this layer keeps close to the references, and how to read the map"
    : "What this model keeps close to the references, and how to read the map";
}

function isStrong(point: ClusterMapPoint) {
  return point.anomalies.some((reason) => reason.severity === "strong");
}

function anomalySummary(flagged: Candidate[]) {
  const counts = new Map<string, number>();
  for (const { point } of flagged) {
    for (const reason of point.anomalies) {
      const direction = reason.feature === TEMPO_FEATURE || reason.feature === TIMBRE_FEATURE
        ? ""
        : reason.delta > 0 ? ", higher" : ", lower";
      const key = `${featureLabel(reason.feature)}${direction}`;
      counts.set(key, (counts.get(key) ?? 0) + 1);
    }
  }
  return [...counts]
    .sort((left, right) => right[1] - left[1] || left[0].localeCompare(right[0]))
    .map(([key, count]) => `${key} ×${count}`)
    .join(" · ");
}

function reasonText(reason: ClusterMapReason) {
  const label = featureLabel(reason.feature);
  if (reason.feature === TIMBRE_FEATURE) return `${label} ${reason.z.toFixed(1)}σ from ref`;
  if (reason.feature === TEMPO_FEATURE) {
    const bpm = (value: number | null) => (value === null ? "—" : String(Math.round(value)));
    const reference = reason.reference_low === null || reason.reference_high === null
      ? "—"
      : bpm(reason.reference_low) === bpm(reason.reference_high)
        ? bpm(reason.reference_low)
        : `${bpm(reason.reference_low)}–${bpm(reason.reference_high)}`;
    return `${label} ${bpm(reason.value)} · ${Math.round(reason.delta)} BPM from ref ${reference}`;
  }
  const value = reason.value === null ? "—" : formatFeatureValue(reason.feature, reason.value);
  const reference = reason.reference_low === null || reason.reference_high === null
    ? "—"
    : formatRange(reason.feature, reason.reference_low, reason.reference_high);
  return `${label} ${value} vs ref ${reference}`;
}

function reasonTitle(reason: ClusterMapReason) {
  const severity = reason.severity === "strong" ? "Strong" : "Mild";
  if (reason.feature === TEMPO_FEATURE) {
    return `${severity}: ${Math.round(reason.delta)} BPM from the references' tempo, counting half and double time.`;
  }
  return `${severity}: ${reason.z.toFixed(1)}σ outside the references' range, in library σ.`;
}

function groupFeatures(features: ClusterMapFeature[]) {
  const groups = new Map<string, ClusterMapFeature[]>();
  for (const feature of features) groups.set(feature.group, [...(groups.get(feature.group) ?? []), feature]);
  return [...groups];
}

function formatRatio(ratio: number) {
  if (ratio >= 10) return `${Math.round(ratio)}×`;
  return `${ratio.toFixed(ratio >= 0.1 ? 1 : 2)}×`;
}

function sonaraFeature(feature: string) {
  for (const group of sonaraCoreFeatureGroups) {
    const descriptor = group.features.find((candidate) => candidate.key === feature);
    if (descriptor) return { key: descriptor.key, label: descriptor.label, group: group.title };
  }
  return null;
}

/** SONARA labels and units come from the track metadata dialog; timbre is the map's own distance in σ. */
function featureLabel(feature: string) {
  if (feature === TIMBRE_FEATURE) return "Timbre (MFCC)";
  const descriptor = sonaraFeature(feature);
  if (!descriptor) return feature.replaceAll("_", " ");
  return groupScopedLabels.has(descriptor.label)
    ? `${descriptor.group} ${descriptor.label.toLowerCase()}`
    : descriptor.label;
}

function formatFeatureValue(feature: string, value: number) {
  if (feature === TEMPO_FEATURE) return `${Math.round(value)} BPM`;
  if (feature === TIMBRE_FEATURE) return `${value.toFixed(1)}σ`;
  const descriptor = sonaraFeature(feature);
  return descriptor ? formatSonaraCoreValue(descriptor.key, value) : value.toFixed(3);
}

// "-10.1 LUFS" and "-9.8 LUFS" read as "-10.1…-9.8 LUFS".
function formatRange(feature: string, low: number, high: number) {
  const lowText = formatFeatureValue(feature, low);
  const highText = formatFeatureValue(feature, high);
  if (lowText === highText) return highText;
  const unit = /(\s[^\d\s]+|\/s|σ)$/.exec(highText)?.[0] ?? "";
  const lowNumber = unit && lowText.endsWith(unit) ? lowText.slice(0, -unit.length) : lowText;
  return `${lowNumber}…${highText}`;
}
