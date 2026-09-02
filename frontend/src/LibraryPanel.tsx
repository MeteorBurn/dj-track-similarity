import { CopyCheck, Database, FlaskConical, FolderOpen, Minus, Plus, RefreshCcw, Save, Settings2, ShieldCheck, Trash2, Zap } from "lucide-react";
import { AnalysisModel } from "./api";
import { mlAnalysisModelOrder, type AnalysisSelection, type StageSelection } from "./analysisSelection";

type LibraryHelpText = {
  databasePath: string;
  refreshTags: string;
  clearDatabase: string;
  sonaraAnalyze: string;
  maestAnalyze: string;
  mertAnalyze: string;
  muqAnalyze: string;
  clapAnalyze: string;
  writeMaestGenres: string;
  analyzeLimit: string;
};

const modelDescriptions: Record<AnalysisModel, string> = {
  sonara: "Считает темп, тональность, ритм, динамику, тембр и структуру трека.",
  maest: "Помогает понять жанровый характер трека.",
  mert: "Ищет похожее звучание от выбранного seed-трека.",
  muq: "Сохраняет дополнительный слой аудио-признаков.",
  mulan: "Связывает текстовое описание с отдельными аудио-эмбеддингами.",
  clap: "Связывает текстовое описание с аудио-звучанием."
};

type StageAction = {
  title: string;
  onClick: () => void;
  className: string;
};

export function LibraryPanel({
  databasePath,
  onChooseDatabase,
  busy,
  stageRunning,
  hasTracks,
  libraryTrackCount,
  maestGenreTrackCount,
  analysisLimit,
  onAnalysisLimitChange,
  helpText,
  onOpenScanDialog,
  onOpenSonaraSettingsDialog,
  onOpenMLSettingsDialog,
  onRefreshTags,
  onWriteMaestGenres,
  onClearDatabase,
  onValidateDatabase,
  onOpenAudioDedup,
  rhythmLabRunning,
  onLaunchRhythmLab,
  analysisCounts,
  selectedStages,
  onToggleStage,
  scanRootSelected,
  onStart,
  onResetAnalysis,
}: {
  databasePath: string | null;
  onChooseDatabase: () => void;
  busy: boolean;
  stageRunning: boolean;
  hasTracks: boolean;
  libraryTrackCount: number;
  maestGenreTrackCount: number;
  analysisLimit: number;
  onAnalysisLimitChange: (value: number) => void;
  helpText: LibraryHelpText;
  onOpenScanDialog: () => void;
  onOpenSonaraSettingsDialog: () => void;
  onOpenMLSettingsDialog: () => void;
  onRefreshTags: () => void;
  onWriteMaestGenres: () => void;
  onClearDatabase: () => void;
  onValidateDatabase: () => void;
  onOpenAudioDedup: () => void;
  rhythmLabRunning: boolean;
  onLaunchRhythmLab: () => void;
  analysisCounts: Record<AnalysisSelection, number>;
  selectedStages: StageSelection[];
  onToggleStage: (stage: StageSelection) => void;
  scanRootSelected: boolean;
  onStart: () => void;
  onResetAnalysis: (adapter: AnalysisModel) => void;
}) {
  const stagesDisabled = busy || stageRunning;
  const isSelected = (stage: StageSelection) => selectedStages.includes(stage);

  const stageRow = ({
    stage,
    title,
    description,
    count,
    disabled,
    action,
  }: {
    stage: StageSelection;
    title: string;
    description: string;
    count: number;
    disabled?: boolean;
    action: StageAction;
  }) => (
    <div className="stage-row" key={stage}>
      <span className="stage-check">
        <input
          className="stage-checkbox"
          type="checkbox"
          aria-label={`${title} selected`}
          checked={isSelected(stage)}
          disabled={stagesDisabled || disabled}
          onChange={() => onToggleStage(stage)}
        />
      </span>
      <span className="stage-name">
        <span className="stage-title">{title}</span>
        <span className="stage-description">{description}</span>
      </span>
      <span className="stage-count">{count}</span>
      <button className={`icon-button stop-button stage-action-button ${action.className}`} disabled={stagesDisabled} title={action.title} onClick={action.onClick} type="button">
        <Trash2 size={16} />
      </button>
    </div>
  );

  const modelRow = (model: AnalysisModel) => stageRow({
    stage: model,
    title: model.toUpperCase(),
    description: modelDescriptions[model],
    count: analysisCounts[model] || 0,
    disabled: model !== "sonara" && analysisCounts.sonara < 1,
    action: {
      title: `Сбросить ${model.toUpperCase()}`,
      onClick: () => onResetAnalysis(model),
      className: `${model}-reset-button`,
    },
  });

  const missingScanFolder = isSelected("database") && !scanRootSelected;
  const warnings: string[] = [];
  if (missingScanFolder) warnings.push("Укажите папку с треками в настройках загрузки.");
  const startDisabled = stagesDisabled || !selectedStages.length || missingScanFolder;

  return (
    <aside className="panel library-panel">
      <div className="panel-title"><FolderOpen size={18} /><h2>1. База и анализ</h2></div>

      <div className="library-panel-body">
        <div className="stage-section-description">
          <span>База данных</span>
          <small>Путь к SQLite библиотеке и загрузка новых треков с диска.</small>
        </div>
        <div className="path-row database-path-row">
          <input value={databasePath || ""} readOnly placeholder="Выберите SQLite базу" title={helpText.databasePath} />
          <button className="icon-button folder-picker database-picker-button" title="Выбрать SQLite базу" aria-label="Выбрать SQLite базу" disabled={stagesDisabled} onClick={onChooseDatabase} type="button"><Database size={17} /></button>
        </div>

        <div className="stage-card database-stage">
          <div className="stage-actions">
            {stageRow({
              stage: "database",
              title: "DATABASE",
              description: "Загружает новые треки из выбранной папки в базу.",
              count: libraryTrackCount,
              action: {
                title: "Очистить базу",
                onClick: onClearDatabase,
                className: "database-clear-button",
              },
            })}
          </div>
          <button className="stage-settings-button" title="Открыть параметры загрузки треков в базу" disabled={stagesDisabled || !databasePath} onClick={onOpenScanDialog} type="button"><Settings2 size={15} />Настройки загрузки треков в базу</button>
        </div>

        <div className="stage-section-description">
          <span>Инструменты</span>
          <small>Быстрые действия над всей библиотекой: теги, жанры, проверка, дубликаты, Rhythm Lab.</small>
        </div>
        <div className="library-tools-row">
          <button className="icon-button refresh-tags-button" disabled={stagesDisabled || !hasTracks} title="Обновить теги" aria-label="Обновить теги" onClick={onRefreshTags} type="button"><RefreshCcw size={16} />Refresh Tags</button>
          <button className="icon-button genre-save-button" disabled={stagesDisabled || !maestGenreTrackCount} title="Сохранить жанры" aria-label="Сохранить жанры" onClick={onWriteMaestGenres} type="button"><Save size={16} />Save Genres</button>
          <button className="icon-button database-validation-button" disabled={stagesDisabled || !hasTracks} title="Проверить базу" aria-label="Проверить базу" onClick={onValidateDatabase} type="button"><ShieldCheck size={16} />Validate Database</button>
          <button className={`icon-button rhythm-lab-button ${rhythmLabRunning ? "active" : ""}`} disabled={busy} title={rhythmLabRunning ? "Открыть Rhythm Lab" : "Запустить Rhythm Lab"} aria-label={rhythmLabRunning ? "Открыть Rhythm Lab" : "Запустить Rhythm Lab"} aria-pressed={rhythmLabRunning} onClick={onLaunchRhythmLab} type="button"><FlaskConical size={16} />Rhythm-Lab</button>
          <button className="icon-button audio-dedup-button" disabled={stagesDisabled || !hasTracks} title="Найти и разобрать дубликаты" aria-label="Найти и разобрать дубликаты" onClick={onOpenAudioDedup} type="button"><CopyCheck size={16} />Audio Dedup</button>
        </div>

        <div className="stage-section-description">
          <span>Sonara</span>
          <small>Основной анализ трека — темп, тональность, ритм и структура. Один запуск обработает отмеченные стадии и пропустит готовые результаты.</small>
        </div>
        <div className="stage-card sonara-stage">
          <div className="stage-actions">
            {stageRow({
              stage: "sonara",
              title: "SONARA",
              description: modelDescriptions.sonara,
              count: analysisCounts.sonara,
              disabled: !hasTracks,
              action: {
                title: "Сбросить SONARA",
                onClick: () => onResetAnalysis("sonara"),
                className: "sonara-reset-button",
              },
            })}
          </div>
          <button className="stage-settings-button" title="Открыть параметры анализа SONARA" disabled={stagesDisabled} onClick={onOpenSonaraSettingsDialog} type="button"><Settings2 size={15} />Настройки анализа SONARA</button>
        </div>

        <div className="stage-section-description">
          <span>ML-модели</span>
          <small>Выберите нужные способы анализа звучания.</small>
        </div>
        <div className="stage-card ml-stage">
          <div className="stage-actions">{mlAnalysisModelOrder.map(modelRow)}</div>
          <button className="stage-settings-button" title="Открыть параметры анализа ML-моделей" disabled={stagesDisabled} onClick={onOpenMLSettingsDialog} type="button"><Settings2 size={15} />Настройки анализа ML моделями</button>
        </div>

        <div className="worker-control analysis-limit" title={helpText.analyzeLimit}>
          <span>Лимит треков</span>
          <div className="stepper">
            <button className="icon-button analysis-limit-decrement-button" title="Уменьшить лимит треков" aria-label="Уменьшить лимит треков" disabled={stagesDisabled || analysisLimit <= 0} onClick={() => onAnalysisLimitChange(Math.max(0, analysisLimit - 1))} type="button"><Minus size={15} /></button>
            <input type="number" min={0} max={100000} value={analysisLimit} aria-label="Лимит треков: 0 = все треки; применяется отдельно к каждой стадии анализа" onChange={(event) => onAnalysisLimitChange(Math.min(100000, Math.max(0, Number(event.target.value) || 0)))} />
            <button className="icon-button analysis-limit-increment-button" title="Увеличить лимит треков" aria-label="Увеличить лимит треков" disabled={stagesDisabled || analysisLimit >= 100000} onClick={() => onAnalysisLimitChange(Math.min(100000, analysisLimit + 1))} type="button"><Plus size={15} /></button>
          </div>
          <small>0 = все треки; применяется отдельно к каждой стадии анализа</small>
        </div>
      </div>

      {warnings.length > 0 && (
        <ul className="stage-start-warnings" role="alert">
          {warnings.map((warning) => <li key={warning}>{warning}</li>)}
        </ul>
      )}
      <button
        className="stage-start-button"
        title="Запустить отмеченную стадию"
        disabled={startDisabled}
        onClick={onStart}
        type="button"
      >
        <Zap size={18} />
        Старт
      </button>
    </aside>
  );
}
