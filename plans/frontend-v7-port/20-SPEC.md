# Frontend v7 Port — Technical Specification

## 1. Полный frontend v7 port

Не считай наличие отдельных `TrackSummaryV7`/`TrackDetailV7` типов доказательством завершённого порта. Сейчас в `frontend/src/api.ts` одновременно остаётся старый основной `Track` с полями наподобие `id`, `path`, `size`, `mtime` и отдельные v7-типы. Найди все реальные consumers и устрани смешанный контракт.

Актуальные backend-модели используют, среди прочего:

- `track_id`;
- `catalog_uuid`;
- `track_uuid`;
- `content_generation`;
- `file_path`;
- `title`, `artist`, `album`;
- `tag_bpm`, `tag_key`;
- `audio_duration_seconds`;
- `liked`;
- `analysis_coverage`;
- `classifier_scores`;
- подробные `file`, `file_tags`, `sonara_core`, `maest`, `embeddings`;
- `classifier_scores_detail`;
- `optional_outputs`.

Требования:

- привести `frontend/src/api.ts` в точное соответствие `api_schemas.py`;
- обновить `frontend/src/apiClient.ts`;
- обновить все React consumers;
- обновить media preview, liked toggle, tags, reset/clear, search results, playlist/set state, dialogs и metadata display;
- mutation-запросы должны передавать актуальную identity:
  - `catalog_uuid`;
  - `track_uuid`;
  - `expected_content_generation`;
- не заменять точную v7 identity одним числовым ID там, где backend требует optimistic identity guard;
- допускается отдельный UI view model, но mapping должен выполняться в одном явном месте и не скрывать v7 identity;
- не использовать `any` и `as unknown as`;
- убрать реально мёртвые legacy types после порта;
- обновить frontend contract tests вместе с контрактами;
- проверить все backend response types, не только track list.

MuQ должна быть частью общего frontend-контракта, а не точечной вставкой:

- введи или расширь канонические TypeScript source/model types так, чтобы `muq` проходила тем же типизированным путём, что MERT, MAEST и CLAP;
- обнови imports/exports и props всех consumers этого общего типа; не оставляй локальные строковые aliases или неиспользуемые MuQ imports;
- найди все hardcoded массивы, `Record`, option lists, readiness/coverage maps, source labels, score breakdowns, reset/status views, help-тексты и test fixtures с закрытым списком моделей;
- не ограничивайся `frontend/src/api.ts`: обнови каждый реальный consumer и соответствующий тест;
- предпочитай общий типизированный source descriptor/config общим повторяющимся массивам, но не делай ради этого большой несвязанный refactor;
- удали или перепиши stale-текст о том, что MuQ существует “без поиска и SET”;
- не называй MuQ экспериментальной и не создавай отдельные имена вроде `experimental_muq`, `muq_audio` или второй API/storage path;
- CLAP text search должен оставаться отдельным от audio-to-audio CLAP evidence; добавление MuQ не должно смешивать эти семантики.

Минимальная MuQ consumer matrix для проверки:

- `frontend/src/api.ts` и `frontend/src/apiClient.ts`;
- `frontend/src/analysisSelection.ts`, `frontend/src/jobUi.tsx`, `frontend/src/useLibraryState.ts`;
- `frontend/src/LibraryPanel.tsx`, `frontend/src/helpText.ts`, `frontend/src/TrackMetadataDialog.tsx`, `frontend/src/trackDisplay.ts`;
- `frontend/src/App.tsx`, `frontend/src/useSearchPlaylist.ts`, `frontend/src/SearchPlaylistPanel.tsx`, `frontend/src/styles.css` и извлечённые из них search/SET/Hybrid tab-компоненты;
- `frontend/src/ReferenceComparePanel.tsx`;
- `frontend/src/AudioDedupDialog.tsx`;
- `tools/rhythm-lab/rhythm_lab/static/index.html`, `static/app.js`, `static/styles.css`;
- все frontend и Rhythm Lab UI/API tests, которые фиксируют model/source lists или пользовательский текст.

Основные точки:

- `frontend/src/api.ts`;
- `frontend/src/apiClient.ts`;
- `frontend/src/App.tsx`;
- `frontend/src/useLibraryState.ts`;
- `frontend/src/useSearchPlaylist.ts`;
- `frontend/src/libraryView.ts`;
- `frontend/src/TrackPanel.tsx`;
- `frontend/src/LibraryPanel.tsx`;
- `frontend/src/SearchPlaylistPanel.tsx`;
- `frontend/src/ReferenceComparePanel.tsx`;
- `frontend/src/ClapSearchTab.tsx`;
- `frontend/src/TrackMetadataDialog.tsx`;
- все frontend tests.

## 2. “Библиотека и прослушивание”: 100/500/1000/все

Добавь в блок `2. Библиотека и прослушивание` понятный контрол загрузки:

- `100`;
- `500`;
- `1000`;
- `Все`.

Требования к поведению:

- выбранный размер относится к текущему запросу, фильтрам, liked-state и preset;
- `1000` и `Все` нельзя реализовывать одним безграничным SQL/API-запросом;
- текущий `/api/tracks` имеет безопасный максимум `500`;
- загружай 1000 и все треки последовательными ограниченными chunk-запросами максимум по 500;
- добавь progress state: загружено N из total;
- добавь отмену или AbortController;
- новый поиск, фильтр, смена базы или preset должны отменять старую загрузку;
- поздний ответ старого запроса не должен перезаписать новое состояние;
- исключи дубли треков;
- корректно обрабатывай смену `content_generation`;
- не загружай тяжёлый `TrackDetailV7` для всего списка — только summaries;
- подробности, timeline и metadata загружай по требованию;
- режим `Все` должен работать для текущего фильтрованного результата, а не только для всей нефильтрованной БД;
- состояние Prev/Next/page input должно быть понятным в paged-режимах;
- в `1000`/`Все` допускается скрыть обычную пагинацию и показать progress/range;
- не рендери тысячи тяжёлых DOM-элементов без оптимизации;
- используй виртуализацию, windowing, incremental rendering или доказанно достаточный эквивалент;
- не добавляй новую тяжёлую dependency без доказанной необходимости;
- сохранение selection, preview, playlist и liked toggle должно оставаться корректным;
- “загрузить все” и “добавить все отфильтрованные треки в сет” — разные действия, не смешивай их.

Проверь поведение на временных библиотеках минимум с:

- 0 треков;
- 100 треков;
- 500 треков;
- 1000+ треков;
- несколькими тысячами synthetic track summaries.

## 3. SONARA

Актуальные output kinds:

- `core`;
- `timeline`;
- `embedding`;
- `fingerprint`.

Не использовать старое объединённое имя `representations`.

Портируй:

- выбор SONARA outputs;
- pipeline payload;
- job status;
- coverage/readiness;
- reset behavior;
- track detail;
- timeline;
- embedding/fingerprint availability;
- search mode and modifiers;
- missing/stale states.

Важные параметры, которые нужно проверить и при необходимости удобно подключить в UI:

- `outputs`;
- `batch_size`;
- search `mode`:
  - `balanced`;
  - `vibe`;
  - `sound`;
  - `dj_transition`;
  - `custom`;
- `limit`;
- `min_similarity`;
- `mixer_weights`:
  - `timbre`;
  - `rhythm`;
  - `dynamics`;
  - `harmonic`;
  - `tempo`;
- modifiers:
  - `energy`;
  - `valence`;
  - `acousticness`;
  - `brightness`;
  - `rhythm_density`;
  - `dynamic_range`;
  - `loudness`;
  - `vocalness`.

Не перегружай основной экран. Редко используемые параметры можно поместить в раскрываемый Advanced-блок с понятными defaults, reset и tooltips.

Готовность SONARA должна определяться по точным активным v7 contracts и текущей identity трека. Наличие старой строки само по себе не означает readiness.

## 4. MERT

Проверь и подключи актуальные параметры:

- `analysis_family="mert"`;
- `seed_track_ids`, без дублей, от 1 до 5;
- `limit`, максимум 500;
- `min_similarity`;
- `epsilon`;
- `noise`;
- analysis `device`;
- model readiness по точному активному embedding contract;
- корректные empty/loading/error states.

MERT search должен использовать только актуальные MERT embeddings. Не смешивай MERT с CLAP text scores или SONARA scores.

`device` относится только к analysis job. Не отправляй `device`, `bpm_tolerance`, `key_compatibility`, `energy_min` или `energy_max` в generic `/api/search`: v7 request имеет `extra="forbid"` и использует уже сохранённые embeddings.

## 5. MuQ

MuQ — штатная embedding-модель, а не экспериментальная опция. Канонические identifiers:

- analysis family: `muq`;
- output kind: `embedding`;
- существующий adapter: `MuqEmbeddingAdapter`;
- существующее v7-хранилище: `muq_embeddings`;
- feature names в classifier/Rhythm Lab: `muq:<index>`.

Не создавай отдельный MuQ endpoint, второй adapter, второй storage path или специальный pipeline. Используй существующий generic analysis/search/source механизм и фактический активный MuQ contract.

Проверь и подключи во всём основном UI:

- MuQ в analysis selection, ML pipeline payload, job progress/status, reset и library coverage;
- readiness только по точному текущему MuQ contract и текущей track identity;
- отдельную верхнеуровневую вкладку `MUQ` для seed-based candidate search по аналогии с `MERT`;
- generic search payload с `analysis_family="muq"`, уникальными `seed_track_ids` от 1 до 5, `limit`, `min_similarity`, `epsilon` и `noise` в точном соответствии backend;
- loading/error/empty/missing/stale states и понятную причину недоступности;
- `LibrarySummary.muq`, `analysis_coverage.muq` и MuQ entry в track detail `embeddings`/metadata там, где показываются остальные анализы;
- MuQ как включаемый source и отдельный score/breakdown signal в SET, Hybrid и Audio Dedup;
- самостоятельную группу MuQ-кандидатов в LAB/Reference Compare;
- MuQ feature readiness и feature-set controls в standalone Rhythm Lab UI.

Отдельно проверь доказанные contract-drift точки:

- frontend `SearchPayload` обязан явно передавать `analysis_family`; не оставляй implicit MERT default и removed legacy extra fields, которые v7 request отклоняет с `422`;
- reset analysis должен отправлять текущий backend key `analysis_family="muq"`, а response type — актуальные Core/Artifacts/classifier deleted-row fields, не legacy `tracks_updated`/`embeddings_deleted`;
- shared `EmbeddingSource`, `EvaluationSource` и `HybridSearchSource` должны включать MuQ и типизировать request/response, evaluation/score-profile sources и returned support без широкого `string[]`;
- если Hybrid response возвращает `source_contract_hashes`, добавь его в TypeScript contract и показывай/используй там же, где проверяется provenance остальных sources;
- help-текст classifier feature inputs не должен утверждать, что поддерживаются только SONARA/MERT/MAEST, если текущий manifest/scoring поддерживает MuQ и CLAP.

Не копируй бизнес-логику MERT целиком: выдели или переиспользуй общий типизированный seed-embedding-search компонент/хук, если это можно сделать локально и без большого refactor. При этом пользователь должен видеть самостоятельную вкладку `MUQ`, а не только скрытый model selector или MuQ внутри LAB.

При нулевом current MuQ coverage вкладка остаётся видимой, но Generate/Search disabled с ясной non-blocking причиной. Не делай MuQ обязательной для других feature recipes или workflow, где пользователь её отключил.

Сохрани runtime-инварианты MuQ: декодирование и resampling выполняет backend; сигнал 24 kHz `float32`; никакого half/bfloat/autocast/compile пути. Не добавляй в UI неподдерживаемые precision/compile controls и не описывай cosine similarity как вероятность или доказанную характеристику mood/genre.

## 6. CLAP

Проверь и подключи:

- `query`;
- `positive_queries`;
- `negative_queries`;
- `adaptive_contrast`;
- `preset`;
- `limit`;
- `min_similarity`;
- `device`;
- stored CLAP embedding readiness.

Сохрани текущую идею presets и negative prompt, но выровняй payload с backend.

Не описывай CLAP similarity как вероятность. Не смешивай CLAP text search с audio-to-audio CLAP evidence, которое используется в SET/Hybrid/Audio Dedup.

## 7. SET

Проверь точное соответствие `SetBuilderGenerateRequest`:

- `seed_mode`: `manual` или `auto`;
- `seed_track_ids`;
- `auto_seed_count`;
- `sources`: непустой уникальный список из `mert`, `maest`, `muq`, `clap`;
- `weights`: точные ключи включённых embedding sources плюс `sonara_broad`;
- `mode`:
  - `similar_crate`;
  - `weird_adjacent`;
  - `balanced_set`;
  - `discovery`;
- `limit`;
- `diversity`;
- `energy_curve`:
  - `warmup`;
  - `balanced`;
  - `peak`;
  - `wave`;
- `bpm_mode`:
  - `general`;
  - `low_to_high`;
  - `high_to_low`;
- `bpm_change`:
  - `slow`;
  - `medium`;
  - `fast`;
- `bpm_start`;
- `bpm_target`;
- `classifier_preferences`;
- `classifier_flows`;
- `random_seed`.

Default SET sources:

- `mert`;
- `maest`;
- `muq`;
- `clap`.

Текущие raw default weights, которые backend нормализует среди включённых сигналов:

- `mert`: `0.30`;
- `maest`: `0.18`;
- `muq`: `0.15`;
- `clap`: `0.22`;
- `sonara_broad`: `0.30`.

Не дублируй нормализацию во frontend как другой scoring contract: default/reset отправляет default `sources` и `weights=null` либо опускает optional field, а custom режим отправляет exact map. Показывай фактические `sources`/`weights_used` из response. Проверяй конечные неотрицательные значения, exact key set и хотя бы один положительный вес. Отключённый source не должен присутствовать в payload `sources` или `weights` и не должен требовать embedding для eligibility.

Сделай source/weight controls удобным Advanced-блоком внутри вкладки SET:

- MuQ включена по умолчанию и управляется тем же переключателем, что остальные embeddings;
- основные SET controls остаются видимыми без прокрутки через длинную Hybrid-форму;
- есть reset к backend defaults;
- показаны coverage, `missing_mert`, `missing_maest`, `missing_muq`, `missing_clap` и причины недоступности;
- breakdown и disabled reasons используют только включённые sources;
- нет silent fallback на stale embeddings или смешанный SONARA release.

Проверь реальную client-side validation, а не только HTML attributes: manual SET принимает 1–5 уникальных seeds, auto SET не требует предварительного seed, числовые `auto_seed_count`/`limit`/`diversity`/BPM/weights блокируются или clamp-ятся в backend bounds, пустой input не превращается молча в `0`, а `random_seed` соответствует показанному пользователю deterministic/random поведению.

Для точной pre-MuQ совместимости должна оставаться представимая конфигурация `sources=["mert","maest","clap"]` с raw weights `mert=0.30`, `maest=0.18`, `clap=0.22`, `sonara_broad=0.30`. Не делай её новым default; используй только как проверяемый legacy opt-out.

Сохрани read-only preview semantics: генерация SET не должна менять аудио или БД, пока пользователь явно не выполняет отдельное разрешённое действие.

SET и Hybrid не являются одним обязательным workflow-слоем. SET строит упорядоченный сет и его кривую/переходы через `/api/set-builder/generate`; Hybrid не должен оставаться длинным блоком, приклеенным под формой Set Builder.

## 8. Hybrid preview

Hybrid — отдельный weighted rank-fusion поиск кандидатов через `/api/search/hybrid`, а не обязательная стадия SET. Сохрани существующий внешний раздел `SET`, но внутри него создай вторичный tablist с двумя вкладками:

1. `Set Builder` — default при первом открытии.
2. `Hybrid Preview`.

Не добавляй Hybrid в основной ряд навигации `SET / SONARA / MERT / MUQ / CLAP / CLASS / LAB`: после добавления отдельной MUQ-вкладки основной ряд и так должен получить responsive/overflow обработку. Удали старое позиционирование “Hybrid preview inside SET” как одного длинного совместного экрана: это две соседние вложенные вкладки с разными endpoint, payload, score semantics и result state.

Проверь точное соответствие `HybridSearchRequest`:

- `seed_track_ids`: уникальные, от 1 до 5;
- `sources`: непустой уникальный список из `mert`, `maest`, `muq`, `sonara`, `clap`;
- `weights` или `score_profile`, но не оба одновременно;
- `per_source`;
- `limit`;
- `rrf_k`;
- `random_seed`;
- `transition_risk_weight`;
- `transition_risk_version`;
- `classifier_preferences`;
- `classifier_risk_weights`;
- `include_diagnostics`;
- `record_session`.

Default sources — `mert`, `maest`, `muq`, `sonara`, `clap`. Без custom weights backend использует равные нормализованные веса `0.20` для пяти sources; при явном legacy four-source списке без MuQ — `0.25` для каждого. Default/reset не должен копировать эти normalized значения в отдельный frontend scoring contract: отправляй `weights=null`/опускай field, пока пользователь не включил custom weights. UI показывает фактические `weights_used` из response, валидирует finite/nonnegative weights и не учитывает отключённые sources.

При `record_session=false` Hybrid остаётся полностью read-only. При `true` разрешены только предусмотренные Evaluation `search_sessions`/`search_result_events` и feedback; Core, Artifacts, production scores и аудиофайлы не изменяются.

Во вложенной вкладке `Hybrid Preview`:

- MuQ включена по умолчанию, имеет тот же toggle/weight UX, что остальные sources, и видна в `source_support`, diagnostics и score breakdown;
- source controls, advanced ranking/risk/classifier controls и diagnostics сгруппированы, а не выстроены одной ломаной колонкой;
- preview, selected candidate, feedback/evaluation session и ошибки принадлежат Hybrid state;
- смена Hybrid config инвалидирует только устаревший Hybrid preview;
- состояние и результаты SET не сбрасываются и не затираются;
- общую полосу выбранных seed tracks можно оставить над вложенным tablist, но явно учитывай разницу: manual SET требует seed, auto SET может работать без него, Hybrid требует от 1 до 5 уникальных seeds;
- переключение `Set Builder` ↔ `Hybrid Preview` не делает запрос, сохраняет введённые параметры, результаты и feedback обеих вкладок;
- при смене выбранной базы обе preview-сессии очищаются явно;
- вложенные tablist/tabpanel имеют отдельный `aria-label`, корректные `id`, `aria-selected`, `aria-controls`, `aria-labelledby`, keyboard navigation Left/Right/Home/End и устойчивую раскладку на desktop и узком окне.

Если `SearchPlaylistPanel.tsx` становится слишком большим, извлеки локальные `SetBuilderTab.tsx` и `HybridSearchTab.tsx` либо эквивалентные компоненты. Не превращай это в несвязанный рефактор всего App.

Устрани provenance-риск общего массива search results:

- SET preview хранится отдельно либо имеет строгий `resultOrigin`/`requestKey`;
- `Add preview` доступен только для последнего успешного и ещё актуального ответа `/api/set-builder/generate`;
- запуск SONARA/MERT/MUQ/CLAP search или Hybrid никогда не подменяет данные, которые добавляет `Add preview`;
- изменение SET seeds/config помечает SET preview stale и блокирует `Add preview` до новой генерации;
- изменение Hybrid input инвалидирует только Hybrid preview;
- поздний response/error/finally старого SET или Hybrid request не заменяет актуальный preview и не снимает loading нового запроса;
- список результатов от другого search workflow не остаётся видимым под активной вложенной вкладкой;
- liked/playlist изменения синхронизируются с локальными SET и Hybrid results без смешения их provenance.

Проверь backend explanation normalizer: MuQ cosine `-1..1` должна обрабатываться как другие embedding sources и нормализоваться в `0..1`. Если текущий `hybrid_explanation.EMBEDDING_SOURCES` всё ещё не содержит `muq`, исправь этот доказанный gap и добавь focused test для `-1 → 0`, `0 → 0.5`, `1 → 1`; schema для этого не меняется.

Не приписывай MuQ конкретную mood/texture/genre axis semantics без доказательств и не добавляй её механически в mood/texture/genre axes. Показывай её как общий acoustic embedding evidence. Не смешивай CLAP text query с хранимым CLAP audio embedding в Hybrid.

Не выдумывай один универсальный readiness/reason object для разных workflow. SET возвращает агрегированные `missing_*`; Hybrid — `source_contract_hashes`, warnings и per-result `source_support`; generic MuQ search при отсутствии точного active contract возвращает request-level ошибку. Отображай эти три семантики раздельно и типизируй фактические responses.

## 9. LAB и Reference Compare

В основной LAB/Reference Compare поверхности проверь:

- `seed_track_id`;
- models:
  - `clap`;
  - `mert`;
  - `muq`;
  - `maest`;
  - `sonara`;
- `limit`;
- verdict:
  - `mood`;
  - `palette`;
  - `instruments`;
  - `groove`;
  - `genre`;
  - `transition`;
  - `miss`;
- notes;
- availability/reason для каждой модели;
- сохранение текущего SET как Rhythm Lab collection;
- launch/status/stop Rhythm Lab;
- v7 source identity коллекций и треков.

LAB должна действительно показывать отдельную группу кандидатов MuQ, когда у seed и кандидатов есть current-contract MuQ embeddings. При отсутствии или stale MuQ данных показывай model-scoped unavailable/reason, не скрывай всю LAB и не подменяй MuQ другой моделью. Verdict должен сохраняться с `model="muq"` через тот же механизм, что остальные группы.

Не удаляй MAEST или MuQ consumers только потому, что основные вкладки ранее назывались SONARA/MERT/CLAP/SET/LAB.

## 10. Standalone Rhythm Lab UI

Rhythm Lab — отдельный safety domain:

- backend: `tools/rhythm-lab/rhythm_lab/web_app.py`;
- source DB adapter: `source_db.py`;
- Lab DB: `lab_db.py`;
- UI:
  - `static/index.html`;
  - `static/app.js`;
  - `static/styles.css`.

Портируй и проверь UI против текущего v7 source contract:

- Core + обязательный Artifacts sidecar;
- `catalog_uuid`;
- `track_uuid`;
- `content_generation`;
- текущий `file_path`;
- точные active contracts;
- `feature_status` для SONARA/MERT/MAEST/CLAP/MuQ;
- MAEST genre/syncopation fields;
- current SONARA Core fields;
- predictions и labels с текущей identity;
- liked toggle как единственный разрешённый narrow write в source DB.

MuQ-specific standalone UI requirements:

- убери stale readiness/copy, где перечислены только SONARA/MERT/MAEST/CLAP или только SONARA/MERT/MAEST;
- показывай MuQ в `feature_status` с current/missing/stale причиной;
- если UI предлагает выбор training/ablation feature sources, добавь штатный `muq` и generic комбинации через существующий синтаксис `source+source`;
- отображай `muq:<index>` как обычные contract-dimensional features, не хардкодь альтернативную размерность;
- сохрани compatibility alias `combined` с его текущим значением `sonara+mert+maest`; не меняй его молча на “всё”;
- readiness/training gate должен вычислять required sources из выбранного feature recipe, а не из hardcoded глобального списка SONARA/MERT/MAEST и не требовать MuQ для legacy recipe без неё;
- не запускай обучение, promotion или scoring автоматически только из-за изменения UI;
- frontend readiness не должен разрешать stale MuQ-containing classifier artifact.

Все остальные labels, predictions, queues, checkpoints и metrics должны оставаться в Lab DB.

Сохрани:

- profile-scoped delete;
- точное подтверждение удаления;
- stale-prediction guards;
- SONARA invalidation semantics;
- сохранение labels при смене SONARA revision;
- запрет обучения/продвижения stale SONARA-dependent artifacts.

Rhythm Lab уже имеет backend pagination до 500. Не поднимай лимит без измерений. Можно улучшить page-size control и loading UX, но обязательные `100/500/1000/Все` относятся прежде всего к основному блоку `Библиотека и прослушивание`.

## 11. Audio Dedup frontend

Портируй `frontend/src/AudioDedupDialog.tsx` и связанные TypeScript contracts к актуальному backend payload/status:

- `sources`: непустой уникальный список из `mert`, `maest`, `muq`, `clap`;
- `weights`: exact key set выбранных sources;
- status/response должны возвращать и показывать фактически применённые `sources` и `weights`;
- MuQ должна быть отдельным toggle и weight control, включённым по умолчанию;
- disabled source не отправляется и не участвует в эффективном score;
- copy для `min_similarity` и evidence должна называть MERT, MAEST, MuQ и audio-to-audio CLAP, а не CLAP text search.

Текущие raw defaults:

- `mert`: `0.43`;
- `maest`: `0.32`;
- `muq`: `0.12`;
- `clap`: `0.04`.

Показывай, что score нормализуется по реально доступным evidence, но не изображай его вероятностью. Для точной pre-MuQ совместимости оставь представимой конфигурацию `sources=["mert","maest","clap"]` с raw weights `0.43/0.32/0.04`; это opt-out, а не default.

Не ослабляй destructive safety:

- dry-run/report остаётся default;
- exact confirmation `APPLY DELETE`, root boundary, report identity и file-state checks сохраняются;
- для любого non-legacy source/weight profile backend по-прежнему должен требовать положительные MERT и MAEST weights и самостоятельное MERT+MAEST corroboration;
- высокий MuQ или CLAP score сам по себе не разрешает удаление;
- UI объясняет blocked reasons, но не пытается заменить backend-проверки;
- browser/runtime tests не запускают apply и не удаляют реальные файлы.

## 12. Оптимизация SQLite

Сначала измеряй, потом меняй.

Эта frontend-задача не разрешает SQLite DDL, новый index, изменение `user_version`, schema/version bump, migration, validator relaxation или изменение topology Core/Artifacts/Evaluation. MuQ уже использует существующие v7 contracts и `muq_embeddings`; для UI-интеграции не нужна новая таблица, колонка или sidecar.

Перед SQLite-работой прочитай `%SQLITE_TOOLKIT_HOME%\AGENTS.md` и используй toolkit по явному пути. Для тестов используй только временные v7 bundles.

Проверь:

- `paginate_track_summaries`;
- фильтры LIKE/FTS;
- liked filter;
- MAEST syncopated filter;
- classifier score filters;
- `COUNT(*)` для total;
- `ORDER BY`;
- `LIMIT/OFFSET`;
- повторные чтения library summary;
- N+1 запросы;
- повторную contract/schema validation;
- Rhythm Lab `list_tracks_page`;
- Rhythm Lab `list_predictions_page`;
- Core ↔ Artifacts binding reads;
- загрузку 100/500/1000/всех summaries.

Используй:

- `EXPLAIN QUERY PLAN`;
- synthetic temp v7 database;
- детерминированные benchmark fixtures;
- несколько прогонов и медиану;
- before/after evidence.

Предпочитай:

- уменьшение повторных запросов;
- корректное кеширование summary с явной invalidation;
- batch reads;
- отсутствие N+1;
- existing indexes;
- bounded chunking;
- detail-on-demand.

Не делай:

- `VACUUM`, destructive maintenance или schema rewrite на реальной базе;
- новый индекс «на всякий случай»;
- ослабление schema validation;
- скрытое изменение v7 contract под тем же version без архитектурного решения;
- in-place migration legacy DB;
- массовую reanalysis/retraining;
- изменение audio files.

Если измерение всё же показывает необходимость нового индекса, зафиксируй query plan/benchmark evidence и оставь отдельную рекомендацию; не внедряй индекс в этой задаче. Реализация ограничена query shape, batching, bounded chunking, устранением N+1, reuse/caching с явной invalidation и detail-on-demand на существующей схеме и индексах.

## 13. Лёгкое улучшение UI без редизайна

Нужны точечные улучшения, а не новый дизайн:

- более ясные loading/progress/empty/error states;
- компактная группировка основных и advanced параметров;
- понятные disabled reasons;
- последовательные labels/tooltips;
- доступные кнопки и input labels;
- сохранение keyboard navigation;
- адаптивное поведение на обычной ширине окна;
- отсутствие layout jumps при загрузке;
- визуально понятный выбранный режим 100/500/1000/Все;
- не блокировать весь UI при chunk loading;
- не сбрасывать введённые пользователем параметры после ошибки.

Следуй корневому `DESIGN.md` и CSS tokens:

- не добавляй raw hex/rgb в React components;
- не вводи CSS-in-JS;
- не добавляй декоративную анимацию;
- все кнопки — `type="button"`;
- missing analysis — non-blocking empty state;
- не меняй узнаваемую структуру вкладок и основных рабочих сценариев без необходимости.

Осторожно разделяй `App.tsx`: небольшой осмысленный extraction допустим, большой несвязанный refactor — нет.

Отдельная `MUQ` tab и вложенные `Set Builder` / `Hybrid Preview` tabs — требуемое изменение структуры, а не запрещённый редизайн. Сделай основной tab strip адаптивным: доступный horizontal overflow или другой устойчивый паттерн без обрезанных кнопок, наложения controls и layout jumps. Вложенные две вкладки SET на узком экране должны оставаться полностью доступными, а фиксированные двухколоночные grids переходить в одну колонку.
