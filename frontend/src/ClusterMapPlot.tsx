import { CircleAlert, RotateCcw, ZoomIn, ZoomOut } from "lucide-react";
import { useEffect, useLayoutEffect, useMemo, useRef, useState, type CSSProperties, type KeyboardEvent } from "react";
import type {
  Annotations,
  Config,
  Data,
  Layout,
  PlotDatum,
  PlotHoverEvent,
  PlotlyHTMLElement,
  PlotMouseEvent,
  Shape,
} from "plotly.js-basic-dist-min";
import type { ClusterMapPoint, Track } from "./api";
import { errorText } from "./errors";
import { placeTooltip, type TooltipPosition } from "./tooltip";
import { displayTrack } from "./trackDisplay";

type PlotlyModule = typeof import("plotly.js-basic-dist-min");
type AxisRange = [number, number];
type View = { x: AxisRange; y: AxisRange };
type Orbit = { x: number[]; y: number[]; step: number; rings: number };
type Palette = {
  agree: string;
  neutral: string;
  disagree: string;
  glowOpacity: number;
  surface: string;
  textStrong: string;
  textMuted: string;
  borderSoft: string;
  accent: string;
  font: string;
};
/** Plotly adds the hovered point's pixel position inside the plot to its event data. */
type HoverDatum = PlotDatum & { xPixel?: number; yPixel?: number };
type Hover = { index: number; left: number; top: number };

// Ring spacing in similarity units: the first step that needs at most six rings.
const RING_STEPS = [0.005, 0.01, 0.02, 0.025, 0.05, 0.1, 0.2, 0.25, 0.5];
const MAX_RINGS = 6;
const VIEW_MARGIN = 1.1;
const PLOT_CONFIG: Partial<Config> = {
  displayModeBar: false,
  displaylogo: false,
  scrollZoom: true,
  doubleClick: false,
  showTips: false,
  responsive: false,
};

let plotlyLoad: Promise<PlotlyModule> | null = null;

/** Plotly arrives as its own chunk with the first map; a failed fetch is tried again on the next call. */
function loadPlotly(): Promise<PlotlyModule> {
  plotlyLoad ??= import("plotly.js-basic-dist-min")
    // The bundle is UMD, so the build hands it over as the default export.
    .then((module) => (module as { default?: PlotlyModule }).default ?? module)
    .catch((error: unknown) => {
      plotlyLoad = null;
      throw error;
    });
  return plotlyLoad;
}

/** SONARA closeness as the share of the library a track beats. */
export function closenessPercent(closeness: number) {
  return `${Math.round(closeness * 100)}%`;
}

/** The colour the map gives a SONARA closeness: the same diverging scale, from
 * --cluster-disagree through --cluster-neutral (a random track) to --cluster-agree. */
export function closenessSwatch(closeness: number): CSSProperties {
  const pole = closeness >= 0.5 ? "var(--cluster-agree)" : "var(--cluster-disagree)";
  const weight = Math.round(Math.abs(closeness - 0.5) * 200);
  return { background: `color-mix(in srgb, ${pole} ${weight}%, var(--cluster-neutral))` };
}

/** Faint rings standing in for the orbit until it is drawn. */
export function OrbitSkeleton() {
  return (
    <svg className="cluster-map-orbit-skeleton" viewBox="-1 -1 2 2" preserveAspectRatio="xMidYMid meet" aria-hidden="true">
      <line x1="-0.92" y1="0" x2="0.92" y2="0" />
      <line x1="0" y1="-0.92" x2="0" y2="0.92" />
      {[0.3, 0.6, 0.9].map((radius) => <circle key={radius} r={radius} />)}
    </svg>
  );
}

/** The orbit: the reference core in the centre, every point at radius 1 - similarity,
 * coloured by how close SONARA puts it to the references. */
export function ClusterMapPlot({
  mapKey,
  points,
  centerSimilarity,
  playingTrackId,
  featureLabel,
  onPreview,
}: {
  mapKey: string;
  points: ClusterMapPoint[];
  centerSimilarity: number;
  playingTrackId: number | null;
  featureLabel: (feature: string) => string;
  onPreview: (track: Track) => void;
}) {
  const frameRef = useRef<HTMLDivElement | null>(null);
  const hostRef = useRef<HTMLDivElement | null>(null);
  const tooltipRef = useRef<HTMLDivElement | null>(null);
  const viewRef = useRef<View | null>(null);
  const pointsRef = useRef(points);
  pointsRef.current = points;
  const onPreviewRef = useRef(onPreview);
  onPreviewRef.current = onPreview;
  const [plotly, setPlotly] = useState<PlotlyModule | null>(null);
  const [failure, setFailure] = useState("");
  const [attempt, setAttempt] = useState(0);
  const [drawn, setDrawn] = useState(false);
  const [themeRevision, setThemeRevision] = useState(0);
  const [hover, setHover] = useState<Hover | null>(null);
  const [tooltipPosition, setTooltipPosition] = useState<TooltipPosition | null>(null);
  const orbit = useMemo(() => orbitOf(points), [points]);
  const ranks = useMemo(() => candidateRanks(points), [points]);
  const hovered = hover ? points[hover.index] : undefined;
  const hoveredRank = hover ? ranks[hover.index] : null;

  useEffect(() => {
    let cancelled = false;
    setFailure("");
    loadPlotly().then(
      (module) => {
        if (!cancelled) setPlotly(module);
      },
      (error: unknown) => {
        if (!cancelled) setFailure(errorText(error));
      },
    );
    return () => {
      cancelled = true;
    };
  }, [attempt]);

  useEffect(() => {
    const observer = new MutationObserver(() => setThemeRevision((value) => value + 1));
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const host = hostRef.current;
    if (!plotly || !host) return undefined;
    let cancelled = false;
    const { data, layout } = figure(points, orbit, readPalette(host), {
      centerSimilarity,
      playingTrackId,
      mapKey,
      view: viewRef.current,
    });
    plotly.react(host, data, layout, PLOT_CONFIG).then(
      (graph) => {
        if (cancelled) return;
        listen(graph);
        rememberView(graph);
        setDrawn(true);
      },
      (error: unknown) => {
        if (!cancelled) setFailure(errorText(error));
      },
    );
    return () => {
      cancelled = true;
    };
  }, [plotly, points, orbit, centerSimilarity, playingTrackId, mapKey, themeRevision, attempt]);

  useEffect(() => {
    const host = hostRef.current;
    if (!plotly || !host || !drawn) return undefined;
    const observer = new ResizeObserver(() => {
      void Promise.resolve(plotly.Plots.resize(host)).catch(() => undefined);
    });
    observer.observe(host);
    return () => observer.disconnect();
  }, [plotly, drawn]);

  useEffect(() => {
    const host = hostRef.current;
    if (!plotly || !host) return undefined;
    return () => plotly.purge(host);
  }, [plotly]);

  useLayoutEffect(() => {
    const frame = frameRef.current;
    const tooltip = tooltipRef.current;
    if (!hover || !frame || !tooltip) {
      setTooltipPosition(null);
      return;
    }
    const size = tooltip.getBoundingClientRect();
    setTooltipPosition(placeTooltip(
      { left: hover.left - 8, top: hover.top - 8, width: 16, height: 16 },
      { width: size.width, height: size.height },
      { width: frame.clientWidth, height: frame.clientHeight },
    ));
  }, [hover]);

  // Plotly drops its listeners whenever `react` rebuilds the plot, so they are
  // attached after every draw; they read refs, never stale props.
  function listen(graph: PlotlyHTMLElement) {
    for (const name of ["plotly_click", "plotly_hover", "plotly_unhover", "plotly_relayout"]) {
      graph.removeAllListeners(name);
    }
    graph.on("plotly_click", (event: PlotMouseEvent) => {
      const point = pointsRef.current[pointIndex(event.points[0])];
      if (point) onPreviewRef.current(point.track);
    });
    graph.on("plotly_hover", (event: PlotHoverEvent) => {
      const datum = event.points[0] as HoverDatum | undefined;
      const index = pointIndex(datum);
      const frame = frameRef.current;
      if (!datum || index < 0 || !frame) return;
      const box = frame.getBoundingClientRect();
      setHover({
        index,
        left: datum.xPixel ?? event.event.clientX - box.left,
        top: datum.yPixel ?? event.event.clientY - box.top,
      });
    });
    graph.on("plotly_unhover", () => setHover(null));
    graph.on("plotly_relayout", () => {
      rememberView(graph);
      setHover(null);
    });
  }

  function rememberView(graph: PlotlyHTMLElement) {
    const x: unknown = graph.layout.xaxis?.range;
    const y: unknown = graph.layout.yaxis?.range;
    if (isRange(x) && isRange(y)) viewRef.current = { x: [x[0], x[1]], y: [y[0], y[1]] };
  }

  function showView(view: View) {
    const host = hostRef.current;
    if (!plotly || !host) return;
    viewRef.current = view;
    // Dotted keys replace only the ranges, so both axes keep their scale anchor.
    // Plotly may write into the arrays it is given, so it gets copies.
    void plotly.relayout(host, {
      "xaxis.range": [view.x[0], view.x[1]],
      "yaxis.range": [view.y[0], view.y[1]],
    }).catch(() => undefined);
  }

  function zoom(factor: number) {
    const view = viewRef.current;
    if (!view) return;
    const scale = ([low, high]: AxisRange): AxisRange => {
      const centre = (low + high) / 2;
      const half = ((high - low) / 2) * factor;
      return [centre - half, centre + half];
    };
    showView({ x: scale(view.x), y: scale(view.y) });
  }

  const reach = orbit.rings * orbit.step * VIEW_MARGIN;
  const candidateCount = ranks.filter((rank) => rank !== null).length;

  return (
    <div className="cluster-map-plot-frame" ref={frameRef} onPointerLeave={() => setHover(null)}>
      <div
        ref={hostRef}
        className="cluster-map-plot"
        role="img"
        aria-label={`Orbit of ${candidateCount} candidates around the reference core, coloured by SONARA closeness to the references`}
      />
      {!drawn && !failure ? <OrbitSkeleton /> : null}
      {failure ? (
        <div className="cluster-map-plot-error" role="alert">
          <CircleAlert size={16} aria-hidden="true" />
          <span>Could not draw the map: {failure}</span>
          <button type="button" title="Load the map view again" onClick={() => setAttempt((value) => value + 1)}>Retry</button>
        </div>
      ) : null}
      <div className="cluster-map-toolbar" role="toolbar" aria-label="Map view" aria-orientation="vertical" onKeyDown={moveToolbarFocus}>
        <button className="icon-button" type="button" title="Zoom in" aria-label="Zoom in" disabled={!drawn} onClick={() => zoom(0.8)}>
          <ZoomIn size={15} />
        </button>
        <button className="icon-button" type="button" title="Zoom out" aria-label="Zoom out" disabled={!drawn} onClick={() => zoom(1.25)}>
          <ZoomOut size={15} />
        </button>
        <button
          className="icon-button"
          type="button"
          title="Reset view"
          aria-label="Reset view"
          disabled={!drawn}
          onClick={() => showView({ x: [-reach, reach], y: [-reach, reach] })}
        >
          <RotateCcw size={15} />
        </button>
      </div>
      {hovered ? (
        <div
          ref={tooltipRef}
          className="cluster-map-tooltip"
          aria-hidden="true"
          style={tooltipPosition ? { left: tooltipPosition.left, top: tooltipPosition.top } : { left: 0, top: 0, visibility: "hidden" }}
        >
          <strong className="cluster-map-tooltip-values">
            {hovered.seed
              ? `Reference · ${hovered.similarity.toFixed(3)} to core`
              : `${hovered.similarity.toFixed(3)} similarity · #${hoveredRank}`}
          </strong>
          <span className="cluster-map-tooltip-name">{displayTrack(hovered.track)}</span>
          <span className="cluster-map-tooltip-line">
            <i className="cluster-map-swatch" style={closenessSwatch(hovered.sonara_closeness)} />
            {`SONARA: closer than ${closenessPercent(hovered.sonara_closeness)} of the library`}
          </span>
          {hovered.seed ? null : (
            <span className="cluster-map-tooltip-line">
              {hovered.sonara_gaps
                .map((item) => `${featureLabel(item.feature)} ${item.delta > 0 ? "+" : ""}${item.delta.toFixed(1)}σ`)
                .join(" · ")}
            </span>
          )}
        </div>
      ) : null}
    </div>
  );
}

function orbitOf(points: ClusterMapPoint[]): Orbit {
  const radii = points.map((point) => Math.max(0, 1 - point.similarity));
  const reach = Math.max(0, ...radii);
  const ringsFor = (step: number) => Math.max(1, Math.ceil(reach / step - 1e-9));
  const step = RING_STEPS.find((candidate) => ringsFor(candidate) <= MAX_RINGS) ?? RING_STEPS[RING_STEPS.length - 1];
  return {
    x: points.map((point, index) => radii[index] * Math.cos(point.angle)),
    y: points.map((point, index) => radii[index] * Math.sin(point.angle)),
    step,
    rings: ringsFor(step),
  };
}

function candidateRanks(points: ClusterMapPoint[]) {
  let rank = 0;
  return points.map((point) => (point.seed ? null : ++rank));
}

function pointIndex(datum: PlotDatum | undefined) {
  return typeof datum?.customdata === "number" ? datum.customdata : -1;
}

function isRange(value: unknown): value is AxisRange {
  return Array.isArray(value)
    && value.length === 2
    && value.every((item) => typeof item === "number" && Number.isFinite(item));
}

// Plotly parses colours itself, so every token it reads must be a plain hex value.
function readPalette(host: HTMLElement): Palette {
  const style = getComputedStyle(host);
  const token = (name: string) => style.getPropertyValue(name).trim();
  return {
    agree: token("--cluster-agree"),
    neutral: token("--cluster-neutral"),
    disagree: token("--cluster-disagree"),
    glowOpacity: Number.parseFloat(token("--cluster-glow-opacity")) || 0,
    surface: token("--surface"),
    textStrong: token("--text-strong"),
    textMuted: token("--text-muted"),
    borderSoft: token("--border-soft"),
    accent: token("--accent"),
    font: style.fontFamily,
  };
}

function figure(
  points: ClusterMapPoint[],
  orbit: Orbit,
  palette: Palette,
  { centerSimilarity, playingTrackId, mapKey, view }: {
    centerSimilarity: number;
    playingTrackId: number | null;
    mapKey: string;
    view: View | null;
  },
): { data: Data[]; layout: Partial<Layout> } {
  const at = (indexes: number[]) => ({
    x: indexes.map((index) => orbit.x[index]),
    y: indexes.map((index) => orbit.y[index]),
  });
  // SONARA's opinion on a diverging scale centred on a random library track;
  // the tracks it disagrees with draw last, over the ones it agrees with.
  const candidates = points
    .flatMap((point, index) => (point.seed ? [] : [index]))
    .sort((left, right) => points[right].sonara_closeness - points[left].sonara_closeness);
  const seeds = points.flatMap((point, index) => (point.seed ? [index] : []));
  const closeness = {
    color: candidates.map((index) => points[index].sonara_closeness),
    cmin: 0,
    cmax: 1,
    colorscale: [[0, palette.disagree], [0.5, palette.neutral], [1, palette.agree]] as Array<[number, string]>,
  };
  const data: Data[] = [];
  if (palette.glowOpacity > 0) {
    data.push({
      type: "scatter",
      mode: "markers",
      ...at(candidates),
      hoverinfo: "skip",
      marker: { ...closeness, size: 22, opacity: palette.glowOpacity, line: { width: 0 } },
    });
  }
  data.push({
    type: "scatter",
    mode: "markers",
    ...at(candidates),
    customdata: candidates,
    hoverinfo: "none",
    marker: { ...closeness, size: 10, line: { width: 2, color: palette.surface } },
  });
  data.push({
    type: "scatter",
    mode: "markers",
    ...at(seeds),
    customdata: seeds,
    hoverinfo: "none",
    marker: { symbol: "diamond", size: 13, color: palette.textStrong, line: { width: 2, color: palette.surface } },
  });
  const playing = points.findIndex((point) => point.track.track_id === playingTrackId);
  if (playing >= 0) {
    data.push({
      type: "scatter",
      mode: "markers",
      ...at([playing]),
      hoverinfo: "skip",
      marker: { symbol: "circle-open", size: 22, color: palette.accent, line: { color: palette.accent, width: 2 } },
    });
  }

  const radii = Array.from({ length: orbit.rings }, (_, ring) => (ring + 1) * orbit.step);
  const outer = radii[radii.length - 1];
  const reach = outer * VIEW_MARGIN;
  const decimals = Math.max(2, (String(orbit.step).split(".")[1] ?? "").length);
  const hairline = { color: palette.borderSoft, width: 1 };
  // The candidates' centre of mass sits on this ring; the angle carries no meaning
  // there, since the angle axes are centred on the candidates themselves.
  const centerRadius = Math.max(0, 1 - centerSimilarity);
  const shapes: Partial<Shape>[] = [
    { type: "line", layer: "below", xref: "x", yref: "y", x0: -outer, y0: 0, x1: outer, y1: 0, line: hairline },
    { type: "line", layer: "below", xref: "x", yref: "y", x0: 0, y0: -outer, x1: 0, y1: outer, line: hairline },
    ...radii.map((radius): Partial<Shape> => ({
      type: "circle",
      layer: "below",
      xref: "x",
      yref: "y",
      x0: -radius,
      y0: -radius,
      x1: radius,
      y1: radius,
      line: hairline,
    })),
    {
      type: "circle",
      layer: "below",
      xref: "x",
      yref: "y",
      x0: -centerRadius,
      y0: -centerRadius,
      x1: centerRadius,
      y1: centerRadius,
      line: { color: palette.accent, width: 1.5, dash: "dash" },
    },
  ];
  const ringLabels = radii.map((radius): Partial<Annotations> => ({
    x: radius * Math.SQRT1_2,
    y: radius * Math.SQRT1_2,
    xref: "x",
    yref: "y",
    text: (1 - radius).toFixed(decimals),
    showarrow: false,
    xanchor: "left",
    yanchor: "bottom",
    font: { size: 10, color: palette.textMuted },
  }));
  const range = view ? { x: [...view.x], y: [...view.y] } : { x: [-reach, reach], y: [-reach, reach] };
  return {
    data,
    layout: {
      autosize: true,
      margin: { l: 0, r: 0, t: 0, b: 0 },
      paper_bgcolor: "transparent",
      plot_bgcolor: "transparent",
      font: { family: palette.font, size: 11, color: palette.textMuted },
      showlegend: false,
      hovermode: "closest",
      hoverdistance: 16,
      dragmode: "pan",
      uirevision: mapKey,
      xaxis: { visible: false, range: range.x, autorange: false, zeroline: false, showgrid: false },
      yaxis: {
        visible: false,
        range: range.y,
        autorange: false,
        zeroline: false,
        showgrid: false,
        scaleanchor: "x",
        scaleratio: 1,
      },
      shapes,
      annotations: ringLabels,
    },
  };
}

function moveToolbarFocus(event: KeyboardEvent<HTMLDivElement>) {
  const step = event.key === "ArrowDown" || event.key === "ArrowRight"
    ? 1
    : event.key === "ArrowUp" || event.key === "ArrowLeft"
      ? -1
      : 0;
  if (!step) return;
  const buttons = [...event.currentTarget.querySelectorAll<HTMLButtonElement>("button:not(:disabled)")];
  const current = buttons.findIndex((button) => button === document.activeElement);
  if (current < 0) return;
  event.preventDefault();
  buttons[(current + step + buttons.length) % buttons.length].focus();
}
