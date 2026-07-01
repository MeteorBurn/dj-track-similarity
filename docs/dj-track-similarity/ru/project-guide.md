# Карта документации

> Audience: Читатели, которым нужна карта документации.
> Goal: Быстро выбрать tutorial, workflow, concepts или reference.
> Type: explanation

Эта страница помогает выбрать короткий маршрут. Начните с первых шагов, если создаёте новую базу; откройте сценарии для DJ-задач; используйте reference, когда уже знаете название команды, флага или endpoint.

## Разделы

- [Первые шаги](./getting-started/index.md) — установка, `scan`, анализ и первый полезный результат.
- [Руководство](./user-guide/index.md) — ежедневная работа в UI: библиотека, поиск, SET, экспорт и безопасные записи тегов.
- [Сценарии](./workflows/index.md) — практические маршруты для подготовки сета и обслуживания коллекции.
- [Концепции](./concepts/index.md) — понятные объяснения features, embeddings, scores и routing.
- [Инструменты](./tools-and-scripts/index.md) — Rhythm Lab, отчёты о дублях, repair helper и оптимизация базы.
- [Reference](./reference/index.md) — краткие факты по CLI, API, базе, конфигурации, анализу и UI.
- [Разработчику](./developer/index.md) — architecture, local development, verification и release checks.
- [Помощь](./help/index.md) — troubleshooting, FAQ и текущие ограничения.

## Текущая команда анализа

```powershell
dj-sim analyze --models sonara,maest,mert,clap --limit 25 --db .\data\library.sqlite
```

Поддерживаемые опции: `--models`, `--device auto|cpu|cuda`, `--top-k`, `--track-batch-size`, `--inference-batch-size`, `--diagnostics`. Для всей библиотеки в CLI не указывайте `--limit`. В UI `Analyze limit = 0` означает всю библиотеку, потому что UI отправляет отсутствие лимита.

## Сборка документации

Исходники лежат в `docs\dj-track-similarity`; сборка запускается командой `npm run build`; результат попадает в `site/` и отдаётся backend по `/docs/`.
