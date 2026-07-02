# Database reference

> Audience: Users and maintainers who need to know what local SQLite stores.
> Goal: Explain the database as local state, not a full schema dump.
> Type: reference

The selected `.sqlite` file is the main local state store. It is not a cache you should delete casually if you care about analysis results, likes, feedback, or classifier scores.

## Main library state

The database stores:

- track paths, size, mtime, and selected metadata,
- working BPM, key, energy, duration, artist, title, and album fields,
- analysis presence flags for SONARA, MERT, MAEST, and CLAP,
- embeddings in the `embeddings` table by `embedding_key`,
- liked tracks,
- classifier scores by `classifier_key`,
- FTS rows for library search,
- library settings such as promoted score-profile data where used.

## Evaluation and feedback state

Search and Hybrid diagnostics can record local evaluation rows. Examples include sessions plus result, feedback, and calibration rows.

## Rhythm Lab state

Rhythm Lab uses its own labels database by default under `tools/rhythm-lab/data/`. It stores profiles, labels, predictions, queues, collections, and checkpoints.

## Write boundaries

- Scan, Refresh Tags, analysis, reset, clear, liked toggle, classifier scoring, feedback, and relocation apply write SQLite.
- Relocation apply changes only stored paths.
- Database clear deletes SQLite tracks and embeddings, then rebuilds track FTS state. It does not delete audio files.
- Audio Dedup apply removes SQLite rows only for tracks whose files were successfully deleted.

## Backup habit

Before destructive SQLite maintenance on a real database, make a backup or work on a copy. The database maintenance script does this automatically.
