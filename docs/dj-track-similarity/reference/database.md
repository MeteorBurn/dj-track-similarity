# Database reference

> Audience: Users and maintainers who need to know what local SQLite stores.
> Goal: Explain the database as local state, not a full schema dump.
> Type: reference

The selected `.sqlite` file is the main local state store. It is not a cache you should delete casually if you care about analysis results, likes, feedback, or classifier scores.

## Main library state

The database stores:

- track paths, size, mtime, and selected metadata,
- working BPM, key, energy, duration, artist, title, and album fields,
- analysis presence flags for SONARA, MAEST, MERT, MuQ, and CLAP,
- SONARA feature metadata, including default `bpm_confidence` and requested mood, instrumentalness, loudness, structure, beat-grid, key-candidate, vocalness, and silence fields,
- `sonara_provenance`, including upstream analysis settings and the installed package version when available,
- `sonara_analysis_signature`, the deterministic SONARA/schema/mode/sample-rate/BPM-range/requested-profile/project-revision compatibility contract,
- embeddings in the `embeddings` table by `embedding_key`,
- complete SONARA sequences (`beats`, `onset_frames`, chord labels/events, `tempo_curve`, `energy_curve`, `loudness_curve`, `downbeats`) plus the SONARA `embedding` and `fingerprint` in the out-of-band `sonara_curves` table, loaded only for UI display and never read by search or classifiers,
- liked tracks,
- classifier scores by `classifier_key`,
- FTS rows for library search,
- library settings such as promoted score-profile data where used.

The out-of-band rows preserve every returned sequence value without expanding the SONARA metadata read by search. Mood affinities and instrumentalness are also storage-only today. The project retains true peak and ReplayGain for possible loudness-management workflows, while direct SONARA similarity ignores both fields.

`GET /api/tracks/{track_id}/sonara-curves` loads the out-of-band payload only when the UI or another client requests it. Regular track rows and full metadata responses do not load the curve table.

## Schema migration

Opening a schema v4 database migrates it to schema v5. The migration adds the
`tracks.has_muq_embedding` flag and backfills it from existing `muq` rows in the
`embeddings` table. Existing tracks, analysis data, likes, and feedback remain in the same
database. The independent SONARA classifier revision check is described below.

The project also records the SONARA classifier feature revision in `library_settings`. On the first main-database open after this revision changes, stored scores whose `feature_set` uses `sonara`, `sonara2`, `sonara2vocal`, or `combined` are invalidated. Rhythm Lab records the same revision independently and removes SONARA-dependent predictions when its labels database opens. Embedding-only scores and predictions, Rhythm Lab labels, likes, pair feedback, and transition feedback are preserved. Old model files are left in place for recovery, but SONARA-dependent manifests without the current analysis signature cannot be scored. Retraining and promotion are required.

## Evaluation and feedback state

Search and Hybrid diagnostics can record local evaluation rows. Examples include sessions plus result, feedback, and calibration rows.

## Rhythm Lab state

Rhythm Lab uses its own labels database by default under `tools/rhythm-lab/data/`. It stores profiles, labels, predictions, queues, collections, checkpoints, and the SONARA prediction feature revision. Revision invalidation removes dependent predictions only. Labels and feedback remain available for retraining.

## Write boundaries

- Scan, Refresh Tags, analysis, reset, clear, liked toggle, classifier scoring, feedback, and relocation apply write SQLite.
- Relocation apply changes only stored paths.
- Database clear deletes SQLite tracks, embeddings, and SONARA curves, then rebuilds track FTS state. It does not delete audio files.
- Reset SONARA also deletes that family's `sonara_curves` rows and SONARA-dependent classifier scores.
- Reset SONARA removes its saved provenance and analysis signature together with its feature metadata and presence flag. It does not remove labels or feedback.
- Audio Dedup apply removes SQLite rows only for tracks whose files were successfully deleted.

## Backup habit

Before destructive SQLite maintenance on a real database, make a backup or work on a copy. The database maintenance script does this automatically.
