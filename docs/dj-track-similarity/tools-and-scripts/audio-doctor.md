# Audio Doctor

Audio Doctor inspects audio files for container and tag faults, and repairs the small set of cases
it knows how to fix safely. It is a standalone CLI tool.

There is no route for it in the application and no button in the browser. Every run starts from a
terminal.

```powershell
python tools\audio-doctor\audio_doctor_cli.py --help
```

## What it repairs

Repair is limited to six recognized states in WAV and AIFF containers:

| Reason | Meaning |
| --- | --- |
| `incomplete_pcm_tail` | WAV incomplete PCM frame at the end of the data chunk |
| `oversized_data` | WAV oversized data chunk before an ID3 chunk |
| `duplicate_id3` | WAV duplicate or unselected ID3 chunks |
| `empty_id3` | AIFF empty ID3 chunks |
| `container_normalization` (WAV) | WAV container and tag chunk normalization |
| `container_normalization` (AIFF) | AIFF container and tag chunk normalization |

Anything else is reported and left alone. Audio Doctor is not a tag editor and does not re-encode
audio.

## Choosing what to inspect

Four input sources, all repeatable and combinable:

| Option | Selects |
| --- | --- |
| positional paths | the files you name |
| `--folder PATH` | one folder scanned recursively for supported extensions |
| `--db PATH` | the `tracks.file_path` values stored in a library database |
| `--log PATH` | post-save readback-failed WAV paths extracted from a project log |

Two options reshape stored database paths before the filesystem is touched:

- `--db-root PATH` keeps only stored paths under that root, and marks it as the source root for
  remapping.
- `--file-root PATH` replaces each matching `--db-root` prefix with a local root. Use this when the
  library was built on another drive letter.

Two options narrow a `--log` run to a time window: `--since` and `--until`, both taking a timestamp
such as `2026-05-21 20:26`.

`--limit N` processes only the first N collected paths.

## Dry run

A run without `--apply` is read-only. Files are opened for reading, and the findings go to a report
plus a state file.

```powershell
python tools\audio-doctor\audio_doctor_cli.py --folder D:\Music
```

```powershell
python tools\audio-doctor\audio_doctor_cli.py --db .\data\library.sqlite
```

With root remapping:

```powershell
python tools\audio-doctor\audio_doctor_cli.py --db .\data\library.sqlite --db-root D:\OldMusic --file-root E:\Music
```

`--workers N` parallelizes the dry run. The default is `1`. Apply mode ignores it and always runs
sequentially.

`--summary-only` prints just the closing summary. `--color auto|always|never` controls status
colorization, defaulting to `auto`.

## Apply mode

`--apply` writes. Read this section before using it.

```powershell
python tools\audio-doctor\audio_doctor_cli.py --folder D:\Music --apply --reason oversized_data
```

The protections around a write, in order:

1. **Backup.** The whole file is copied into `tools/audio-doctor/data/backups` before anything is
   written. `--backup-dir PATH` moves that destination. `--no-backup` skips it, and the tool refuses
   `--backup-dir` and `--no-backup` together.
2. **Write.** Only entries the dry run classified as repairable are touched.
3. **Container verification.** The file is re-read and checked for a valid RIFF or FORM header, a
   declared size matching the file, and PCM block alignment.
4. **Tag verification.** Mutagen must read the repaired file cleanly.
5. **Restore on failure.** If any check fails, the backup is copied back over the file and the error
   is raised.
6. **Backup cleanup.** After a verified write the backup is deleted.

There is no confirmation phrase and no interactive prompt. `--apply` writes as soon as the run
reaches a repairable file. Earlier versions of this page and the tool's own README described an
`APPLY REPAIR` prompt. No such prompt exists in the code.

The backup is a rollback buffer for one write rather than an archive, because step 6 removes it once
verification passes. Take your own backup before a large apply run.

`--keep-id3 first|last|none` decides which readable top-level ID3 chunk survives a WAV repair. The
default is `first`.

### Scoping an apply run by reason

Folder and database runs record their findings in a state file. `--reason` then repairs one stored
reason at a time, so you can review a category before touching it.

```powershell
python tools\audio-doctor\audio_doctor_cli.py --folder D:\Music
python tools\audio-doctor\audio_doctor_cli.py --folder D:\Music --apply --reason duplicate_id3
```

Repeat `--reason` to include more than one. The value must match the reason recorded in the state
file exactly.

`--state PATH` overrides the state file. Its default path is derived from the resolved `--folder` or
`--db` sources and stored under `tools/audio-doctor/data/state`.

## Output

Every run writes a three-file bundle into `tools/audio-doctor/data/reports`, named
`audio_doctor_report_<timestamp>` with `.json`, `.xlsx`, and `.log` extensions. The closing summary
prints all three paths.

- `--out-dir PATH` moves the bundle.
- `--no-report` skips it.
- `--file-log PATH` writes an extra console transcript, overwritten on every run.
- `--no-file-log` skips that transcript.

Reports name file paths and diagnostics, so treat them as private. The output, state, and backup
directories under `tools/audio-doctor/data/` are ignored by Git.

## Related pages

- [Local-first safety](../concepts/local-first-safety.md)
- [Tags and audio writes](../user-guide/tags-and-audio-writes.md)
- [CLI reference](../reference/commands.md)
