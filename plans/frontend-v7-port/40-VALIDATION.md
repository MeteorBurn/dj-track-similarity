# Frontend v7 Port — Validation and Final Report

## 14. Тестирование

Сначала зафиксируй baseline до изменений. Не доверяй утверждению о количестве passing tests в документации — запусти их сам.

### Frontend

Из `frontend/`:

- `npm run typecheck`;
- `npm test`;
- `npm run build`.

Обязательно добавить или обновить tests для:

- точных v7 API types;
- track summary/detail mapping;
- mutation identity;
- SONARA output kinds;
- MERT/MuQ/CLAP/SET/Hybrid/LAB/Audio Dedup payloads и response types;
- канонического MuQ model/source membership во всех закрытых TypeScript lists и `Record`;
- отдельной MUQ seed-search tab, generic `analysis_family="muq"` payload и current/missing/stale states;
- LAB model list, отдельной MuQ candidate group, availability reason и verdict с `model="muq"`;
- SET `sources`/`weights`, `missing_muq`, `weights_used`, MuQ toggle и legacy opt-out;
- Hybrid five-source defaults, MuQ toggle/weight/support/diagnostics и four-source legacy normalization;
- вложенных `Set Builder` / `Hybrid Preview` tabs: default selection, ARIA relations, Left/Right/Home/End navigation и отсутствие API request при простом переключении;
- независимого SET/Hybrid state и provenance: `Add preview` принимает только актуальный SET response, не search или Hybrid results;
- раздельной invalidation и late-response protection SET и Hybrid;
- Audio Dedup `sources`/`weights`/status, MuQ defaults, disabled-source payload и сохранения apply-confirmation UI;
- standalone Rhythm Lab MuQ `feature_status`, source copy и feature-set controls;
- отсутствия stale help/copy и четырёхисточниковых списков там, где актуальный contract пятиисточниковый;
- 100/500/1000/Все;
- chunk aggregation;
- deduplication;
- AbortController/stale-response guard;
- фильтров и смены базы во время загрузки;
- loading/progress/error/empty states;
- page-size selection;
- explicit no-database state;
- media preview и liked toggle;
- отсутствия legacy API names.

Обязательно пересмотри известные stale assertions в `frontend/tests/hybridPreviewState.test.mjs`, `frontend/tests/clapSimilaritySemantics.test.mjs`, `frontend/tests/apiContract.test.mjs` и `frontend/tests/setBuilderControls.test.mjs`; сохрани действующие MuQ LAB assertions в `referenceCompareContract.test.mjs`.

Добавь exact mocked-fetch serialization tests для MuQ search/reset, SET, Hybrid и Audio Dedup, включая omission optional fields и backend error text. Одних regex/assertions по тексту TSX/CSS недостаточно для независимого state, keyboard navigation и stale-request behavior: вынеси pure payload/signature helpers либо добавь минимальные component/browser behavioral tests.

Node tests не являются browser tests.

### Backend

Запусти focused backend tests для реально затронутых routes/repositories/schemas, включая:

- tracks/list/detail;
- database selection;
- analysis/pipeline;
- SONARA;
- MERT/search;
- MuQ generic search;
- CLAP text search;
- SET builder;
- Hybrid search;
- Reference Compare;
- Audio Dedup job contract;
- MuQ-containing classifier/Rhythm Lab feature contracts, если UI-порт потребовал backend alignment;
- Rhythm Lab bridge;
- v7 runtime/schema;
- artifact identity;
- reset/clear/mutations.

После focused green запусти максимально полный безопасный backend suite, если он укладывается в разумное время. Не используй реальную библиотеку.

### Rhythm Lab

Минимум:

`python -m pytest tools\rhythm-lab\tests\test_rhythm_lab.py --override-ini addopts=`

При изменении promoted scoring boundaries также:

`python -m pytest tests\test_break_energy.py --override-ini addopts=`

Добавь focused tests для v7 identity, pagination, MuQ feature status, `muq:<index>`/feature-set controls и UI API payloads. Не запускай реальное обучение, promotion или production scoring.

### Документация

Если меняются пользовательские команды, UI workflows, controls, backend contracts или setup:

- обнови соответствующие EN страницы;
- обнови зеркальные RU страницы;
- сохрани технические identifiers;
- выполни `npm run check` в `docs/dj-track-similarity/`.

Отдельно найди и обнови только после фактической реализации страницы, которые сейчас могут честно предупреждать об отложенном React v7/MuQ UI: `reference/ui-controls.md`, `getting-started/first-library.md`, `user-guide/smart-set-builder.md`, `tools-and-scripts/audio-dedup.md`, `tools-and-scripts/rhythm-lab.md`, `user-guide/class-tab.md` и их RU mirrors. Не оставляй после порта утверждение, что MuQ controls доступны только через CLI/API, но и не удаляй caveat для поверхности, которая реально осталась не портирована.

Не трогай текущие несвязанные dirty docs без необходимости.

## 15. Визуальная и runtime проверка

После typecheck/tests/build выполни реальную browser-проверку:

- не используй `frontend/dist` до свежей сборки;
- не коммить `frontend/dist`;
- проверь, не занят ли порт 8765 существующим процессом проекта;
- не останавливай чужой или пользовательский процесс;
- используй временную v7 Core + Artifacts database;
- не используй `C:\db\volumes.sqlite`, пока пользователь отдельно не разрешил работу с ней;
- проверь основной UI и Rhythm Lab UI;
- проверь desktop, узкое окно и 200% browser zoom;
- проверь верхнеуровневые вкладки SONARA, MERT, MUQ, CLAP, SET, CLASS, LAB;
- внутри SET проверь обе вложенные вкладки `Set Builder` и `Hybrid Preview`, keyboard navigation, независимое состояние и отсутствие stale списка другого workflow;
- проверь MuQ analysis/status, MUQ seed search, отдельную MuQ candidate group в LAB, MuQ controls/breakdown в SET и Hybrid;
- открой Audio Dedup dialog и проверь MuQ source/weight controls, defaults, disabled state и безопасный dry-run path без apply;
- в standalone Rhythm Lab проверь MuQ feature status и все видимые source/feature-set controls;
- проверь 100/500/1000/Все;
- проверь loading, отмену, смену фильтра, пустую БД и ошибки;
- проверь, что UI остаётся отзывчивым при нескольких тысячах synthetic summaries;
- проверь отсутствие console errors и failed requests.

На узком окне отдельно проверь, что основной tab strip не обрезает `MUQ`, вложенные SET tabs остаются кликабельными, source/weight grids переходят в одну колонку, labels/inputs не перекрываются и результаты не вызывают horizontal page overflow.

Если Playwright используется, помни: существующий `npm test` не запускает браузер автоматически. Browser smoke нужно выполнить отдельно.

## 17. Финальный отчёт

В конце дай краткий, но доказательный отчёт:

- что портировано;
- какие legacy contracts удалены;
- какие параметры добавлены по каждой вкладке;
- полную MuQ consumer matrix: backend contract → TypeScript type → UI file/control → behavior → test;
- где MuQ доступна для analysis, MUQ seed search, SET, Hybrid, LAB, Audio Dedup и standalone Rhythm Lab;
- какие default sources/raw weights и MuQ-disabled compatibility profiles используются в SET, Hybrid и Audio Dedup;
- как разделены вложенные `Set Builder` и `Hybrid Preview`, как защищён result provenance и почему `Add preview` не может взять чужие результаты;
- как реализованы 100/500/1000/Все;
- как предотвращены stale requests и UI freeze;
- что изменено в Rhythm Lab;
- какие SQLite-запросы оптимизированы;
- query-plan/benchmark before/after;
- какие тесты запускались и точные результаты;
- что проверено в браузере;
- какие ограничения остались;
- какие несвязанные dirty-файлы сохранены;
- текущий Git status.

Не создавай коммит, не пушь и не открывай PR, пока пользователь отдельно не попросит. Не останавливайся после аудита или частичного порта: продолжай до выполнения Goal либо до настоящего блокера, который невозможно безопасно обойти.
