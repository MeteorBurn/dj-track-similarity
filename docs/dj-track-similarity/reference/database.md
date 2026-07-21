# Database reference

> Audience: Users and maintainers who need to know what local SQLite stores.
> Goal: Explain the database as local state, not a full schema dump.
> Type: reference

Selecting `library.sqlite` opens one catalog backed by three adjacent SQLite files:

| Store | File | Contents |
| --- | --- | --- |
| Core | `library.sqlite` | tracks, tags, light SONARA values, MAEST/MERT/MuQ/CLAP embeddings, flags, likes, classifier/evaluation state, FTS |
| Timeline | `library.timeline.sqlite` | complete SONARA arrays, time events, curves, and segments |
| Representations | `library.representations.sqlite` | optional SONARA embedding and fingerprint only |

All three carry the same generated catalog ID. The app refuses a side database copied from another
catalog. Keep the files together when moving or backing up a library.

## Main library state

The database stores:

- track paths, size, mtime, and selected metadata,
- working BPM, key, energy, duration, artist, title, and album fields,
- analysis presence flags for SONARA, MAEST, MERT, MuQ, and CLAP,
- one indexed Core `embeddings` table for the MAEST, MERT, MuQ, and CLAP float32 vectors used by search and ranking,
- SONARA Core metadata, including `bpm_confidence`, mood, instrumentalness, loudness, compact structure, beat-grid, key-candidate, vocalness, silence, Contrast, MFCC, and Chroma fields,
- `sonara_provenance`, including upstream analysis settings and the installed package version when available,
- `sonara_analysis_signature`, the deterministic SONARA/schema/mode/sample-rate/BPM-range/requested-profile/project-revision compatibility contract,
- Timeline and Representations field-name manifests used by the metadata dialog,
- liked tracks,
- classifier scores by `classifier_key`,
- FTS rows for library search,
- library settings such as promoted score-profile data where used.

The Timeline database preserves every returned sequence value. The Representations database stores
only SONARA's optional 48-dimensional vector as a float32 BLOB and its fingerprint as a JSON payload.
Regular track reads return only their field names, not the values. Mood affinities and
instrumentalness are data-only today. The project
retains true peak and ReplayGain for possible loudness-management workflows, while direct SONARA
similarity ignores both fields.

`GET /api/tracks/{track_id}/sonara-timeline` explicitly loads Timeline payload for a future workflow.
The metadata dialog does not call it.

The physical `has_sonara_analysis` flag describes Core only. Timeline and Representations freshness
comes from their own rows and signatures. Analysis scheduling checks the exact selected outputs.

## Schema migration

Opening a schema v5 main database migrates it to schema v6 and creates the two side databases. This
is intentionally a fresh SONARA migration. It keeps the catalog and MAEST metadata together with the
MAEST/MERT/MuQ/CLAP embeddings and their flags. Likes, feedback, evaluation rows, and embedding-only
classifier scores also remain. The migration deletes old SONARA values and curves, resets only the
SONARA Core flag. SONARA-dependent classifier scores become invalid. Schema v4 and older databases
are rejected rather than adapted.

The project also records the SONARA classifier feature revision in `library_settings`. On the first
main-database open after this revision changes, stored scores are invalidated when `feature_set` is
`combined` or any plus-separated source begins with `sonara`. This includes `sonara`, `sonara2`,
`sonara2vocal`, and their embedding combinations. Rhythm Lab records the same revision independently
and removes SONARA-dependent predictions when its labels database opens. Embedding-only scores and
predictions, Rhythm Lab labels, likes, pair feedback, and transition feedback are preserved. Old
model files are left in place for recovery, but SONARA-dependent manifests without the current
analysis signature cannot be scored. Retraining and promotion are required.

Do not confuse the version numbers: upstream SONARA analysis schema is `4`, the main SQLite schema
is `6`, the project SONARA feature revision is `4`, and the promoted classifier manifest version is
`2`. Revision `4` also signs `decoder_backend="sonara-symphonia"` and
`execution_path="analyze_batch"`.

## Evaluation and feedback state

Search and Hybrid diagnostics can record local evaluation rows. Examples include sessions plus result, feedback, and calibration rows.

## Rhythm Lab state

Rhythm Lab uses its own labels database by default under `tools/rhythm-lab/data/`. It stores profiles, labels, predictions, queues, collections, checkpoints, and the SONARA prediction feature revision. Revision invalidation removes dependent predictions only. Labels and feedback remain available for retraining.

## Write boundaries

- Scan, Refresh Tags, analysis, reset, clear, liked toggle, classifier scoring, feedback, and relocation apply write SQLite.
- Relocation apply changes only stored paths.
- Database clear deletes Core tracks and attached Timeline/Representations rows, then rebuilds track FTS state. It does not delete audio files.
- Reset SONARA deletes Core metadata, Timeline rows, SONARA embedding/fingerprint rows, and SONARA-dependent classifier scores.
- Reset SONARA removes its saved provenance and analysis signature together with its feature metadata and presence flag. It does not remove labels or feedback.
- Audio Dedup apply removes SQLite rows only for tracks whose files were successfully deleted.

## Backup habit

Before destructive SQLite maintenance on a real database, back up all three matching files or work on a copy. The database maintenance script does this automatically where supported.
