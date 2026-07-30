# Tags Metadata Storage Design

## Scope

Update only the metadata dialog's `Tags` block and the current, unversioned
Core database definition used by `dj-track-similarity`.

The work uses the real Core database at
`C:\projects\dj-track-similarity\database\volumes.sqlite`. Do not create a
backup, copy, migration, schema version, or contract version for this change.
Apply the database maintenance directly to that file in one SQLite
transaction. Roll back the transaction if any statement fails.

## Tags block

Rename `File and Mutagen tags` to `Tags`. Render one ordered metadata list:

1. Title
2. Artist
3. Album
4. Year
5. Country
6. Genre
7. BPM
8. Key
9. Label
10. Audio Length
11. Audio Format
12. Sample Rate
13. Bit Rate
14. Channels
15. Last Scanned
16. Missing Since
17. File Name
18. File Size
19. File Path

Keep the existing copy-path control on `File Path`. Do not show `Comment`,
`Catalog Number`, `ISRC`, `Track Number`, or `Disc Number` in this block.

Render audio duration in one row from the existing
`tracks.audio_duration_seconds` value:

```text
Audio Length    4:07 (247.37 sec.)
```

The clock portion rounds to the nearest whole second using the existing
`m:ss` or `h:mm:ss` representation. The parenthetical portion formats the
original finite duration to exactly two decimal places. Do not add another
database or API field for the formatted value.

Display `Last Scanned` and a populated `Missing Since` in European
`DD.MM.YYYY HH:mm:ss` form without fractional seconds. Preserve the stored
UTC RFC 3339 values and format them only for presentation so timestamp
validation, ordering, and database semantics remain intact.

Derive `File Name` from the stored `file_path`. Preserve numeric database
representations for file size, sample rate, bit rate, and channel count;
formatting these values remains a presentation responsibility.

Store `tracks.audio_duration_seconds` as one `REAL` value measured in seconds
and normalized to two decimal places before every write. Enforce that scale
in the current Core DDL with a `round(audio_duration_seconds, 2)` check.
Normalize all existing non-null durations in the real database with the same
rounding rule. SQLite stores a numeric value rather than textual trailing
zeroes; the UI must always render exactly two decimal places.

## Path storage

Store the resolved Windows path with its filesystem-provided component casing
directly in `tracks.file_path`. Normalize separators to `/`, but do not
lowercase the stored display path. For example:

```text
M:/Volumes/Avantgarde/HiRes/Artist/Track.wav
```

During scanning, obtain `file_path` from the path discovered by filesystem
enumeration. Refresh its stored casing even when file size, modification time,
and audio content are unchanged. Derive `File Name` from this stored
case-preserving path.

Do not add or persist a normalized path-key column. Keep `file_path` unique.
When repository operations must compare Windows paths without regard to
case, derive the existing ordinal lowercase identity key transiently in
memory. Perform the comparison and following write under the repository's
existing path-scoped write lock.

## Removed stored tags

Remove these fields completely from the current project definition:

- `catalog_number`
- `isrc`
- `disc_number`

Remove them from:

- the `file_tags` table;
- the `track_search_fts` virtual table;
- scanner tag aliases and scanned-tag models;
- database reads, writes, validation, and FTS synchronization;
- API response models and frontend types;
- tests and fixtures that define the current schema or response shape.

Continue storing `comment` and `track_number`, but do not display them in the
new `Tags` block.

Do not change `PRAGMA user_version` and do not add a migration path. The
change corrects the current initial schema definition.

## Real database maintenance

The existing database contains 3,017 `tracks` rows and 3,017 `file_tags`
rows. Before maintenance, `catalog_number` is populated for 1,022 rows,
`isrc` for 467 rows, and `disc_number` for 433 rows. Their removal is
intentional and irreversible.

Perform the following work directly in `volumes.sqlite`:

1. Acquire an immediate write transaction.
2. Rebuild `tracks` with its existing columns, case-preserving `file_path`,
   and the two-decimal `audio_duration_seconds` constraint.
3. Recover the actual casing of existing paths from filesystem enumeration
   under the accessible `M:/Volumes` tree and normalize all stored durations
   to two decimal places.
4. Rebuild `file_tags` with only the retained columns and copy all 3,017 rows.
5. Recreate `idx_file_tags_sort`.
6. Recreate `track_search_fts` without the three removed fields.
7. Repopulate the FTS table from `tracks`, retained `file_tags` values, and
   MAEST genres.
8. Verify row counts, exact-path uniqueness, and normalized durations before
   committing.
9. Commit only if all statements succeed.

Do not create backup or temporary database files. A temporary table inside
the same transaction is allowed and must not remain after commit or rollback.

## Verification

Use focused tests to prove:

- the Core DDL contains none of the three removed fields;
- scan and tag refresh paths do not read or write them;
- track detail responses omit them;
- FTS creation and synchronization use the retained fields;
- the metadata dialog renders the exact requested order;
- duration renders as `4:07 (247.37 sec.)`;
- timestamps render as `DD.MM.YYYY HH:mm:ss`;
- `File Name` is derived from `File Path`;
- `tracks.file_path` preserves filesystem casing;
- differently cased spellings of one Windows path resolve to one
  transient in-memory identity;
- an unchanged rescan refreshes the stored display-path casing.

After changing the real database, verify:

- `PRAGMA integrity_check` returns `ok`;
- `PRAGMA foreign_key_check` returns no rows;
- `tracks` and `file_tags` still each contain 3,017 rows;
- the three removed column names are absent from both relevant schemas;
- no temporary maintenance table remains;
- FTS contains one row per track;
- no path-key column exists;
- every non-null duration equals its value rounded to two decimal places;
- every available track path uses the casing returned by filesystem
  enumeration.
