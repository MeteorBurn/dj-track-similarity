# Database and Stored Data

This page documents the current SQLite schema and the metadata/analysis payloads stored in SQLite.

## SQLite Specification

The current schema version is `2`.

### `tracks`

Stores one row per indexed audio file:

- `id`: stable local track ID.
- `path`: unique stored audio path.
- `size`: file size at scan time.
- `mtime`: file modification time at scan time.
- `artist`, `title`, `album`: selected file metadata.
- `bpm`, `musical_key`, `energy`, `duration`: working fields used by the UI and
  analysis flows.
- `metadata_json`: JSON object for Mutagen fields and model-derived metadata.
- `created_at`, `updated_at`: local row timestamps.

`metadata_json` must be valid JSON. The schema has triggers to reject invalid
JSON on insert or update.

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

### `library_settings`

Stores local database-level settings such as the selected music root.

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
