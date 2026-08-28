# Know when audio files can be written

Most of what the app does leaves your source audio untouched. The exceptions are narrow and
deliberate, and this page covers what each one does when you run it.

[Local-first safety](../concepts/local-first-safety.md) holds the canonical list of read-only
workflows and write paths. This page is the operator view of the three writes you can trigger.

## The one write inside the app

`Сохранить жанры` (save genres), the Save icon in panel `1. База и анализ` (database and analysis),
is the only backend job that modifies audio files. Everything else in the browser writes SQLite,
logs, reports, temporary preview files, or export files.

The button is disabled until at least one track carries a stored MAEST genre.

### What the genre job writes

The job runs over every track with stored MAEST genres. The API rejects per-track genre writes, so
the current behavior is all available MAEST genre rows in one sequential job.

Each label is cleaned before it is written. An `_` character becomes a space, surrounding
whitespace is stripped, and a hierarchical MAEST label keeps only the part after its last `---`. Multiple labels
are joined with `; `.

The job writes only the standard genre field:

| Format | Tag field |
| --- | --- |
| MP3 | ID3 `TCON`, saved as ID3v2.3 |
| WAV/WAVE | Mutagen WAVE/ID3 genre handling, read back as `TCON` |
| AIF/AIFF, DSF, DFF | ID3 genre handling |
| FLAC | `GENRE` |
| M4A/MP4/ALAC | `©gen` |
| Anything else Mutagen can tag | ID3 genre when the tag object supports it, otherwise a `Genre` key |

An unsupported container raises `Unsupported audio tag format` for that track instead of writing
something else.

### The safety steps around each write

Every write goes through the same sequence:

1. The expected file state is captured before the write.
2. The genre field is written.
3. The tags are read back from disk.
4. The read-back genre values are compared with what was requested, and a mismatch raises
   `Genre tag readback mismatch after save`.
5. The scanned metadata for that track is refreshed in SQLite.

Normal tags such as title, artist, album, BPM, key, and comment are preserved. Failed writes are
recorded per track and the batch continues, with `applied`, `skipped`, and `failed` counts in the
job status.

To stop a running genre job, use the square Stop icon in the top bar.

## Audio Doctor apply

Audio Doctor is a standalone CLI tool. It has no API route and no button in the app.

Its protections, in the order they apply:

- Report mode is the default. Nothing is written without `--apply`.
- `--apply` repairs only files a previous run reported as repairable.
- Backups are created by default. `--no-backup` opts out.
- Each repair is verified, and a failed verification restores the backup.
- Apply runs sequentially rather than in parallel.

There is no confirmation phrase. `--apply` writes as soon as the command runs, so treat it as a
destructive flag and check the report first. See
[Audio Doctor](../tools-and-scripts/audio-doctor.md).

## Audio Dedup deletion

Audio Dedup is report-first in both surfaces, and only deletion touches files.

From the CLI, `--apply` prints a destructive-apply block and waits for you to type `APPLY DELETE`
exactly. It then deletes only safe candidates inside `--root`, and it skips a candidate whose keeper
is missing.

From the browser reviewer, you mark copies per group, choose `В корзину` (to the recycle bin) or
`Безвозвратно` (permanently) in the `Куда` (where to) select, then press
`Удалить помеченное` (delete the marked copies). A confirmation dialog names the count, the group
count, and the total size, and you answer `Да` (yes) or `Нет` (no).

The delete button becomes active as soon as at least one copy is marked and no job is running. The
`APPLY DELETE` phrase is still required by the API, and the browser client supplies it with the
request. Nobody types it in the browser. A selection that would empty a group is refused before the
request leaves the client.

Deletion removes SQLite rows only for tracks whose files were deleted. See
[Audio Dedup](../tools-and-scripts/audio-dedup.md).

## Relocation apply

`dj-sim relocate-library OLD NEW` previews by default and applies with `--apply`. It updates stored
SQLite paths only. It rejects conflicts and missing target files before applying, and it does not
move, copy, delete, or retag audio files.

Relocation has no browser surface. It is a CLI command with a matching API route.

## Single-track deletion

The delete action in the track detail dialog, titled `Удалить из базы` (delete from the database),
removes the track and its catalog-owned SQLite data after a confirmation. Its confirmation states
the outcome plainly:
`Будут удалены трек и все связанные данные SQLite. Аудиофайл <track> на диске останется.`
(the track and all related SQLite data are deleted, the audio file stays on disk).
