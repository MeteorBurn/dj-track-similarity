import { CircleAlert, RotateCcw, ZoomIn, ZoomOut } from "lucide-react";
import { useEffect, useLayoutEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import type { Config, Data, Layout, PlotDatum, PlotHoverEvent, PlotlyHTMLElement, PlotMouseEvent } from "plotly.js-basic-dist-min";
import type { ClusterMapPoint, Track } from "./api";
import { errorText } from "./errors";
import { placeTooltip, type TooltipPosition } from "./tooltip";
import { displayTrack } from "./trackDisplay";

type PlotlyModule = typeof import("plotly.js-basic-dist-min");
type AxisRange = [number, number];
type View = { x: AxisRange; y: AxisRange };
type HoverDatum = PlotDatum & { xPixel?: number; yPixel?: number };
type Hover = { index: number; left: number; top: number };
const PLOT_CONFIG: Partial<Config> = {
  displayModeBar: false, displaylogo: false, scrollZoom: true,
  doubleClick: false, showTips: false, responsive: false,
};
let plotlyLoad: Promise<PlotlyModule> | null = null;

function loadPlotly(): Promise<PlotlyModule> {
  plotlyLoad ??= import("plotly.js-basic-dist-min")
    .then((module) => (module as { default?: PlotlyModule }).default ?? module)
    .catch((error: unknown) => { plotlyLoad = null; throw error; });
  return plotlyLoad;
}

export function MapSkeleton() {
  return <div className="cluster-map-plot-loading" role="status">Подготавливаем сравнение модели и SONARA…</div>;
}

/** Both coordinates are measurements; unmeasured candidates remain in the ranked list. */
export function ClusterMapPlot({
  mapKey, points, librarySimilarity, totalDescriptors, selectedTrackId, playingTrackId, describePoint, onSelect, onPreview,
}: {
  mapKey: string;
  points: ClusterMapPoint[];
  librarySimilarity: number;
  totalDescriptors: number;
  selectedTrackId: number | null;
  playingTrackId: number | null;
  describePoint: (point: ClusterMapPoint) => string;
  onSelect: (trackId: number) => void;
  onPreview: (track: Track) => void;
}) {
  const frameRef = useRef<HTMLDivElement | null>(null);
  const hostRef = useRef<HTMLDivElement | null>(null);
  const tooltipRef = useRef<HTMLDivElement | null>(null);
  const viewRef = useRef<View | null>(null);
  const callbacks = useRef({ points, onSelect, onPreview });
  callbacks.current = { points, onSelect, onPreview };
  const [plotly, setPlotly] = useState<PlotlyModule | null>(null);
  const [failure, setFailure] = useState("");
  const [attempt, setAttempt] = useState(0);
  const [drawn, setDrawn] = useState(false);
  const [themeRevision, setThemeRevision] = useState(0);
  const [hover, setHover] = useState<Hover | null>(null);
  const [tooltipPosition, setTooltipPosition] = useState<TooltipPosition | null>(null);
  const measured = useMemo(() => points.flatMap((point, index) => (
    !point.seed && point.sonara.available && point.sonara.percentile !== null ? [index] : []
  )), [points]);
  const defaultView = useMemo<View>(() => ({
    x: [Math.min(librarySimilarity, ...points.filter((point) => !point.seed).map((point) => point.similarity)) - 0.01, 1.01],
    y: [-3, 103],
  }), [points, librarySimilarity]);
  const hovered = hover ? points[hover.index] : undefined;

  useEffect(() => {
    let cancelled = false;
    setFailure("");
    loadPlotly().then(
      (module) => { if (!cancelled) setPlotly(module); },
      (error: unknown) => { if (!cancelled) setFailure(errorText(error)); },
    );
    return () => { cancelled = true; };
  }, [attempt]);

  useEffect(() => {
    const observer = new MutationObserver(() => setThemeRevision((value) => value + 1));
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const host = hostRef.current;
    if (!plotly || !host) return;
    let cancelled = false;
    const style = getComputedStyle(host);
    const token = (name: string) => style.getPropertyValue(name).trim();
    const ordinary = measured.filter((index) => points[index].sonara.requires_listening === false && points[index].sonara.descriptor_count === totalDescriptors);
    const anomalous = measured.filter((index) => points[index].sonara.requires_listening === true);
    const incomplete = measured.filter((index) => points[index].sonara.requires_listening !== true && !ordinary.includes(index));
    const coordinates = (indexes: number[]) => ({
      x: indexes.map((index) => points[index].similarity),
      y: indexes.map((index) => points[index].sonara.percentile!),
    });
    const data: Data[] = [
      { type: "scatter", mode: "markers", ...coordinates(ordinary), customdata: ordinary, hoverinfo: "none",
        marker: { size: 10, color: token("--text-muted"), line: { width: 1, color: token("--surface") } } },
      { type: "scatter", mode: "markers", ...coordinates(anomalous), customdata: anomalous, hoverinfo: "none",
        marker: { size: 11, symbol: "diamond", color: token("--cluster-exception"), line: { width: 1, color: token("--surface") } } },
      { type: "scatter", mode: "markers", ...coordinates(incomplete), customdata: incomplete, hoverinfo: "none",
        marker: { size: 10, symbol: "x", color: token("--text-muted") } },
    ];
    const selected = measured.filter((index) => points[index].track.track_id === selectedTrackId);
    const playing = measured.filter((index) => points[index].track.track_id === playingTrackId);
    for (const [indexes, color, size] of [
      [selected, token("--text-strong"), 19], [playing, token("--accent"), 24],
    ] as const) {
      if (indexes.length) data.push({
        type: "scatter", mode: "markers", ...coordinates(indexes), hoverinfo: "skip",
        marker: { symbol: "circle-open", size, color, line: { color, width: 2 } },
      });
    }
    const view = viewRef.current ?? defaultView;
    const layout: Partial<Layout> = {
      autosize: true, margin: { l: 58, r: 18, t: 22, b: 54 },
      paper_bgcolor: "transparent", plot_bgcolor: "transparent",
      font: { family: style.fontFamily, size: 10, color: token("--text-muted") },
      showlegend: false, hovermode: "closest", hoverdistance: 16, dragmode: "pan", uirevision: mapKey,
      xaxis: {
        title: { text: "Сходство модели · cosine →" }, range: [...view.x], autorange: false,
        zeroline: false, gridcolor: token("--border-soft"), tickformat: ".2f",
      },
      yaxis: {
        title: { text: "Расхождение SONARA · процентиль" }, range: [...view.y], autorange: false,
        zeroline: false, gridcolor: token("--border-soft"), tickmode: "array", tickvals: [0, 25, 50, 75, 100],
      },
      shapes: [{
        type: "line", layer: "below", xref: "x", yref: "paper", x0: librarySimilarity, x1: librarySimilarity, y0: 0, y1: 1,
        line: { color: token("--text-muted"), width: 1.5, dash: "dash" },
      }],
    };
    void Promise.resolve().then(() => plotly.react(host, data, layout, PLOT_CONFIG)).then(
      (graph) => {
        if (cancelled) return;
        listen(graph); rememberView(graph); setDrawn(true);
      },
      (error: unknown) => { if (!cancelled) setFailure(errorText(error)); },
    );
    return () => { cancelled = true; };
  }, [plotly, points, measured, defaultView, librarySimilarity, totalDescriptors, selectedTrackId, playingTrackId, mapKey, themeRevision, attempt]);

  useEffect(() => {
    const host = hostRef.current;
    if (!plotly || !host || !drawn) return;
    const observer = new ResizeObserver(() => {
      void Promise.resolve().then(() => plotly.Plots.resize(host)).catch(() => undefined);
    });
    observer.observe(host);
    return () => observer.disconnect();
  }, [plotly, drawn]);

  useEffect(() => {
    const host = hostRef.current;
    if (!plotly || !host) return;
    return () => plotly.purge(host);
  }, [plotly]);

  useLayoutEffect(() => {
    const frame = frameRef.current;
    const tooltip = tooltipRef.current;
    if (!hover || !frame || !tooltip) { setTooltipPosition(null); return; }
    const size = tooltip.getBoundingClientRect();
    setTooltipPosition(placeTooltip(
      { left: hover.left - 8, top: hover.top - 8, width: 16, height: 16 },
      { width: size.width, height: size.height }, { width: frame.clientWidth, height: frame.clientHeight },
    ));
  }, [hover]);

  function listen(graph: PlotlyHTMLElement) {
    for (const name of ["plotly_click", "plotly_hover", "plotly_unhover", "plotly_relayout"]) graph.removeAllListeners(name);
    graph.on("plotly_click", (event: PlotMouseEvent) => {
      const point = callbacks.current.points[pointIndex(event.points[0])];
      if (point) { callbacks.current.onSelect(point.track.track_id); callbacks.current.onPreview(point.track); }
    });
    graph.on("plotly_hover", (event: PlotHoverEvent) => {
      const datum = event.points[0] as HoverDatum | undefined;
      const index = pointIndex(datum);
      const frame = frameRef.current;
      if (!datum || index < 0 || !frame) return;
      const box = frame.getBoundingClientRect();
      setHover({ index, left: datum.xPixel ?? event.event.clientX - box.left, top: datum.yPixel ?? event.event.clientY - box.top });
    });
    graph.on("plotly_unhover", () => setHover(null));
    graph.on("plotly_relayout", () => { rememberView(graph); setHover(null); });
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
    void plotly.relayout(host, { "xaxis.range": [...view.x], "yaxis.range": [...view.y] }).catch(() => undefined);
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

  return (
    <div className="cluster-map-plot-frame" ref={frameRef} onPointerLeave={() => setHover(null)}>
      <div ref={hostRef} className="cluster-map-plot" role="img" aria-label={`Сходство модели и независимое расхождение SONARA: ${measured.length} кандидатов. Те же измерения доступны в списке треков.`} />
      {!drawn && !failure ? <MapSkeleton /> : null}
      {drawn && measured.length === 0 ? <div className="cluster-map-plot-loading">Нет кандидатов с доступной проверкой SONARA. Все треки остаются в списке.</div> : null}
      {failure ? (
        <div className="cluster-map-plot-error" role="alert">
          <CircleAlert size={16} aria-hidden="true" /><span>Не удалось нарисовать карту: {failure}</span>
          <button type="button" onClick={() => setAttempt((value) => value + 1)}>Повторить</button>
        </div>
      ) : null}
      <div className="cluster-map-toolbar" role="toolbar" aria-label="Вид карты" aria-orientation="vertical" onKeyDown={moveToolbarFocus}>
        <button className="icon-button" type="button" title="Приблизить" aria-label="Приблизить" disabled={!drawn} onClick={() => zoom(0.8)}><ZoomIn size={15} /></button>
        <button className="icon-button" type="button" title="Отдалить" aria-label="Отдалить" disabled={!drawn} onClick={() => zoom(1.25)}><ZoomOut size={15} /></button>
        <button className="icon-button" type="button" title="Сбросить вид" aria-label="Сбросить вид" disabled={!drawn} onClick={() => showView(defaultView)}><RotateCcw size={15} /></button>
      </div>
      {hovered ? (
        <div ref={tooltipRef} className="cluster-map-tooltip" aria-hidden="true" style={tooltipPosition ? { left: tooltipPosition.left, top: tooltipPosition.top } : { left: 0, top: 0, visibility: "hidden" }}>
          <strong className="cluster-map-tooltip-name">{displayTrack(hovered.track)}</strong>
          <span>Модель {hovered.similarity.toFixed(3)} · SONARA P{hovered.sonara.percentile?.toFixed(1)}</span>
          <span className="cluster-map-tooltip-line">{describePoint(hovered)}</span>
        </div>
      ) : null}
    </div>
  );
}

function pointIndex(datum: PlotDatum | undefined) {
  return typeof datum?.customdata === "number" ? datum.customdata : -1;
}

function isRange(value: unknown): value is AxisRange {
  return Array.isArray(value) && value.length === 2 && value.every((item) => typeof item === "number" && Number.isFinite(item));
}

function moveToolbarFocus(event: KeyboardEvent<HTMLDivElement>) {
  const step = event.key === "ArrowDown" || event.key === "ArrowRight" ? 1 : event.key === "ArrowUp" || event.key === "ArrowLeft" ? -1 : 0;
  if (!step) return;
  const buttons = [...event.currentTarget.querySelectorAll<HTMLButtonElement>("button:not(:disabled)")];
  const current = buttons.findIndex((button) => button === document.activeElement);
  if (current < 0) return;
  event.preventDefault();
  buttons[(current + step + buttons.length) % buttons.length].focus();
}
