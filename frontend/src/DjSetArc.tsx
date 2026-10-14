import { useEffect, useRef, useState, type KeyboardEvent, type PointerEvent } from "react";
import type { DjSetBuildResponse, DjSetSlot, DjSetStage } from "./api";
import { djSetStageLabel, type DjSetSlotPlan } from "./djSetView";
import { displayTrack } from "./trackDisplay";

type IntensityEdit = { intensity_start?: number; intensity_end?: number };
type Handle = { stage: number; x: number; value: number; label: string; apply: (value: number) => IntensityEdit };

/** Slot centres and values in the 0..100 box the SVG and the overlay share. */
function slotX(index: number, count: number) {
  return ((index + 0.5) / count) * 100;
}

function intensityY(value: number) {
  return (1 - Math.min(1, Math.max(0, value))) * 100;
}

function linePath(points: [number, number][]) {
  return points.map(([x, y], index) => `${index ? "L" : "M"}${x.toFixed(2)},${y.toFixed(2)}`).join(" ");
}

/** The shape of the set: the planned intensity and tempo of every slot.
 * In "shape" mode its vertices are handles that drag the stage targets; in
 * "set" mode the built tracks sit on it, and a dot plays its track. */
export function DjSetArc({ preset, stages, plan, result, playingTrackId, onIntensityChange, onSlotSelect }: {
  preset: string;
  stages: DjSetStage[];
  plan: DjSetSlotPlan[];
  result: DjSetBuildResponse | null;
  playingTrackId: number | null;
  onIntensityChange: (stage: number, edit: IntensityEdit) => void;
  onSlotSelect: (slot: DjSetSlot) => void;
}) {
  const canvasRef = useRef<HTMLDivElement | null>(null);
  const builtSlots = result?.slots ?? [];
  const [mode, setMode] = useState<"shape" | "set">("shape");
  const showSet = mode === "set" && builtSlots.length > 0;

  // A finished build turns the chart to what it built.
  useEffect(() => {
    setMode(result?.slots.length ? "set" : "shape");
  }, [result?.seed, result?.slots.length]);

  const count = plan.length;
  const tempos = [...plan.map((slot) => slot.bpm), ...(showSet ? builtSlots.map((slot) => slot.score_breakdown.bpm) : [])];
  const bpmLow = Math.min(...tempos) - 1;
  const bpmHigh = Math.max(...tempos) + 1;
  const bpmY = (bpm: number) => (1 - (bpm - bpmLow) / (bpmHigh - bpmLow)) * 100;

  const target: [number, number][] = plan.map((slot, index) => [slotX(index, count), intensityY(slot.intensity)]);
  const tempo: [number, number][] = plan.map((slot, index) => [slotX(index, count), bpmY(slot.bpm)]);
  const actual: [number, number][] = builtSlots.map((slot, index) => [
    slotX(index, builtSlots.length),
    intensityY(slot.score),
  ]);
  const area = `${linePath(target)} L${target[count - 1][0].toFixed(2)},100 L${target[0][0].toFixed(2)},100 Z`;

  const bands = stages.map((stage, index) => {
    const first = plan.findIndex((slot) => slot.stage === index);
    const size = plan.filter((slot) => slot.stage === index).length;
    return { key: stage.key, first, size, label: djSetStageLabel(preset, stage.key) };
  });

  const handles: Handle[] = bands.flatMap(({ first, size, label }, index): Handle[] => {
    const stage = stages[index];
    if (size === 1) {
      const spread = (stage.intensity_end - stage.intensity_start) / 2;
      return [{
        stage: index,
        x: slotX(first, count),
        value: plan[first].intensity,
        label,
        apply: (value) => ({
          intensity_start: Math.min(1, Math.max(0, value - spread)),
          intensity_end: Math.min(1, Math.max(0, value + spread)),
        }),
      }];
    }
    return [
      { stage: index, x: slotX(first, count), value: stage.intensity_start, label: `${label}, вход`, apply: (value) => ({ intensity_start: value }) },
      { stage: index, x: slotX(first + size - 1, count), value: stage.intensity_end, label: `${label}, выход`, apply: (value) => ({ intensity_end: value }) },
    ];
  });

  function commit(handle: Handle, value: number) {
    const rounded = Math.round(Math.min(1, Math.max(0, value)) * 100) / 100;
    const edit = handle.apply(rounded);
    onIntensityChange(handle.stage, Object.fromEntries(
      Object.entries(edit).map(([field, next]) => [field, Math.round(next * 100) / 100]),
    ));
  }

  function drag(handle: Handle, event: PointerEvent<HTMLButtonElement>) {
    if (!event.currentTarget.hasPointerCapture(event.pointerId)) return;
    const box = canvasRef.current?.getBoundingClientRect();
    if (!box || box.height <= 0) return;
    commit(handle, 1 - (event.clientY - box.top) / box.height);
  }

  function nudge(handle: Handle, event: KeyboardEvent<HTMLButtonElement>) {
    const step = event.shiftKey ? 0.05 : 0.01;
    const delta = event.key === "ArrowUp" ? step : event.key === "ArrowDown" ? -step : 0;
    if (!delta) return;
    event.preventDefault();
    commit(handle, handle.value + delta);
  }

  return (
    <div className="djset-arc">
      <div className="djset-arc-stages" aria-hidden="true">
        {bands.map(({ key, size, label }) => (
          <span key={key} style={{ flex: `${size} 0 0` }} title={label}>{label}</span>
        ))}
      </div>
      <div className="djset-arc-plot">
        <span className="djset-arc-axis djset-arc-axis-top">плотно</span>
        <span className="djset-arc-axis djset-arc-axis-bottom">спокойно</span>
        <span className="djset-arc-axis djset-arc-axis-bpm-top">{Math.round(bpmHigh)} BPM</span>
        <span className="djset-arc-axis djset-arc-axis-bpm-bottom">{Math.round(bpmLow)}</span>
        <div className="djset-arc-canvas" ref={canvasRef}>
          <svg viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
            {bands.map(({ key, first, size }, index) => (
              <rect
                key={key}
                className={index % 2 ? "djset-arc-band alt" : "djset-arc-band"}
                x={(first / count) * 100}
                y={0}
                width={(size / count) * 100}
                height={100}
              />
            ))}
            <path className="djset-arc-area" d={area} />
            <path className="djset-arc-tempo" d={linePath(tempo)} />
            <path className="djset-arc-line" d={linePath(target)} />
            {showSet ? <path className="djset-arc-actual" d={linePath(actual)} /> : null}
          </svg>
          {showSet ? builtSlots.map((slot, index) => (
            <i
              key={slot.slot}
              className="djset-arc-tempo-tick"
              style={{ left: `${actual[index][0]}%`, top: `${bpmY(slot.score_breakdown.bpm)}%` }}
            />
          )) : null}
          {showSet ? builtSlots.map((slot, index) => {
            const playing = playingTrackId === slot.track.track_id;
            const classes = [
              "djset-arc-dot",
              slot.out_of_tolerance ? "is-out" : "",
              slot.pinned ? "is-pinned" : "",
              playing ? "is-playing" : "",
            ].filter(Boolean).join(" ");
            const about = `${slot.slot} · ${djSetStageLabel(result?.preset ?? preset, slot.stage)} · ${slot.score_breakdown.bpm.toFixed(1)} BPM · ${displayTrack(slot.track)}`;
            return (
              <button
                key={slot.slot}
                className={classes}
                style={{ left: `${actual[index][0]}%`, top: `${actual[index][1]}%` }}
                title={`${about}${slot.out_of_tolerance ? " · темп вне допуска" : ""}`}
                aria-label={`${playing ? "Пауза" : "Слушать"}: ${about}`}
                aria-pressed={playing}
                onClick={() => onSlotSelect(slot)}
                type="button"
              />
            );
          }) : handles.map((handle) => (
            <button
              key={`${handle.stage}:${handle.label}`}
              className="djset-arc-handle"
              style={{ left: `${handle.x}%`, top: `${intensityY(handle.value)}%` }}
              title={`${handle.label}: интенсивность ${handle.value.toFixed(2)}. Тяните вверх или вниз; стрелки меняют на 0,01, с Shift — на 0,05.`}
              aria-label={`Интенсивность, ${handle.label}`}
              aria-valuemin={0}
              aria-valuemax={1}
              aria-valuenow={Number(handle.value.toFixed(2))}
              aria-orientation="vertical"
              role="slider"
              onPointerDown={(event) => event.currentTarget.setPointerCapture(event.pointerId)}
              onPointerMove={(event) => drag(handle, event)}
              onKeyDown={(event) => nudge(handle, event)}
              type="button"
            />
          ))}
        </div>
      </div>
      <div className="djset-arc-legend">
        <span className="djset-arc-key djset-arc-key-intensity">интенсивность</span>
        <span className="djset-arc-key djset-arc-key-tempo">темп</span>
        {showSet ? <span className="djset-arc-key djset-arc-key-track">треки сета</span> : null}
        <div className="segmented djset-arc-mode" role="group" aria-label="Что показывает график">
          <button
            className={showSet ? "" : "active"}
            aria-pressed={!showSet}
            title="Показать форму сета. Точки на кривой тянутся мышью или стрелками и меняют интенсивность этапов."
            onClick={() => setMode("shape")}
            type="button"
          >
            Форма
          </button>
          <button
            className={showSet ? "active" : ""}
            aria-pressed={showSet}
            disabled={!builtSlots.length}
            title={builtSlots.length
              ? "Показать собранный сет поверх формы. Точка — трек; нажмите, чтобы его послушать."
              : "Сначала соберите сет: его треки лягут на эту кривую."}
            onClick={() => setMode("set")}
            type="button"
          >
            Сет
          </button>
        </div>
      </div>
    </div>
  );
}
