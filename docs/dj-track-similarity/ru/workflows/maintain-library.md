# Maintain the library

Аудитория: power users  
Цель: безопасно выбирать maintenance tools для database и audio edge cases  
Тип: how-to

Maintenance workflows отделены от обычного search и analysis. Начинайте с
reports and dry-runs, затем apply только когда scope понятен.

## Choose the right tool

| Need | Tool |
| --- | --- |
| найти likely duplicate audio rows/files | [Audio dedup](../tools-and-scripts/audio-dedup.md) |
| inspect/repair known metadata/container failures | [Audio repair](../tools-and-scripts/repair-audio-metadata.md) |
| compact/analyze SQLite database | [Optimize database](../tools-and-scripts/optimize-database.md) |
| move stored paths after relocation | `dj-sim relocate-library` |

## Safe order

1. Сделайте backup database или работайте на copy.
2. Запустите report/dry-run mode.
3. Прочитайте output paths и selected scope.
4. Apply только smallest operation, решающую проблему.
5. Verify post-condition.

## Apply boundaries

- Audio dedup report-only by default. `--apply` требует explicit confirmation.
- Audio repair dry-run by default. `--apply` переписывает только files reported
  as repairable и делает full-file backups by default.
- Database optimization создает SQLite backup перед `VACUUM`, `ANALYZE` и
  `PRAGMA optimize`.
- Library relocation обновляет только stored SQLite paths. Оно не move, copy,
  delete или retag audio.
