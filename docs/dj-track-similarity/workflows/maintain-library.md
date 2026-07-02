# Maintain a library safely

> Audience: Users keeping a local library and SQLite database healthy.
> Goal: Give a routine that avoids accidental audio edits.
> Type: workflow

## Routine checks

1. **Scan** after adding new files. Scan updates SQLite rows for changed file stats and reads tags.
2. **Refresh Tags** after editing tags externally. It rereads selected Mutagen tags for existing tracks.
3. **Analyze missing data** only for the families you need.
4. **Reset selectively** when you intentionally want one analysis family recomputed.
5. **Export** review crates and sets rather than editing audio files.

## Moving a library

Use relocation preview first. Apply only after the preview has no conflicts and no missing target files. Relocation apply updates stored SQLite paths only.

CLI:

```powershell
dj-sim relocate-library D:\Music E:\Music --db .\data\library.sqlite
```

Apply:

```powershell
dj-sim relocate-library D:\Music E:\Music --apply --db .\data\library.sqlite
```

## Reports before repairs

Use Audio Doctor in dry-run mode before repair. Use Audio Dedup in report mode before delete. Review XLSX reports before any apply mode.

## Database maintenance

Run database optimization only on a local SQLite file you control. The script creates a backup and runs integrity checks before and after maintenance.

```powershell
python scripts\optimize_database.py --db .\data\library.sqlite
```

## Do not use apply modes as tests

Audio Doctor apply and Audio Dedup apply are real file operations. Do not run them as routine verification.
