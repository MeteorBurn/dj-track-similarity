# Frontend v7 Port — Context

## Текущее архитектурное состояние

Актуальный runtime — greenfield v7:

- обязательная Core SQLite;
- обязательная соседняя Artifacts SQLite;
- обе связаны одним `catalog_uuid`;
- Evaluation SQLite создаётся только при необходимости;
- не-v7 базы, отсутствующий Artifacts sidecar и несовпадающий `catalog_uuid` отклоняются fail-closed;
- in-place migration старых баз отсутствует;
- не добавляй скрытую совместимость с legacy v6/v1;
- не ослабляй schema validation ради UI.

`C:\db\volumes.sqlite` сейчас может быть старой базой с `user_version=1`. Не удаляй, не мигрируй и не перезаписывай её. Для разработки и тестов используй временные v7 Core + Artifacts bundles. Реальную библиотеку, аудио и массовый анализ не трогай без отдельного явного разрешения.

На момент составления задания рабочее дерево могло содержать несвязанные изменения:

- `docs/dj-track-similarity/reference/cli.md`;
- `docs/dj-track-similarity/ru/reference/cli.md`;
- EN/RU `persistent-ann-indexes.md`;
- `.kglite/code-review.kgl`;
- `.kglite/code-review.kgl.meta.json`.

Сначала выполни `git status`. Сохраняй любые несвязанные пользовательские изменения, не перезаписывай и не включай их в свой scope.

В рабочем дереве также может уже находиться незакоммиченная backend/tool-интеграция MuQ для SET, Hybrid, Rhythm Lab/classifiers и Audio Dedup. Считай её пользовательской и не откатывай. Сначала проверь текущий исполняемый код и тесты; подключай frontend к фактическому актуальному контракту, не дублируй backend-механизмы и не возвращай прежние hardcoded списки без MuQ.
