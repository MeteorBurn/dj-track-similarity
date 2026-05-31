# Database and Stored Data

This page documents the current SQLite schema and the metadata/analysis payloads
stored in SQLite. Use it when you want to understand what the app saves, what a
reset removes, or why one search mode needs a particular analysis pass first.

## SQLite Specification

The current schema version is `3`.

Existing schema version `2` library databases are not migrated automatically by
the app. Run the standalone migration script first, with dry-run as the default
mode:

```powershell
.\.venv\Scripts\python.exe scripts\migrate_database_v3.py --db .\data\library.sqlite
.\.venv\Scripts\python.exe scripts\migrate_database_v3.py --db .\data\library.sqlite --apply
```

The script creates an online SQLite backup before `--apply`. Close the running
app before applying the migration to the same database.

The database is local user state. Normal scan, analysis, search, reset, clear,
and relocation workflows modify SQLite records only; they do not rewrite audio
files. The explicit exception is the separate MAEST genre tag write workflow,
which is documented in [Search & Tags](search-and-tags.md).

### `tracks`

Stores one row per indexed audio file:

- `id`: stable local track ID.
- `path`: unique stored audio path.
- `size`: file size at scan time.
- `mtime`: file modification time at scan time.
- `artist`, `title`, `album`: selected file metadata.
- `bpm`, `musical_key`, `energy`, `duration`: working fields used by the UI and
  analysis flows.
- `has_sonara_analysis`, `has_maest_embedding`, `has_mert_embedding`,
  `has_clap_embedding`: derived presence flags maintained by analysis writes
  and resets. They speed up library summary counters and missing-analysis
  candidate selection. They represent stored analysis presence, not a
  stale/fresh policy.
- `metadata_json`: JSON object for Mutagen fields and model-derived metadata.
- `created_at`, `updated_at`: local row timestamps.

`metadata_json` must be valid JSON. The schema has triggers to reject invalid
JSON on insert or update.

Use this table to answer "what tracks are in the library?" and "what metadata
or analysis summaries does the UI show for a row?" The `path` is the link back
to the local audio file; relocation updates that stored path only when the same
files moved to a new root.

### `embeddings`

Stores model vectors by track and embedding space:

- `track_id`: references `tracks.id`.
- `embedding_key`: currently `mert`, `clap`, or `maest`.
- `model_name`: model or checkpoint identifier.
- `dim`: vector dimension.
- `vector`: binary float32 vector payload.
- `updated_at`: local row timestamp.

The primary key is `(track_id, embedding_key)`, so the same track can have MERT,
CLAP, and MAEST vectors without mixing those spaces.

Use this table to check whether an embedding-backed workflow has enough data:
MERT search needs `mert`, CLAP text search needs `clap`, and promoted combined
classifiers need `mert` plus `maest` alongside Sonara features.

### `library_settings`

Stores local database-level settings such as the selected music root.

Use this table for app-level preferences tied to one database rather than one
track.

### `track_likes`

Stores the local liked-track list:

- `track_id`: references `tracks.id`.
- `liked_at`: local timestamp for the latest like action.

The primary key is `track_id`, so a track is either liked or not liked. Rows are
deleted automatically when the related track is removed from the local library
database. Likes are app state only; they never write to audio files or Mutagen
tags.

### `track_classifier_scores`

Stores derived classifier outputs by track and classifier key:

- `track_id`: references `tracks.id`.
- `classifier`: classifier key such as `live_instrumentation`.
- `score`: primary user-facing score used for filtering.
- `label`: coarse label such as `high`, `medium`, or `low`.
- `confidence`: maximum class probability.
- `probabilities_json`: classifier probabilities keyed by the profile's
  training labels.
- `feature_set`: feature family used by the classifier artifact, currently
  `combined`.
- `model_id`: promoted model path used for scoring.
- `analyzed_at`: local scoring timestamp.

The primary key is `(track_id, classifier)`, so rerunning a classifier updates
the score for that track instead of appending historical rows.

Use this table when a CLASS filter does not behave as expected. Missing rows
usually mean the promoted classifier has not scored that track yet, or the track
was missing required Sonara, MERT, or MAEST inputs during scoring.

## Metadata and Analysis Data

The app deliberately separates file tags from computed values.

Mutagen scanning reads this fixed whitelist:

- `artist`
- `title`
- `album`
- `genre`
- `year`
- `country`
- `label`
- `catalog_number`
- `track_number`
- `disc_number`
- `bpm`
- `key`
- `comment`
- `isrc`
- `duration`
- `audio_format`
- `audio_codec`
- `date`

Values are normalized into JSON-safe values before being stored. Mutagen-specific
objects such as ID3 timestamps are converted to strings.

`RefreshTags` replaces only this Mutagen metadata subset. It preserves stored
paths and model analysis data.

Analysis outputs live beside those file tags instead of replacing them. This is
why a track can show both file metadata such as `genre` or `bpm` and computed
values such as Sonara BPM, MAEST genres, embeddings, or classifier scores.
