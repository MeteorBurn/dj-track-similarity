import { memo, useEffect, useId, useMemo, useRef, useState } from "react";
import type { SheetSage2MelodySource, SheetSage2TimelineResponse, TrackIdentity } from "./api";
import { api, ApiError } from "./apiClient";
import { usePreviewPosition } from "./previewPosition";
import { buildSheetSage2Timeline, type SheetSage2Interval } from "./sheetsageTimelineData";

function clock(seconds: number) {
  const whole = Math.floor(Math.max(0, seconds));
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, "0")}`;
}

function sectionTone(label: string) {
  const common: Record<string, number> = { intro: 4, outro: 4, verse: 1, chorus: 3, "pre-chorus": 0, bridge: 2 };
  const known = common[label.toLowerCase()];
  if (known != null) return known;
  return Array.from(label).reduce((sum, letter) => sum + letter.charCodeAt(0), 0) % 4;
}

type TimelineProps = { track: TrackIdentity; expanded: boolean; onSeek: (seconds: number) => void };

export function SheetSage2Timeline(props: TimelineProps) {
  const { catalog_uuid, track_uuid, track_id } = props.track;
  const identity = `${catalog_uuid}:${track_uuid}:${track_id}`;
  const [state, setState] = useState<{ identity: string; data?: SheetSage2TimelineResponse; error?: string; missing?: boolean }>();
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setState({ identity });
    void api.sheetsage2Timeline({ catalog_uuid, track_uuid, track_id }, controller.signal).then(data => {
      if (controller.signal.aborted) return;
      if (data.catalog_uuid !== catalog_uuid || data.track_uuid !== track_uuid || data.track_id !== track_id) {
        setState({ identity, error: "Библиотека или трек изменились. Откройте карточку заново." });
      } else setState({ identity, data });
    }).catch((error: unknown) => {
      if (controller.signal.aborted) return;
      setState({ identity, missing: error instanceof ApiError && error.status === 404,
        error: error instanceof Error ? error.message : "Не удалось загрузить SheetSage2 timeline" });
    });
    return () => controller.abort();
  }, [catalog_uuid, track_uuid, track_id, identity, retry]);
  return <section className="sheetsage-timeline" aria-label="Структура трека SheetSage2">
    {state?.identity !== identity || (!state.data && !state.error) ? <p className="metadata-empty-state" role="status">Загрузка структуры трека…</p>
      : state.missing ? <p className="metadata-empty-state">SheetSage2 timeline ещё не рассчитан</p>
      : state.error ? <div className="sheetsage-timeline-error" role="alert">{state.error} <button type="button" onClick={() => setRetry(value => value + 1)}>Повторить</button></div>
      : state.data ? <TimelineView key={identity} data={state.data} expanded={props.expanded} onSeek={props.onSeek} /> : null}
  </section>;
}

type Data = ReturnType<typeof buildSheetSage2Timeline>;
type Geometry = { width: number; left: number; plot: number; tops: number[]; heights: number[]; height: number };

function preciseTime(seconds: number) {
  const ms = Math.round(Math.max(0, seconds) * 1000);
  return `${Math.floor(ms / 60000)}:${((ms % 60000) / 1000).toFixed(3).padStart(6, "0")}`;
}

function TimelineHover({ data, geometry: g, start, end, notes, yPitch, yTempo }: {
  data: Data; geometry: Geometry; start: number; end: number;
  notes: Data["notes"]; yPitch: (pitch: number) => number; yTempo: (bpm: number) => number;
}) {
  const [hover, setHover] = useState<{
    name: string; start: number; end: number; x: number; y: number;
    time?: number; bpm?: number;
  } | null>(null);
  const width = Math.min(286, g.width - 8);
  return <g>
    <rect x={g.left} y={28} width={g.plot} height={g.height - 28} fill="transparent"
      onPointerLeave={() => setHover(null)}
      onPointerMove={event => {
        const bounds = event.currentTarget.ownerSVGElement!.getBoundingClientRect();
        const px = (event.clientX - bounds.left) * g.width / bounds.width;
        const py = (event.clientY - bounds.top) * g.height / bounds.height;
        const time = start + (px - g.left) / g.plot * (end - start);
        const row = g.tops.findIndex((top, i) => py >= top && py <= top + g.heights[i]);
        const base = { x: px, y: py };
        if (row === 1) {
          const segment = data.tempo.find(item => time >= item.start && time < item.end);
          setHover(segment ? { ...base, name: "Tempo", ...segment, time } : null);
        } else if (row === 3) {
          const tolerance = 4 / g.plot * (end - start);
          const note = notes.filter(item => time >= item.start_s - tolerance && time <= item.end_s + tolerance
            && Math.abs(yPitch(item.pitch_midi) - py) <= 7)
            .sort((a, b) => Math.abs(yPitch(a.pitch_midi) - py) - Math.abs(yPitch(b.pitch_midi) - py)
              || Math.abs(time - (a.start_s + a.end_s) / 2) - Math.abs(time - (b.start_s + b.end_s) / 2))[0];
          const names = ["C", "C♯", "D", "D♯", "E", "F", "F♯", "G", "G♯", "A", "A♯", "B"];
          setHover(note ? { ...base, name: `${names[note.pitch_midi % 12]}${Math.floor(note.pitch_midi / 12) - 1} · MIDI ${note.pitch_midi} · ${note.source_track === "vocal" ? "Vocal" : "Instrumental"}`, start: note.start_s, end: note.end_s } : null);
        } else {
          const intervals = row === 0 ? data.structure : row === 4 ? data.chord : row === 5 ? data.key : [];
          const segment = intervals.find(item => time >= item.start && time < item.end);
          setHover(segment ? { ...base, name: segment.label, start: segment.start, end: segment.end } : null);
        }
      }} />
    {hover && <g pointerEvents="none">
      {hover.bpm !== undefined && <circle cx={hover.x} cy={yTempo(hover.bpm)} r={3} className="sheetsage-tempo-hover" />}
      <foreignObject x={Math.max(4, Math.min(g.width - width - 4, hover.x + 12))}
        y={Math.max(2, Math.min(g.height - 116, hover.y - 120))} width={width} height={116}>
        <div className="sheetsage-hover" role="tooltip">
          <strong>{hover.name}{hover.bpm !== undefined ? ` · ${hover.bpm.toFixed(3).replace(/\.?0+$/, "")} BPM` : ""}</strong>
          {hover.time !== undefined && <span>Позиция: {preciseTime(hover.time)}</span>}
          <span>Начало: {preciseTime(hover.start)}</span>
          <span>Конец: {preciseTime(hover.end)}</span>
          <span>Длительность: {Number((hover.end - hover.start).toFixed(3))} с</span>
        </div>
      </foreignObject>
    </g>}
  </g>;
}

const TimelineMarks = memo(function TimelineMarks({ data, geometry: g, start, end, source }: {
  data: Data; geometry: Geometry; start: number; end: number; source: SheetSage2MelodySource;
}) {
  const clip = useId();
  const x = (time: number) => g.left + (time - start) / (end - start) * g.plot;
  const visibleTempo = data.tempo.filter(item => item.end > start && item.start < end);
  const tempoBounds = visibleTempo.reduce(([min, max], item) => [Math.min(min, item.bpm), Math.max(max, item.bpm)], [Infinity, -Infinity]);
  const tempoMin = Number.isFinite(tempoBounds[0]) ? Math.floor(tempoBounds[0] - 1) : 0;
  const tempoMax = Number.isFinite(tempoBounds[1]) ? Math.ceil(tempoBounds[1] + 1) : 1;
  const notes = data.notes.filter(note => note.end_s > start && note.start_s < end && (source === "all" || source === note.source_track));
  const pitches = notes.reduce(([min, max], note) => [Math.min(min, note.pitch_midi), Math.max(max, note.pitch_midi)], [Infinity, -Infinity]);
  const pitchMin = Number.isFinite(pitches[0]) ? Math.max(0, pitches[0] - 2) : 48;
  const pitchMax = Number.isFinite(pitches[1]) ? Math.min(127, pitches[1] + 2) : 72;
  const yTempo = (bpm: number) => g.tops[1] + 12 + (tempoMax - bpm) / (tempoMax - tempoMin) * (g.heights[1] - 24);
  const yPitch = (pitch: number) => g.tops[3] + 10 + (pitchMax - pitch) / Math.max(1, pitchMax - pitchMin) * (g.heights[3] - 20);
  const rawStep = (end - start) / Math.max(2, Math.floor(g.plot / 85));
  const magnitude = 10 ** Math.floor(Math.log10(rawStep));
  const step = ([1, 2, 5, 10].find(n => n * magnitude >= rawStep) ?? 10) * magnitude;
  const ticks = Array.from({ length: Math.ceil((end - start) / step) + 1 }, (_, i) => (Math.ceil(start / step) + i) * step).filter(t => t <= end);
  const intervalRows: [SheetSage2Interval[], number, string][] = [[data.structure, 0, "structure"], [data.chord, 4, "chord"], [data.key, 5, "key"]];
  return <>
    <defs><clipPath id={clip}><rect x={g.left} y={28} width={g.plot} height={g.height - 28} /></clipPath></defs>
    {["Structure", "Tempo", "Rhythm", "Melody", "Chord", "Key"].map((label, i) => <g key={label}>
      <text x={0} y={g.tops[i] + 15} className="sheetsage-track-label">{label}</text>
      <rect x={g.left} y={g.tops[i]} width={g.plot} height={g.heights[i]} rx={3} className="sheetsage-track-bg" data-lane={i} />
    </g>)}
    {ticks.map(t => <g key={t}><line x1={x(t)} x2={x(t)} y1={28} y2={g.height - 8} className="sheetsage-grid" /><text x={x(t)} y={17} textAnchor={x(t) < g.left + 22 ? "start" : x(t) > g.width - 35 ? "end" : "middle"} className="sheetsage-axis-label">{step < 1 ? t.toFixed(1) + "s" : clock(t)}</text></g>)}
    <text x={0} y={g.tops[1] + 32} className="sheetsage-axis-label">BPM</text>
    <text x={0} y={g.tops[3] + 32} className="sheetsage-axis-label">MIDI</text>
    {visibleTempo.length > 0 && [tempoMin, tempoMax].map(bpm => <text key={bpm} x={g.left - 7} y={yTempo(bpm) + 4} textAnchor="end" className="sheetsage-axis-label">{bpm}</text>)}
    {notes.length > 0 && [pitchMin, pitchMax].map(pitch => <text key={pitch} x={g.left - 7} y={yPitch(pitch) + 4} textAnchor="end" className="sheetsage-axis-label">{pitch}</text>)}
    <g clipPath={`url(#${clip})`}>
      {intervalRows.map(([intervals, row, family]) => <g key={family}>{intervals.filter(item => item.end > start && item.start < end).map((item, index) => {
        const left = x(Math.max(start, item.start)), width = x(Math.min(end, item.end)) - left;
        return <g key={`${item.start}:${index}`} className={`sheetsage-interval sheetsage-${family}`} data-tone={sectionTone(item.label)}>
          <rect x={left} y={g.tops[row] + 4} width={width} height={g.heights[row] - 8} rx={2}><title>{item.label} · {clock(item.start)}–{clock(item.end)}</title></rect>
          {width > item.label.length * 7 + 12 && <text x={left + width / 2} y={g.tops[row] + g.heights[row] / 2 + 4} textAnchor="middle">{item.label}</text>}
        </g>;
      })}</g>)}
      <path className="sheetsage-tempo-line" d={visibleTempo.map(item => `M${x(item.start)},${yTempo(item.bpm)}H${x(item.end)}`).join(" ")} />
      {[false, true].map(downbeat => <path key={String(downbeat)} className={downbeat ? "sheetsage-downbeat" : "sheetsage-beat"} d={data.beats.filter(beat => beat.time >= start && beat.time <= end && (beat.position === 0) === downbeat).map(beat => `M${x(beat.time)},${g.tops[2] + (downbeat ? 22 : 30)}V${g.tops[2] + g.heights[2] - 5}`).join(" ")} />)}
      {data.meters.map((meter, index) => {
        const stop = data.meters[index + 1]?.time ?? end;
        const left = x(Math.max(start, meter.time)), right = x(Math.min(end, stop));
        return stop > start && meter.time < end && right - left > 35 ? <text key={meter.time} x={left + 5} y={g.tops[2] + 14} className="sheetsage-axis-label">{meter.label ?? "?"}</text> : null;
      })}
      {(["vocal", "instrumental"] as const).map(part => <path key={part} className={`sheetsage-note sheetsage-note-${part}`} d={notes.filter(note => note.source_track === part).map(note => `M${x(note.start_s)},${yPitch(note.pitch_midi)}H${x(note.end_s)}`).join(" ")} />)}
    </g>
    {!visibleTempo.length && <text x={g.left + 8} y={g.tops[1] + g.heights[1] / 2} className="sheetsage-axis-label">Нет данных темпа</text>}
    {!notes.length && <text x={g.left + 8} y={g.tops[3] + g.heights[3] / 2} className="sheetsage-axis-label">Нет нот в участке</text>}
    <TimelineHover key={`${start}:${end}:${source}`} data={data} geometry={g} start={start} end={end} notes={notes} yPitch={yPitch} yTempo={yTempo} />
  </>;
});

function TimelineView({ data: response, expanded, onSeek }: { data: SheetSage2TimelineResponse; expanded: boolean; onSeek: (seconds: number) => void }) {
  const data = useMemo(() => buildSheetSage2Timeline(response.events), [response.events]);
  const [source, setSource] = useState<SheetSage2MelodySource>("all");
  const [window, setWindow] = useState<[number, number]>([0, response.duration_s]);
  const [width, setWidth] = useState(600);
  const box = useRef<HTMLDivElement>(null);
  const position = usePreviewPosition();
  const current = position.trackId === response.track_id ? Math.min(response.duration_s, position.currentTime) : 0;
  const [start, end] = window;
  const span = end - start, duration = response.duration_s;
  useEffect(() => {
    const element = box.current;
    if (!element) return;
    const observer = new ResizeObserver(entries => setWidth(Math.max(220, entries[0].contentRect.width)));
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  const geometry = useMemo(() => {
    const heights = expanded ? [56, 96, 62, 150, 52, 48] : [42, 70, 46, 90, 42, 40];
    let top = 34;
    const tops = heights.map(height => { const y = top; top += height + 12; return y; });
    const left = width < 480 ? 86 : 106;
    return { width, left, plot: Math.max(1, width - left - 10), heights, tops, height: top };
  }, [width, expanded]);
  const x = (time: number) => geometry.left + (time - start) / span * geometry.plot;
  const zoom = (factor: number) => {
    const nextSpan = Math.min(duration, Math.max(Math.min(1, duration), span * factor));
    const center = current >= start && current <= end ? current : (start + end) / 2;
    const nextStart = Math.min(duration - nextSpan, Math.max(0, center - nextSpan / 2));
    setWindow([nextStart, nextStart + nextSpan]);
  };
  const at = (items: SheetSage2Interval[]) => items.find(item => current >= item.start && current < item.end);
  const section = at(data.structure), chord = at(data.chord), key = at(data.key);
  let meter: string | null = null;
  for (const item of data.meters) {
    if (item.time > current) break;
    meter = item.label;
  }
  return <>
    <div className="sheetsage-toolbar"><strong>Структура трека</strong><div className="feature-badges">
      <button type="button" className="feature-badge" onClick={() => zoom(.5)} disabled={span <= Math.min(1, duration)} aria-label="Приблизить участок">+</button>
      <button type="button" className="feature-badge" onClick={() => zoom(2)} disabled={span >= duration} aria-label="Отдалить участок">−</button>
      <button type="button" className="feature-badge" onClick={() => setWindow([0, duration])}>Весь трек</button>
      <span>{clock(start)}–{clock(end)}</span>
    </div></div>
    {(expanded || span < duration) && <div className="sheetsage-overview">
      <span>Весь трек · {clock(duration)}</span>
      <svg width="100%" height={26} viewBox="0 0 1000 26" preserveAspectRatio="none" role="img" aria-label="Обзор секций и видимого участка" onClick={event => {
        const rect = event.currentTarget.getBoundingClientRect();
        const nextStart = Math.min(duration - span, Math.max(0, (event.clientX - rect.left) / rect.width * duration - span / 2));
        setWindow([nextStart, nextStart + span]);
      }}>
        {data.structure.map((item, index) => <rect key={index} x={item.start / duration * 1000} y={4} width={(item.end - item.start) / duration * 1000} height={18} className="sheetsage-overview-section" data-tone={sectionTone(item.label)}><title>{`${item.label}\nНачало: ${preciseTime(item.start)}\nКонец: ${preciseTime(item.end)}\nДлительность: ${Number((item.end - item.start).toFixed(3))} с`}</title></rect>)}
        <rect x={start / duration * 1000} y={1} width={span / duration * 1000} height={24} className="sheetsage-overview-window" />
      </svg>
    </div>}
    <div className="sheetsage-window-controls">
      <label>Начало, с <input type="number" min={0} max={Math.max(0, end - .1)} step={.1} value={Number(start.toFixed(2))} onChange={event => {
        const value = event.target.valueAsNumber;
        if (Number.isFinite(value)) setWindow([Math.max(0, Math.min(end - .1, value)), end]);
      }} /></label>
      <label>Конец, с <input type="number" min={start + .1} max={duration} step={.1} value={Number(end.toFixed(2))} onChange={event => {
        const value = event.target.valueAsNumber;
        if (Number.isFinite(value)) setWindow([start, Math.min(duration, Math.max(start + .1, value))]);
      }} /></label>
      {span < duration && <label className="sheetsage-pan">Перемещение <input type="range" aria-label="Перемещение видимого участка" min={0} max={duration - span} step={.1} value={start} onChange={event => { const value = Number(event.target.value); setWindow([value, value + span]); }} /></label>}
    </div>
    <div ref={box} className="sheetsage-chart">
      <svg width={geometry.width} height={geometry.height} role="img" aria-label="Structure, Tempo в BPM, Rhythm, Melody в MIDI, Chord и Key на общей шкале времени" onClick={event => {
        const rect = event.currentTarget.getBoundingClientRect();
        const local = event.clientX - rect.left;
        if (local >= geometry.left) onSeek(Math.min(end, Math.max(start, start + (local - geometry.left) / geometry.plot * span)));
      }}>
        <TimelineMarks data={data} geometry={geometry} start={start} end={end} source={source} />
        {position.trackId === response.track_id && current >= start && current <= end && <line x1={x(current)} x2={x(current)} y1={28} y2={geometry.height - 8} className="sheetsage-cursor" />}
      </svg>
    </div>
    <div className="sheetsage-toolbar"><div className="feature-badges" role="group" aria-label="Мелодическая партия на карте"><span>Melody</span>
      {(["all", "vocal", "instrumental"] as const).map(part => <button type="button" className="feature-badge" key={part} aria-pressed={source === part} onClick={() => setSource(part)}>{part === "all" ? "All" : part === "vocal" ? "Vocal" : "Instrumental"}</button>)}
    </div><span className="sheetsage-legend"><span>━ Vocal</span><span>┄ Instrumental</span></span></div>
    <label className="sheetsage-position">Позиция {clock(current)}<input type="range" min={0} max={duration} step={.1} value={current} aria-label="Позиция на временной шкале" onChange={event => onSeek(Number(event.target.value))} /></label>
    <div className="sheetsage-selection"><strong>{section?.label ?? "Нет секции"}</strong><span>{section ? `${clock(section.start)}–${clock(section.end)}` : "–"}</span><span>{key?.label ?? "Нет тональности"} · {chord?.label ?? "Нет аккорда"}</span><span>{meter ?? "–"}</span></div>
    {response.warnings.length > 0 && <details className="sheetsage-warnings"><summary>Предупреждения анализа ({response.warnings.length})</summary><ul>{response.warnings.map((warning, index) => <li key={index}>{warning}</li>)}</ul></details>}
  </>;
}
