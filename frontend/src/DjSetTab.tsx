import { useEffect, useState } from "react";
import { Dices, ListMusic, Pin } from "lucide-react";
import type { DjSetBuildResponse, DjSetDirectionAxis, DjSetDirectionRelation, DjSetSlot, DjSetStage } from "./api";
import { DjSetArc } from "./DjSetArc";
import {
  djSetFunnelLabel,
  djSetPresetName,
  djSetPresetShortName,
  djSetPresetSummary,
  djSetRuleTraces,
  djSetStageLabel,
  djSetStageRules,
  type DjSetStageField,
} from "./djSetView";
import { seedSearchModelPresentation, type SeedEmbeddingFamily } from "./searchSurfaceState";
import { displayTrack } from "./trackDisplay";
import type { DjSetSeedRole, DjSetState } from "./useDjSet";

const roleChoices: { key: DjSetSeedRole; label: string; title: string }[] = [
  {
    key: "reference",
    label: "ориентир",
    title: "Выберите, чтобы трек задал породу сета. Сам он в сет не попадёт; на него опираются «Порода» и «Смещение».",
  },
  {
    key: "pinned",
    label: "в сет",
    title: "Выберите, чтобы трек вошёл в сет. Слот для него подберёт алгоритм.",
  },
  {
    key: "slot",
    label: "слот",
    title: "Выберите, чтобы закрепить трек за слотом. Номер слота укажите в поле справа.",
  },
];

const axisChoices: { key: DjSetDirectionAxis; label: string }[] = [
  { key: "energy", label: "энергия" },
  { key: "valence", label: "настроение" },
  { key: "acousticness", label: "акустичность" },
  { key: "brightness", label: "яркость" },
  { key: "rhythm_density", label: "плотность ритма" },
  { key: "dynamic_range", label: "динамический диапазон" },
  { key: "loudness", label: "громкость" },
  { key: "aggression", label: "агрессия" },
];

const relationChoices: { key: DjSetDirectionRelation; label: string }[] = [
  { key: "lower", label: "ниже" },
  { key: "similar", label: "как у ориентира" },
  { key: "higher", label: "выше" },
];

const stageColumns: { field: DjSetStageField; label: string; name: string; step: number; title: string }[] = [
  {
    field: "share",
    label: "доля",
    name: "Доля",
    step: 1,
    title: "Укажите долю сета для этапа: больше 0 и до 100. Чем больше доля, тем больше треков достанется этапу; доли нормируются по их сумме.",
  },
  {
    field: "intensity_start",
    label: "инт. от",
    name: "Интенсивность на входе",
    step: 0.01,
    title: "Укажите интенсивность первого трека этапа: от 0 (спокойно) до 1 (плотно). Выше — этап начинается плотнее.",
  },
  {
    field: "intensity_end",
    label: "до",
    name: "Интенсивность на выходе",
    step: 0.01,
    title: "Укажите интенсивность последнего трека этапа: от 0 до 1. Выше входной — этап нарастает, ниже — затихает.",
  },
  {
    field: "bpm_start",
    label: "BPM от",
    name: "BPM на входе",
    step: 0.5,
    title: "Укажите темп первого трека этапа: от 60 до 200. Резкий шаг вниз от предыдущего этапа алгоритм сводит через брейкдаун.",
  },
  {
    field: "bpm_end",
    label: "до",
    name: "BPM на выходе",
    step: 0.5,
    title: "Укажите темп последнего трека этапа: от 60 до 200. Между входом и выходом темп меняется равными шагами.",
  },
];

/** An empty or half-typed number field is null, never a guessed number. */
function numberOrNull(input: HTMLInputElement) {
  return Number.isFinite(input.valueAsNumber) ? input.valueAsNumber : null;
}

function NumberField({ label, name, value, minimum, maximum, step = 1, placeholder, title, disabled = false, onChange }: {
  label: string;
  name: string;
  value: number | null;
  minimum: number;
  maximum: number;
  step?: number;
  placeholder?: string;
  title: string;
  disabled?: boolean;
  onChange: (value: number | null) => void;
}) {
  return (
    <label className={disabled ? "disabled-filter" : undefined} title={title}>
      {label}
      <input
        name={name}
        type="number"
        min={minimum}
        max={maximum}
        step={step}
        value={value ?? ""}
        placeholder={placeholder}
        title={title}
        disabled={disabled}
        onChange={(event) => onChange(numberOrNull(event.currentTarget))}
      />
    </label>
  );
}

/** The outline of a preset, from its own stage numbers: every stage takes
 * its share of the width and runs from its entry intensity to its exit. The
 * rules of its stages (key walk, classifier ranges) are dashed steps. */
function PresetOutline({ stages }: { stages: DjSetStage[] }) {
  const total = stages.reduce((sum, stage) => sum + stage.share, 0);
  let passed = 0;
  const spans = stages.map((stage) => {
    const from = (passed / total) * 100;
    passed += stage.share;
    return { from, to: (passed / total) * 100 };
  });
  const y = (value: number) => ((1 - value) * 100).toFixed(1);
  const outline = stages.flatMap((stage, index) => {
    const { from, to } = spans[index];
    const inset = (to - from) * 0.18;
    return [`${(from + inset).toFixed(1)},${y(stage.intensity_start)}`, `${(to - inset).toFixed(1)},${y(stage.intensity_end)}`];
  });
  return (
    <svg viewBox="0 -6 100 112" preserveAspectRatio="none" aria-hidden="true">
      {djSetRuleTraces(stages).map((trace, index) => (
        <path
          key={index}
          className="djset-preset-rule"
          d={`M${trace.flatMap((value, stage) => [`${spans[stage].from.toFixed(1)},${y(value)}`, `${spans[stage].to.toFixed(1)},${y(value)}`]).join(" L")}`}
        />
      ))}
      <path d={`M${outline.join(" L")}`} />
    </svg>
  );
}

/** How many candidates each gate left, as bars against the first count. */
export function DjSetFunnel({ funnel }: { funnel: DjSetBuildResponse["funnel"] }) {
  const first = funnel[0]?.remaining || 1;
  return (
    <div className="djset-funnel" role="list" aria-label="Сколько кандидатов осталось после каждого отбора">
      {funnel.map(({ key, remaining }) => (
        <div className="djset-funnel-row" role="listitem" key={key}>
          <span>{djSetFunnelLabel(key)}</span>
          <span className="djset-funnel-bar"><i style={{ width: `${(remaining / first) * 100}%` }} /></span>
          <b>{remaining.toLocaleString("ru-RU")}</b>
        </div>
      ))}
    </div>
  );
}

/** The DJ SET tab: how the set develops, who steers it, and the build. The
 * built set is not listed here: the panel shows it below, in the shared
 * result list. */
export function DjSetTab({ djSet, busy, playingTrackId, onSlotSelect }: {
  djSet: DjSetState;
  busy: boolean;
  playingTrackId: number | null;
  onSlotSelect: (slot: DjSetSlot) => void;
}) {
  const { settings, setSetting, references, hasReference, poolModels, poolModel, pendingSince, presets, presetKey, stages, plan } = djSet;
  const pending = pendingSince !== null;
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (pendingSince === null) return;
    setNow(Date.now());
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [pendingSince]);

  const elapsedSeconds = pendingSince === null ? 0 : Math.max(0, Math.floor((now - pendingSince) / 1000));
  const maxSlot = settings.tracks ?? 60;
  const builtSeed = djSet.result?.seed ?? null;
  const needsReference = hasReference ? "" : "Считается от ориентира: добавьте seed-трек лупой в строке трека — он станет ориентиром.";
  const poolModelDisabled = !hasReference || !poolModels.length;
  const poolModelTitle = needsReference || (poolModel
    ? `Выберите модель, которая отбирает в пул треки, похожие на ориентиры. ${seedSearchModelPresentation[poolModel].description}`
    : "В библиотеке нет эмбеддингов: запустите ML-анализ, чтобы отбирать пул по ориентирам.");
  const poolSizeTitle = needsReference
    || "Укажите размер пула: сколько ближайших к ориентирам треков остаются кандидатами, от 100 до 20000. Малый пул строже держит породу, большой даёт больше выбора.";
  const axisTitle = needsReference
    || "Выберите свойство SONARA, по которому сет сдвигается относительно ориентиров. «нет» — без смещения.";
  const relationTitle = needsReference
    || "Выберите, куда сдвинуть сет по этому свойству: ниже, как у ориентира или выше.";
  const marginTitle = needsReference
    || "Укажите запас в процентильных пунктах библиотеки: от 0 до 50. Для «ниже» и «выше» это минимальный сдвиг от ориентира, для «как у ориентира» — допустимое отклонение.";
  const varietyTitle = "Укажите долю случайности при выборе треков: от 0 до 1. При 0 сборка берёт лучших кандидатов, выше — сеты разнообразнее от сборки к сборке.";
  const buildTitle = busy
    ? "Дождитесь завершения текущей операции"
    : pending
      ? "Сет собирается: обычно это занимает до полуминуты."
      : djSet.problem || "Собрать сет по этим настройкам. Он появится списком ниже и заменит показанный.";

  return (
    <>
      <section className="djset-section" aria-label="Развитие сета">
        <div className="custom-control-header">
          <div className="custom-control-copy">
            <span>Развитие</span>
            <small>
              {presetKey
                ? `— ${djSetPresetName(presetKey)}. ${djSetPresetSummary(presetKey)}`
                : "— как сет движется от первого трека к последнему."}
            </small>
          </div>
        </div>
        {presets && presetKey && stages ? (
          <>
            <div className="djset-presets" role="group" aria-label="Тип развития сета">
              {presets.map((preset) => (
                <button
                  key={preset.key}
                  className="djset-preset"
                  aria-pressed={preset.key === presetKey}
                  title={`Выберите «${djSetPresetName(preset.key)}». ${djSetPresetSummary(preset.key)}`}
                  onClick={() => djSet.selectPreset(preset.key)}
                  type="button"
                >
                  <PresetOutline stages={preset.stages} />
                  <span>{djSetPresetShortName(preset.key)}</span>
                </button>
              ))}
            </div>
            {plan ? (
              <DjSetArc
                preset={presetKey}
                stages={plan.stages}
                plan={plan.slots}
                result={djSet.result}
                playingTrackId={playingTrackId}
                onIntensityChange={(index, edit) => {
                  if (edit.intensity_start !== undefined) djSet.setStageValue(index, "intensity_start", edit.intensity_start);
                  if (edit.intensity_end !== undefined) djSet.setStageValue(index, "intensity_end", edit.intensity_end);
                }}
                onSlotSelect={onSlotSelect}
              />
            ) : (
              <span className="embedding-search-requirement">График появится, когда все поля этапов и число треков заполнены.</span>
            )}
            <div className="custom-control-header">
              <div className="custom-control-copy">
                <span>Этапы</span>
              </div>
              <div className="djset-tools">
                <button title="Сдвинуть темп всех этапов на 1 BPM вниз, сохранив форму." onClick={() => djSet.shiftBpm(-1)} type="button">−1 BPM</button>
                <button title="Сдвинуть темп всех этапов на 1 BPM вверх, сохранив форму." onClick={() => djSet.shiftBpm(1)} type="button">+1 BPM</button>
                <button
                  title={`Вернуть этапам значения «${djSetPresetName(presetKey)}» по умолчанию.`}
                  disabled={!djSet.stagesChanged}
                  onClick={djSet.resetStages}
                  type="button"
                >
                  Сбросить
                </button>
              </div>
            </div>
            <div className="djset-stages" role="table" aria-label={`Этапы «${djSetPresetName(presetKey)}»`}>
              <div className="djset-stages-row djset-stages-head" role="row">
                <span role="columnheader">этап</span>
                {stageColumns.map((column) => (
                  <span role="columnheader" title={column.title} key={column.field}>{column.label}</span>
                ))}
              </div>
              {stages.map((stage, index) => {
                const label = djSetStageLabel(presetKey, stage.key);
                return (
                  <div className="djset-stages-row" role="row" key={stage.key}>
                    <span role="rowheader" title={label}>{label}</span>
                    {stageColumns.map((column) => (
                      <span role="cell" key={column.field}>
                        <input
                          name={`djset-stage-${stage.key}-${column.field}`}
                          type="number"
                          step={column.step}
                          value={stage[column.field] ?? ""}
                          aria-label={`${column.name}: ${label}`}
                          title={column.title}
                          onChange={(event) => djSet.setStageValue(index, column.field, numberOrNull(event.currentTarget))}
                        />
                      </span>
                    ))}
                  </div>
                );
              })}
            </div>
            {stages.some((stage) => djSetStageRules(stage).length) ? (
              <dl
                className="djset-rules"
                title="Правила этапа отбирают треки до подбора по интенсивности и темпу: трек без нужного ключа или скора на этап не попадает. Правила задаёт тип развития."
              >
                {stages.map((stage) => {
                  const rules = djSetStageRules(stage);
                  return (
                    <div key={stage.key}>
                      <dt>{djSetStageLabel(presetKey, stage.key)}</dt>
                      <dd>{rules.length ? rules.map((rule) => <span key={rule}>{rule}</span>) : "без правил"}</dd>
                    </div>
                  );
                })}
              </dl>
            ) : null}
          </>
        ) : (
          <span className="embedding-search-requirement">
            {djSet.presetsStatus === "unavailable"
              ? "Типы развития сета недоступны: перезапустите сервер. Сборка пойдёт по «The Arch»."
              : "Загружаем типы развития…"}
          </span>
        )}
      </section>

      <section className="djset-section" aria-label="Референсы">
        <div className="custom-control-header">
          <div className="custom-control-copy">
            <span>Референсы</span>
            <small>— что каждый seed-трек делает в сете.</small>
          </div>
        </div>
        {references.length ? references.map(({ track, role, slot }) => {
          const name = displayTrack(track);
          return (
            <div className="djset-reference" key={track.track_uuid}>
              <span className="djset-reference-name" title={name}>{name}</span>
              <div className="djset-reference-controls">
                <div className="segmented" role="group" aria-label={`Роль референса ${name}`}>
                  {roleChoices.map((choice) => (
                    <button
                      key={choice.key}
                      className={role === choice.key ? "active" : ""}
                      aria-pressed={role === choice.key}
                      title={choice.title}
                      onClick={() => djSet.setSeedRole(track, choice.key)}
                      type="button"
                    >
                      {choice.label}
                    </button>
                  ))}
                </div>
                <span className="djset-reference-slot">
                  {role === "slot" ? (
                    <input
                      name={`djset-slot-${track.track_id}`}
                      type="number"
                      min={1}
                      max={maxSlot}
                      step={1}
                      value={slot ?? ""}
                      placeholder="№"
                      aria-label={`Слот для ${name}`}
                      title={`Укажите номер слота для этого трека: от 1 до ${maxSlot}.`}
                      onChange={(event) => djSet.setSeedSlot(track, numberOrNull(event.currentTarget))}
                    />
                  ) : null}
                </span>
              </div>
            </div>
          );
        }) : (
          <span className="embedding-search-requirement">
            Референсов нет — сет соберётся из всей библиотеки. Добавьте seed-трек лупой в строке трека: он станет ориентиром и включит «Породу» и «Смещение».
          </span>
        )}
        <div className="search-filter-grid djset-fields">
          <label className={poolModelDisabled ? "disabled-filter" : undefined} title={poolModelTitle}>
            Порода: модель
            <select
              className="embedding-model-select"
              name="djset-pool-model"
              value={poolModel ?? ""}
              title={poolModelTitle}
              disabled={poolModelDisabled}
              onChange={(event) => setSetting("poolModel", event.target.value as SeedEmbeddingFamily)}
            >
              {poolModels.length ? poolModels.map((family) => (
                <option key={family} value={family}>{seedSearchModelPresentation[family].label}</option>
              )) : <option value="">нет эмбеддингов</option>}
            </select>
          </label>
          <NumberField
            label="Порода: пул"
            name="djset-pool-size"
            value={settings.poolSize}
            minimum={100}
            maximum={20000}
            step={100}
            title={poolSizeTitle}
            disabled={!hasReference}
            onChange={(value) => setSetting("poolSize", value)}
          />
          <label className={hasReference ? undefined : "disabled-filter"} title={axisTitle}>
            Смещение: ось
            <select
              className="embedding-model-select"
              name="djset-direction-axis"
              value={settings.directionAxis ?? ""}
              title={axisTitle}
              disabled={!hasReference}
              onChange={(event) => setSetting("directionAxis", (event.target.value || null) as DjSetDirectionAxis | null)}
            >
              <option value="">нет</option>
              {axisChoices.map((choice) => <option key={choice.key} value={choice.key}>{choice.label}</option>)}
            </select>
          </label>
          {settings.directionAxis !== null ? (
            <>
              <label className={hasReference ? undefined : "disabled-filter"} title={relationTitle}>
                Отношение
                <select
                  className="embedding-model-select"
                  name="djset-direction-relation"
                  value={settings.directionRelation}
                  title={relationTitle}
                  disabled={!hasReference}
                  onChange={(event) => setSetting("directionRelation", event.target.value as DjSetDirectionRelation)}
                >
                  {relationChoices.map((choice) => <option key={choice.key} value={choice.key}>{choice.label}</option>)}
                </select>
              </label>
              <NumberField
                label="Запас"
                name="djset-direction-margin"
                value={settings.directionMargin}
                minimum={0}
                maximum={50}
                title={marginTitle}
                disabled={!hasReference}
                onChange={(value) => setSetting("directionMargin", value)}
              />
            </>
          ) : null}
        </div>
      </section>

      <section className="djset-section" aria-label="Сборка">
        <div className="search-filter-grid djset-fields">
          <NumberField
            label="Треков"
            name="djset-tracks"
            value={settings.tracks}
            minimum={5}
            maximum={60}
            title="Укажите, сколько треков будет в сете: целое число от 5 до 60, не меньше числа этапов."
            onChange={(value) => setSetting("tracks", value)}
          />
          <label title="Укажите зерно, чтобы повторить сборку: целое число от 0 до 4294967295. Пустое поле — новое зерно при каждой сборке.">
            Зерно
            <span className="djset-seed">
              <input
                name="djset-seed"
                type="number"
                min={0}
                max={4294967295}
                step={1}
                value={settings.seed ?? ""}
                placeholder="новое"
                onChange={(event) => setSetting("seed", numberOrNull(event.currentTarget))}
              />
              <button
                className="icon-button"
                title={builtSeed === null
                  ? "Закрепить зерно последней сборки: сначала соберите сет."
                  : `Закрепить зерно последней сборки (${builtSeed}): следующая сборка с теми же настройками даст тот же сет.`}
                aria-label="Закрепить зерно последней сборки"
                disabled={builtSeed === null || builtSeed === settings.seed}
                onClick={() => setSetting("seed", builtSeed)}
                type="button"
              >
                <Pin size={15} />
              </button>
              <button
                className="icon-button"
                title="Отпустить зерно: каждая сборка возьмёт новое и даст другой сет."
                aria-label="Отпустить зерно"
                disabled={settings.seed === null}
                onClick={() => setSetting("seed", null)}
                type="button"
              >
                <Dices size={15} />
              </button>
            </span>
          </label>
          <label className="range-control djset-field-wide" title={varietyTitle}>
            <span>
              Вариативность
              <em>{settings.variety.toFixed(2)}</em>
            </span>
            <input
              name="djset-variety"
              type="range"
              min={0}
              max={1}
              step={0.05}
              value={settings.variety}
              title={varietyTitle}
              onChange={(event) => setSetting("variety", Number(event.target.value))}
            />
          </label>
        </div>
      </section>

      <div className="djset-build">
        <div className="embedding-search-row djset-build-row">
          <button
            className="embedding-search-button"
            title={buildTitle}
            aria-busy={pending || undefined}
            disabled={busy || pending || Boolean(djSet.problem)}
            onClick={djSet.build}
            type="button"
          >
            <ListMusic size={17} />
            {pending ? `Собираем… ${elapsedSeconds} с` : "Собрать сет"}
          </button>
          {pending ? (
            <button
              title="Прервать сборку: запрос отменяется, показанный сет остаётся."
              onClick={djSet.cancel}
              type="button"
            >
              Отмена
            </button>
          ) : null}
        </div>
        {djSet.problem ? <span className="embedding-search-requirement">{djSet.problem}</span> : null}
        {djSet.error ? <span className="embedding-search-requirement error" role="alert">{djSet.error}</span> : null}
      </div>
    </>
  );
}
