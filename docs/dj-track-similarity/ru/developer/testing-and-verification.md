# Тестирование и проверка

> Для кого: Разработчики, выбирающие проверки после изменения.
> Задача: Запустить сфокусированные проверки, соответствующие риску правки.
> Тип: Практическая инструкция

## Обычные проверки

```powershell
python -m pytest tests
python -m pytest tools\rhythm-lab\tests scripts\tests
npm --prefix .\frontend test
npm --prefix .\frontend run typecheck
npm --prefix .\frontend run build
npm --prefix .\docs\dj-track-similarity run check
git diff --check
```

Корневая конфигурация Pytest нацелена только на `tests/`. Наборы отдельных инструментов запускайте
явно через `python -m pytest tools/rhythm-lab/tests scripts/tests`.

`npm run check` выполняет строгую проверку Vale для `README.md` и дерева Markdown, затем собирает
сайт. После свежего клонирования репозитория или изменения пакетов Vale один раз выполните
`npm run vale:sync`; список пакетов указан в `.vale.ini`. Для того же отчёта без завершения с ошибкой используйте `npm run lint:style`.

## Примеры целевых проверок

- Audio Doctor: `scripts\tests\test_repair_audio_metadata.py` и `tests\test_api_audio_doctor.py`.
- Audio Dedup: `scripts\tests\test_audio_dedup.py`.
- Rhythm Lab: `tools\rhythm-lab\tests\test_rhythm_lab.py`.
- Контракт и хранилище SONARA: `tests\test_sonara_contract.py` и `tests\test_sonara_features.py`.
- Темп, Camelot, SET и переходы: `tests\test_tempo_resolution.py`, `tests\test_track_resolution.py`, `tests\test_set_builder.py` и `tests\test_transition_diagnostics.py`.
- Совместимость классификаторов: `tests\test_classifier_productionization.py`, `tests\test_break_energy.py` и `tools\rhythm-lab\tests\test_rhythm_lab.py`.

## Безопасность

Не запускайте разрушительные режимы применения или удаления для обычной проверки. Тесты должны
использовать временные базы.
