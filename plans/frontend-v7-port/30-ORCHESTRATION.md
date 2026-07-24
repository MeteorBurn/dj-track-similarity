# Frontend v7 Port — Orchestration

## Роль главного агента

Ты — главный интегратор и оркестратор:

- сначала изучи архитектуру и составь точную матрицу backend API → TypeScript contracts → UI consumers → tests; для MuQ матрица должна охватывать каждый реальный model/source/readiness/breakdown consumer, а не только вкладку анализа;
- вызывай субагентов параллельно только для независимых и ограниченных подзадач;
- не отдавай субагентам финальную интеграцию общих fan-in файлов;
- сам контролируй изменения в `frontend/src/api.ts`, `frontend/src/apiClient.ts`, `frontend/src/App.tsx`, backend schemas/routes и общих v7-контрактах;
- не позволяй нескольким субагентам одновременно редактировать одни файлы;
- субагенты не должны самостоятельно коммитить, пушить, создавать PR, менять реальную БД или запускать массовый анализ музыки;
- регулярно собирай результаты субагентов, проверяй их по исходникам и тестам и только затем интегрируй.

Перед любыми изменениями полностью прочитай:

- все `AGENTS.md` и `AGENTS.override.md` в репозитории;
- `E:\Projects\dj-track-similarity\.omo\drafts\database-schema-redesign.md`;
- `README.md`;
- `pyproject.toml`;
- `frontend/package.json`;
- `frontend/AGENTS.md`;
- `DESIGN.md`;
- `tools/rhythm-lab/AGENTS.md`;
- актуальные backend schemas, routes, repositories и tests;
- `git show` для коммитов:
  - `79295a0` — greenfield v7 storage architecture;
  - `b3b512a` — server without implicit database;
  - `387a6e8` — interactive Windows database launcher.

Явная авторизация этой задачи отменяет только прежнюю отсрочку frontend v7 port в корневом `AGENTS.md`. Все остальные ограничения и правила безопасности сохраняются.

## Настройка моделей и reasoning субагентов

Если выбор модели доступен, используй:

1. Главный агент:
   - модель: `gpt-5.6-sol`;
   - reasoning: `xhigh`;
   - `max` используй только для финального cross-system integration review или сложного архитектурного конфликта.

2. Backend/API/v7 contract audit:
   - модель: `gpt-5.6-sol`;
   - reasoning: `xhigh`.

3. SQLite/query/index performance audit:
   - модель: `gpt-5.6-sol`;
   - reasoning: `xhigh`.

4. Основной React UI, состояние и производительность:
   - модель: `gpt-5.6-sol` или `gpt-5.6-terra`;
   - reasoning: `high`;
   - для сложной типизации/API alignment — `gpt-5.6-sol xhigh`;
   - для локального UX/CSS — `gpt-5.6-terra high`.

5. Rhythm Lab UI:
   - модель: `gpt-5.6-sol`;
   - reasoning: `high` или `xhigh`, если затрагивается source identity/feature contract.

6. Финальный code/test review:
   - модель: `codex-auto-review`;
   - reasoning: `xhigh`.

7. Документация:
   - модель: `gpt-5.6-terra`;
   - reasoning: `medium` или `high`.

При model override создавай субагентов с `fork_turns="none"` или небольшим числом последних turns и передавай им самодостаточное задание с точными файлами, контрактом и ограничениями. Не используй полный fork при явном model override. Не ставь `ultra` для механических исправлений, CSS, docs или простых тестов.

Рекомендуемый порядок:

### Фаза A — параллельный read-only аудит

Можно параллельно запустить до 5–6 read-only субагентов:

- backend v7 API/schema contract audit;
- frontend legacy/v7 contract inventory;
- SONARA/MERT/MAEST/MuQ/CLAP/SET/Hybrid/LAB/Audio Dedup parameter inventory;
- Rhythm Lab v7 UI/source identity audit;
- SQLite query-plan/performance audit;
- frontend baseline test and visual-regression inventory.

Они не должны редактировать файлы.

### Фаза B — реализация независимых частей

После аудита раздай непересекающиеся write-задачи:

- React library-loading UX;
- отдельные tab-компоненты;
- Rhythm Lab static UI;
- backend query/API optimization;
- focused tests;
- EN/RU docs.

Главный агент оставляет за собой общие API types, App state, backend contract changes и финальную интеграцию.

Не допускай бесконтрольного дерева субагентов. Обычно достаточно 3–5 одновременно работающих write-агентов с точным file ownership.
