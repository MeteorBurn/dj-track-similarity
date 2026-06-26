# Maintain the library

Audience: power users  
Goal: choose safe maintenance tools for database and audio-file edge cases  
Type: how-to

Maintenance workflows are intentionally separated from normal search and
analysis. Start with reports and dry-runs, then apply only when you understand
the scope.

## Choose the right tool

| Need | Tool |
| --- | --- |
| find likely duplicate audio rows/files | [Audio dedup](../tools-and-scripts/audio-dedup.md) |
| inspect or repair known metadata/container failures | [Audio repair](../tools-and-scripts/repair-audio-metadata.md) |
| compact and analyze a SQLite database | [Optimize database](../tools-and-scripts/optimize-database.md) |
| move stored paths after a library relocation | `dj-sim relocate-library` |

## Safe order

1. Back up the database or work on a copy.
2. Run report/dry-run mode first.
3. Read the output paths and selected scope.
4. Apply only the smallest operation that solves the problem.
5. Verify the post-condition.

## Apply boundaries

- Audio dedup is report-only by default. `--apply` requires explicit
  confirmation before deleting safe duplicate candidates.
- Audio repair is dry-run by default. `--apply` rewrites only files reported as
  repairable and uses full-file backups by default.
- Database optimization creates a SQLite backup before `VACUUM`, `ANALYZE`, and
  `PRAGMA optimize`.
- Library relocation updates stored SQLite paths only. It does not move, copy,
  delete, or retag audio.
